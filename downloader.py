import json
from pathlib import Path

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

_ytt = YouTubeTranscriptApi()


def download_video(url: str, output_dir: Path) -> tuple[Path, str]:
    """Download video to output_dir. Returns (video_path, video_id)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "quiet": False,
        "no_warnings": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info["id"]

    # yt-dlp may merge into .mkv if mp4 isn't available — find whatever was saved
    candidates = list(output_dir.glob(f"{video_id}.*"))
    video_path = candidates[0] if candidates else output_dir / f"{video_id}.mp4"

    print(f"  Video saved: {video_path}")
    return video_path, video_id


def fetch_transcript(video_id: str, output_dir: Path) -> list[dict]:
    """
    Fetch the YouTube transcript for video_id.
    Each entry: {'text': str, 'start': float, 'duration': float}
    """
    fetched = _ytt.fetch(video_id)
    transcript = [{"text": s.text, "start": s.start, "duration": s.duration} for s in fetched]

    transcript_path = output_dir / "transcript.json"
    transcript_path.write_text(json.dumps(transcript, indent=2))

    print(f"  Transcript saved: {len(transcript)} segments → {transcript_path}")
    return transcript
