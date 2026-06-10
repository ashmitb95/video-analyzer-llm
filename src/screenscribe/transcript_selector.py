"""
Selection helpers: timestamp parsing, time-range parsing, and the
importance-aware validate/filter that turns raw timestamp picks into the final
frame/slide selection. Shared by the Gemini selector and analyzer.
"""

import re


def _parse_timestamp(s: str) -> float:
    """Parse a timestamp string like '5:30', '330', or '1:05:30' into seconds."""
    s = s.strip()
    parts = s.split(":")
    if len(parts) == 1:
        return float(parts[0])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    raise ValueError(f"Invalid timestamp format: {s}")


def _parse_time_range(time_range: str) -> tuple[float, float] | None:
    """Parse 'START-END' string into (start_seconds, end_seconds). Returns None if empty."""
    if not time_range or not time_range.strip():
        return None
    m = re.match(r"^(.+?)\s*-\s*(\d.*)$", time_range.strip())
    if not m:
        raise ValueError(f"Invalid time range format: {time_range}. Expected 'START-END' (e.g. '5:00-15:00' or '300-900').")
    start = _parse_timestamp(m.group(1))
    end = _parse_timestamp(m.group(2))
    if end <= start:
        raise ValueError(f"Time range end ({end}s) must be after start ({start}s).")
    return (start, end)


def _parse_timestamps_list(timestamps_str: str) -> list[dict]:
    """Parse comma-separated timestamps into a selections list."""
    if not timestamps_str or not timestamps_str.strip():
        return []
    parts = [p.strip() for p in timestamps_str.split(",") if p.strip()]
    return [
        {"timestamp": _parse_timestamp(p), "reason": "user-specified timestamp"}
        for p in parts
    ]


def _validate_and_filter(raw_selections, video_duration, max_items, min_interval, time_range=None):
    """
    Turn raw timestamp picks into the final selection.

    raw_selections arrives in IMPORTANCE order (the selector returns the most
    critical moments first). We greedily accept picks in that order, skipping any
    that fall within min_interval of an already-accepted pick — which both
    enforces spacing and collapses exact/near-duplicate timestamps — and stop once
    we have max_items. The kept picks are then sorted by time for chronological
    output. This keeps the MOST IMPORTANT moments when capping, rather than just
    the earliest-in-time ones.
    """
    range_start = time_range[0] if time_range else 0
    range_end = time_range[1] if time_range else video_duration

    accepted = []
    for item in raw_selections:
        raw_ts = item.get("timestamp")
        if raw_ts is None:
            continue  # skip picks with no timestamp
        try:
            ts = float(raw_ts)
        except (TypeError, ValueError):
            continue  # skip malformed picks rather than crashing the run
        reason = str(item.get("reason", ""))
        if not (range_start <= ts <= range_end):
            continue
        if any(abs(ts - a["timestamp"]) < min_interval for a in accepted):
            continue  # too close to a higher-priority pick (or an exact duplicate)
        accepted.append({"timestamp": ts, "reason": reason})
        if len(accepted) >= max_items:
            break

    accepted.sort(key=lambda x: x["timestamp"])
    return accepted
