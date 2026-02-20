"""
Analyzer — Pass 1 only.

Takes extracted frames + transcript and generates visual descriptions
using Claude Vision. Results are stored in the session and queried
later via `ask`.
"""

import base64

import anthropic


def get_transcript_context(transcript: list[dict], timestamp: float, window: float) -> str:
    """Return transcript text for segments within `window` seconds of `timestamp`."""
    segments = [
        seg for seg in transcript
        if seg["start"] >= timestamp - window and seg["start"] <= timestamp + window
    ]
    return " ".join(seg["text"] for seg in segments).strip()


def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def describe_frames(
    frames: list[dict],
    transcript: list[dict],
    model: str,
    transcript_window: float,
    batch_size: int,
) -> list[str]:
    """
    For each batch of frames, ask Claude to describe what's on screen
    and what concept the instructor is explaining.
    Returns a list of description strings (one per batch).
    """
    client = anthropic.Anthropic()
    descriptions = []

    for batch_start in range(0, len(frames), batch_size):
        batch = frames[batch_start : batch_start + batch_size]
        batch_end = min(batch_start + batch_size, len(frames))
        print(f"  Describing frames {batch_start + 1}–{batch_end} of {len(frames)}...")

        content = []

        for frame in batch:
            ts = frame["timestamp"]
            ctx = get_transcript_context(transcript, ts, transcript_window)

            content.append({
                "type": "text",
                "text": (
                    f"\n--- Frame at {ts:.1f}s ---\n"
                    f"Transcript around this moment: \"{ctx}\"\n"
                    f"Screen at {ts:.1f}s:"
                ),
            })
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": encode_image(frame["path"]),
                },
            })

        content.append({
            "type": "text",
            "text": (
                "For each frame above, describe concisely:\n"
                "1. What is visible on screen — chart type, timeframe, price levels, "
                "highlighted zones, drawn lines, annotations, candle patterns\n"
                "2. What concept the instructor is demonstrating based on the transcript\n"
                "3. Any specific entry/exit conditions, confirmations, or invalidations shown\n\n"
                "Be precise — mention exact visual elements like 'red supply zone', "
                "'wick below support closing above', 'break and retest', etc."
            ),
        })

        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=(
                "You are analyzing an instructional screen-recording video. "
                "Charts and annotations only — no webcam. "
                "Extract precise, actionable information from each frame."
            ),
            messages=[{"role": "user", "content": content}],
        )

        descriptions.append(response.content[0].text)

    return descriptions
