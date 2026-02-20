"""
video-analyzer MCP server.

Exposes 3 tools to any MCP client (Claude Code, Claude Desktop, etc.):
  extract_video(url)         — process a video, save a session
  get_session(session_id)    — return session data (descriptions + transcript)
  list_sessions()            — list all processed videos

Claude Code usage:
  Add to ~/.claude.json or settings:
    {
      "mcpServers": {
        "video-analyzer": {
          "command": "python",
          "args": ["/home/ashmit/projects/video-analyzer/server.py"],
          "env": { "ANTHROPIC_API_KEY": "sk-ant-..." }
        }
      }
    }

Then in Claude Code, just mention a YouTube URL — Claude will call
extract_video automatically if needed, then use get_session to answer
questions with full repo context.
"""

import json
import sys
from pathlib import Path

# Add project dir to path so imports work when run directly
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

# Load .env from the project directory (picks up ANTHROPIC_API_KEY)
try:
    from dotenv import load_dotenv
    load_dotenv(_HERE / ".env")
except ImportError:
    pass

from mcp.server.fastmcp import FastMCP

from analyzer import describe_frames
from config import (
    CLAUDE_MODEL,
    FRAME_SELECTION_MAX,
    FRAME_SELECTION_MIN_INTERVAL,
    FRAME_SELECTION_MODEL,
    IMAGE_MAX_WIDTH,
    MAX_FRAMES_PER_BATCH,
    TRANSCRIPT_WINDOW,
)
from downloader import download_video, fetch_transcript
from frame_extractor import extract_frames_at_timestamps
from session import (
    frames_dir as session_frames_dir,
    list_sessions as _list_sessions,
    load_session,
    save_session,
    session_dir,
    session_exists,
)

import re

mcp = FastMCP("video-analyzer")


def _extract_video_id(url: str) -> str:
    patterns = [
        r"youtu\.be/([^?&/]+)",
        r"youtube\.com/watch\?v=([^&]+)",
        r"youtube\.com/shorts/([^?&/]+)",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    raise ValueError(f"Cannot extract video ID from: {url}")


@mcp.tool()
def extract_video(url: str) -> str:
    """
    Process a YouTube video: download it, extract key frames, generate
    visual descriptions using Claude Vision, and save a session.

    This runs once per video (~2 minutes). Subsequent calls with the
    same URL return immediately (session already exists).

    Returns: session_id to use with get_session.
    """
    video_id = _extract_video_id(url)

    if session_exists(video_id):
        session = load_session(video_id)
        return json.dumps({
            "status": "already_extracted",
            "session_id": video_id,
            "title": session.get("title", "Unknown"),
            "frame_count": session.get("frame_count", 0),
            "message": f"Session already exists. Use get_session('{video_id}') to access it.",
        })

    s_dir = session_dir(video_id)
    f_dir = session_frames_dir(video_id)

    # Download
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "Unknown")
    except Exception:
        title = "Unknown"

    video_path, _ = download_video(url, s_dir)
    transcript = fetch_transcript(video_id, s_dir)

    # Analyze transcript for key visual moments
    from transcript_selector import select_frames_from_transcript
    selections = select_frames_from_transcript(
        transcript=transcript,
        model=FRAME_SELECTION_MODEL,
        max_frames=FRAME_SELECTION_MAX,
        min_interval=FRAME_SELECTION_MIN_INTERVAL,
    )

    # Extract targeted frames
    frames = extract_frames_at_timestamps(
        video_path=video_path,
        frames_dir=f_dir,
        selections=selections,
        max_width=IMAGE_MAX_WIDTH,
    )

    if not frames:
        return json.dumps({"status": "error", "message": "No frames extracted."})

    # Describe frames
    descriptions = describe_frames(
        frames=frames,
        transcript=transcript,
        model=CLAUDE_MODEL,
        transcript_window=TRANSCRIPT_WINDOW,
        batch_size=MAX_FRAMES_PER_BATCH,
    )

    duration = frames[-1]["timestamp"] if frames else 0.0

    save_session(
        video_id=video_id,
        url=url,
        title=title,
        duration=duration,
        transcript=transcript,
        frame_descriptions=descriptions,
        frames=frames,
    )

    return json.dumps({
        "status": "success",
        "session_id": video_id,
        "title": title,
        "frame_count": len(frames),
        "duration_seconds": duration,
        "message": f"Session ready. Call get_session('{video_id}') to access the content.",
    })


@mcp.tool()
def get_session(session_id: str) -> str:
    """
    Return the full processed content of a video session:
    frame-by-frame visual descriptions and transcript.

    Use the returned content to answer questions about the video.
    You (Claude) provide any codebase/project context from the
    current conversation — no need to pass it here.

    Args:
        session_id: The video ID returned by extract_video or list_sessions.
    """
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        return json.dumps({
            "error": f"No session found for '{session_id}'.",
            "hint": "Run extract_video(url) first.",
        })

    full_transcript = " ".join(seg["text"] for seg in session["transcript"])

    return json.dumps({
        "video_id": session["video_id"],
        "title": session.get("title", "Unknown"),
        "url": session.get("url", ""),
        "duration_seconds": session.get("duration", 0),
        "frame_count": session.get("frame_count", 0),
        "extracted_at": session.get("extracted_at", ""),
        "frame_descriptions": session["frame_descriptions"],
        "transcript": full_transcript[:15000],  # first 15k chars
    })


@mcp.tool()
def list_sessions() -> str:
    """
    List all videos that have been processed and are available to query.
    Returns session IDs, titles, durations, and extraction timestamps.
    """
    sessions = _list_sessions()
    if not sessions:
        return json.dumps({
            "sessions": [],
            "message": "No sessions yet. Run extract_video(url) to process a video.",
        })
    return json.dumps({"sessions": sessions})


if __name__ == "__main__":
    mcp.run()
