"""
video-analyzer v0.2

Commands:
  extract <url>              Process a video once — downloads, extracts frames,
                             generates descriptions, saves a session.
  ask <session_id> <question> Ask anything about a processed video.
  sessions                   List all processed videos.

Examples:
  python main.py extract "https://youtu.be/RnP08K2SAZs"
  python main.py ask RnP08K2SAZs "What is the entry trigger?"
  python main.py ask RnP08K2SAZs "implement this as a BaseStrategy" \\
      --context ~/algo-bot/backend/core/strategy.py \\
      --context ~/algo-bot/backend/core/liquidity_detector.py
  python main.py ask RnP08K2SAZs "how does this relate?" --stdin < my_notes.md
  python main.py sessions
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yt_dlp

from analyzer import describe_frames
from asker import ask as ask_session
from config import (
    CLAUDE_MODEL,
    IMAGE_MAX_WIDTH,
    MAX_FRAMES_PER_BATCH,
    MIN_FRAME_INTERVAL,
    SCENE_THRESHOLD,
    SYNTHESIS_MODEL,
    TRANSCRIPT_WINDOW,
)
from context import load_context
from downloader import download_video, fetch_transcript
from extractor import extract_frames
from session import (
    frames_dir as session_frames_dir,
    list_sessions,
    load_session,
    save_session,
    session_dir,
    session_exists,
)


def extract_video_id(url: str) -> str:
    patterns = [
        r"youtu\.be/([^?&/]+)",
        r"youtube\.com/watch\?v=([^&]+)",
        r"youtube\.com/embed/([^?&/]+)",
        r"youtube\.com/shorts/([^?&/]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Cannot extract video ID from: {url}")


def get_video_title(url: str) -> str:
    """Fetch video title without downloading."""
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("title", "Unknown")
    except Exception:
        return "Unknown"


# ── extract ───────────────────────────────────────────────────────────────────

def cmd_extract(args):
    video_id = extract_video_id(args.url)
    s_dir = session_dir(video_id)
    f_dir = session_frames_dir(video_id)

    print(f"\n{'=' * 44}")
    print(f"  video-analyzer extract")
    print(f"  Video ID : {video_id}")
    print(f"  Session  : {s_dir}")
    print(f"{'=' * 44}\n")

    if session_exists(video_id) and not args.force:
        print(f"Session already exists. Use --force to re-extract.")
        print(f"Run: python main.py ask {video_id} \"your question\"")
        return

    # 1 — Download
    print("[1/3] Downloading video and transcript...")
    title = get_video_title(args.url)
    video_path, _ = download_video(args.url, s_dir)
    transcript = fetch_transcript(video_id, s_dir)

    # 2 — Extract frames
    print("\n[2/3] Extracting key frames...")
    frames = extract_frames(
        video_path=video_path,
        frames_dir=f_dir,
        threshold=args.threshold,
        min_interval=args.interval,
        max_width=IMAGE_MAX_WIDTH,
    )

    if not frames:
        print("ERROR: No frames extracted. Try --threshold 0.05")
        sys.exit(1)

    # 3 — Describe frames (Pass 1)
    print(f"\n[3/3] Describing {len(frames)} frames with {CLAUDE_MODEL}...")
    descriptions = describe_frames(
        frames=frames,
        transcript=transcript,
        model=CLAUDE_MODEL,
        transcript_window=TRANSCRIPT_WINDOW,
        batch_size=MAX_FRAMES_PER_BATCH,
    )

    # Get video duration from frames metadata
    duration = frames[-1]["timestamp"] if frames else 0.0

    # Save session
    session_path = save_session(
        video_id=video_id,
        url=args.url,
        title=title,
        duration=duration,
        transcript=transcript,
        frame_descriptions=descriptions,
        frames=frames,
    )

    print(f"\n{'=' * 44}")
    print(f"  DONE — session saved")
    print(f"  {session_path}")
    print(f"\n  Now ask anything:")
    print(f"  python main.py ask {video_id} \"your question\"")
    print(f"{'=' * 44}\n")


# ── ask ───────────────────────────────────────────────────────────────────────

def cmd_ask(args):
    try:
        session = load_session(args.session_id)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    context = load_context(args.context or [], from_stdin=args.stdin)

    print(f"\nAsking about: {session.get('title', args.session_id)}")
    if context:
        print(f"Context: {len(context)} chars injected")
    print()

    answer = ask_session(
        session=session,
        question=args.question,
        context=context,
        model=SYNTHESIS_MODEL,
    )

    print(answer)

    # Save to session queries log
    queries_path = session_dir(args.session_id) / "queries.jsonl"
    with open(queries_path, "a") as f:
        f.write(json.dumps({
            "question": args.question,
            "context_sources": args.context or [],
            "answer": answer,
        }) + "\n")


# ── sessions ──────────────────────────────────────────────────────────────────

def cmd_sessions(_args):
    sessions = list_sessions()
    if not sessions:
        print("No sessions found. Run: python main.py extract <url>")
        return

    print(f"\n{'─' * 60}")
    print(f"  {'SESSION ID':<20} {'FRAMES':>6}  {'DUR':>5}  TITLE")
    print(f"{'─' * 60}")
    for s in sessions:
        dur = f"{int(s['duration'] // 60)}m{int(s['duration'] % 60):02d}s"
        title = s['title'][:30] + ("…" if len(s['title']) > 30 else "")
        print(f"  {s['session_id']:<20} {s['frames']:>6}  {dur:>5}  {title}")
    print(f"{'─' * 60}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="video-analyzer",
        description="Turn instructional videos into queryable knowledge sessions.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # extract
    p_extract = sub.add_parser("extract", help="Process a video (run once)")
    p_extract.add_argument("url", help="YouTube URL")
    p_extract.add_argument("--threshold", type=float, default=SCENE_THRESHOLD,
                           help=f"Scene change sensitivity 0–1 (default {SCENE_THRESHOLD})")
    p_extract.add_argument("--interval", type=float, default=MIN_FRAME_INTERVAL,
                           help=f"Min seconds between frames (default {MIN_FRAME_INTERVAL})")
    p_extract.add_argument("--force", action="store_true",
                           help="Re-extract even if session already exists")

    # ask
    p_ask = sub.add_parser("ask", help="Ask a question about a processed video")
    p_ask.add_argument("session_id", help="Video ID (from 'sessions' command)")
    p_ask.add_argument("question", help="Your question")
    p_ask.add_argument("--context", action="append", metavar="SOURCE",
                       help="File path, directory, URL, or raw text. Repeatable.")
    p_ask.add_argument("--stdin", action="store_true",
                       help="Read additional context from stdin")

    # sessions
    sub.add_parser("sessions", help="List all processed videos")

    args = parser.parse_args()

    if args.command == "extract":
        cmd_extract(args)
    elif args.command == "ask":
        cmd_ask(args)
    elif args.command == "sessions":
        cmd_sessions(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
