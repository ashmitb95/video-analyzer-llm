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


def _format_chapters(chapters: list[dict]) -> str:
    """Format YouTube chapters for the prompt."""
    if not chapters:
        return ""
    lines = []
    for ch in chapters:
        t = ch.get("start_time", 0)
        mm, ss = int(t // 60), int(t % 60)
        end = ch.get("end_time", 0)
        emm, ess = int(end // 60), int(end % 60)
        lines.append(f"  [{mm}:{ss:02d} - {emm}:{ess:02d}] {ch.get('title', '')}")
    return "\n".join(lines)


def _call_claude_with_retry(client, model, system_prompt, user_prompt):
    """Call Claude with exponential backoff retry on transient errors."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response
        except _RETRYABLE as e:
            if attempt == MAX_RETRIES:
                raise
            delay = INITIAL_BACKOFF * (2 ** (attempt - 1))
            print(f"    \u23f3 {type(e).__name__} — retrying in {delay:.0f}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(delay)


def _validate_and_filter(raw_selections, video_duration, max_items, min_interval):
    """Validate timestamps, sort, apply interval filter, and cap at max."""
    selections = []
    for item in raw_selections:
        ts = float(item.get("timestamp", 0))
        reason = str(item.get("reason", ""))
        if 0 <= ts <= video_duration:
            selections.append({"timestamp": ts, "reason": reason})

    selections.sort(key=lambda x: x["timestamp"])

    timestamps = [s["timestamp"] for s in selections]
    filtered_ts = set(apply_min_interval(timestamps, min_interval))
    selections = [s for s in selections if s["timestamp"] in filtered_ts]

    if len(selections) > max_items:
        selections = selections[:max_items]
        selections.sort(key=lambda x: x["timestamp"])

    return selections


def select_frames_from_transcript(
    transcript: list[dict],
    model: str,
    max_frames: int = 25,
    min_interval: float = 5.0,
    chapters: list[dict] | None = None,
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

    chapters_section = ""
    if chapters:
        chapters_section = (
            f"\n\nThe video has the following chapters:\n"
            f"{_format_chapters(chapters)}\n"
            f"IMPORTANT: Always capture a frame near the END of each chapter — "
            f"this is when the instructor's final annotation, completed zone, or "
            f"summary for that section is fully visible on screen.\n"
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
        f"while describing something on screen\n"
        f"- **A topic or section is wrapping up** — the completed chart/diagram/zone is "
        f"fully drawn and the instructor is summarizing or transitioning to the next topic. "
        f"These end-of-section frames capture the final, complete visual.\n"
        f"{chapters_section}\n"
        f"Return ONLY a JSON array, ordered by importance (most critical first):\n"
        f'[{{"timestamp": <seconds>, "reason": "<brief description>"}}]\n\n'
        f"TRANSCRIPT:\n{formatted}"
    )

    response = _call_claude_with_retry(client, model, system_prompt, user_prompt)
    raw_selections = _parse_json_response(response.content[0].text)
    return _validate_and_filter(raw_selections, video_duration, max_frames, min_interval)


def select_slides_from_transcript(
    transcript: list[dict],
    model: str,
    max_slides: int = 15,
    min_interval: float = 10.0,
    chapters: list[dict] | None = None,
) -> list[dict]:
    """
    Analyze transcript with Claude to identify timestamps where the screen
    shows a complete visual that would work as a standalone presentation slide.

    Returns: [{"timestamp": float, "reason": str}, ...]
    """
    if not transcript:
        return []

    video_duration = transcript[-1]["start"] + transcript[-1].get("duration", 0)
    formatted = _format_transcript(transcript)

    client = anthropic.Anthropic()

    system_prompt = (
        "You are analyzing the transcript of an instructional video to identify "
        "moments where the screen shows a COMPLETE visual that would work as a "
        "standalone slide in a presentation deck. The video shows charts, diagrams, "
        "code, and annotations."
    )

    chapters_section = ""
    if chapters:
        chapters_section = (
            f"\n\nThe video has the following chapters:\n"
            f"{_format_chapters(chapters)}\n"
            f"IMPORTANT: Capture a frame near the END of each chapter — this is "
            f"when the completed visual for that section is fully visible.\n"
        )

    user_prompt = (
        f"Here is the transcript of a {int(video_duration)}-second instructional video. "
        f"Identify up to {max_slides} timestamps where the screen shows a COMPLETE "
        f"visual that would make a good standalone presentation slide.\n\n"
        f"Select moments where:\n"
        f"- A diagram, chart, or illustration is FULLY DRAWN and COMPLETE (not "
        f"mid-animation or mid-drawing). Prefer the moment just AFTER the instructor "
        f"finishes building a visual, not while they are still adding to it.\n"
        f"- Text, labels, or titles are clearly visible and would be readable as a slide.\n"
        f"- A key concept, definition, formula, or summary is displayed on screen.\n"
        f"- A code snippet or configuration is fully shown (not partially scrolled).\n"
        f"- A comparison table, list of steps, or structured information is complete.\n"
        f"- A section title or topic header is shown (good for slide deck dividers).\n\n"
        f"AVOID selecting moments where:\n"
        f"- The instructor is mid-drawing or mid-typing (visual is incomplete).\n"
        f"- The screen is transitioning between views.\n"
        f"- The content is a near-duplicate of an already-selected slide.\n"
        f"- The visual is too zoomed-in to be self-explanatory without narration.\n\n"
        f"For each selection, the 'reason' should describe what the slide would "
        f"communicate as a standalone visual (e.g. 'Complete architecture diagram "
        f"showing 3-tier system' not 'instructor is drawing a diagram').\n\n"
        f"Prioritize DIVERSITY of content — a good slide deck covers all major topics.\n"
        f"{chapters_section}\n"
        f"Return ONLY a JSON array, ordered by importance (most critical first):\n"
        f'[{{"timestamp": <seconds>, "reason": "<brief description>"}}]\n\n'
        f"TRANSCRIPT:\n{formatted}"
    )

    response = _call_claude_with_retry(client, model, system_prompt, user_prompt)
    raw_selections = _parse_json_response(response.content[0].text)
    return _validate_and_filter(raw_selections, video_duration, max_slides, min_interval)
