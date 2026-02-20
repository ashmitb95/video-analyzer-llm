"""
Transcript-driven frame selection.

Analyzes a video transcript with Claude (text-only, cheap) to identify
timestamps where the instructor is showing something visually important.
Returns targeted timestamps instead of blind time-based sampling.
"""

import json
import re
import time

import anthropic

from frame_extractor import apply_min_interval

MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0

_RETRYABLE = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


def _format_transcript(transcript: list[dict]) -> str:
    """Format transcript segments as [MM:SS] text for the prompt."""
    lines = []
    for seg in transcript:
        t = seg["start"]
        mm, ss = int(t // 60), int(t % 60)
        lines.append(f"[{mm}:{ss:02d}] {seg['text']}")
    return "\n".join(lines)


def _parse_json_response(text: str) -> list[dict]:
    """Extract JSON array from Claude's response, handling markdown fences."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = cleaned.strip()

    # Find the JSON array in the response
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array found in response: {text[:200]}")

    return json.loads(match.group(0))


def select_frames_from_transcript(
    transcript: list[dict],
    model: str,
    max_frames: int = 25,
    min_interval: float = 5.0,
) -> list[dict]:
    """
    Analyze transcript with Claude to identify timestamps where a screenshot
    would be valuable for understanding the visual content.

    Returns: [{"timestamp": float, "reason": str}, ...]
    """
    if not transcript:
        return []

    video_duration = transcript[-1]["start"] + transcript[-1].get("duration", 0)
    formatted = _format_transcript(transcript)

    client = anthropic.Anthropic()

    system_prompt = (
        "You are analyzing the transcript of an instructional screen-recording video "
        "to identify moments where a screenshot would help understand the visual content. "
        "The video shows charts, diagrams, and annotations — no webcam."
    )

    user_prompt = (
        f"Here is the transcript of a {int(video_duration)}-second instructional video. "
        f"Identify up to {max_frames} timestamps where the instructor is showing something "
        f"visually important that would require a screenshot to understand.\n\n"
        f"Focus on moments where:\n"
        f"- A new chart, diagram, or example appears on screen\n"
        f"- The instructor points to, circles, or highlights specific visual elements\n"
        f"- Key patterns, zones, levels, or formations are being described\n"
        f"- Step-by-step visual walkthroughs transition to a new step\n"
        f"- Before/after comparisons are shown\n"
        f"- The instructor uses words like 'here', 'this', 'look', 'see', 'notice' "
        f"while describing something on screen\n\n"
        f"Return ONLY a JSON array, ordered by importance (most critical first):\n"
        f'[{{"timestamp": <seconds>, "reason": "<brief description>"}}]\n\n'
        f"TRANSCRIPT:\n{formatted}"
    )

    # Call with retry
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            break
        except _RETRYABLE as e:
            if attempt == MAX_RETRIES:
                raise
            delay = INITIAL_BACKOFF * (2 ** (attempt - 1))
            print(f"    ⏳ {type(e).__name__} — retrying in {delay:.0f}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(delay)

    raw_selections = _parse_json_response(response.content[0].text)

    # Validate and normalize
    selections = []
    for item in raw_selections:
        ts = float(item.get("timestamp", 0))
        reason = str(item.get("reason", ""))
        if 0 <= ts <= video_duration:
            selections.append({"timestamp": ts, "reason": reason})

    # Sort by timestamp for interval filtering
    selections.sort(key=lambda x: x["timestamp"])

    # Apply min interval filter
    timestamps = [s["timestamp"] for s in selections]
    filtered_ts = set(apply_min_interval(timestamps, min_interval))
    selections = [s for s in selections if s["timestamp"] in filtered_ts]

    # Cap at max_frames (keep original importance ordering from Claude)
    if len(selections) > max_frames:
        selections = selections[:max_frames]
        selections.sort(key=lambda x: x["timestamp"])

    return selections
