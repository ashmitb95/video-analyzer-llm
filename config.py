# Scene change sensitivity: 0.0–1.0
# Lower = more sensitive. Chart screen recordings have subtle changes (lines drawn,
# zones highlighted) — 0.1 captures these without flooding with near-duplicates.
SCENE_THRESHOLD = 0.1

# Minimum seconds between two captured frames.
# Prevents bursting frames during slow zoom/pan animations.
MIN_FRAME_INTERVAL = 3.0

# Seconds of transcript to pull around each frame's timestamp (before + after).
TRANSCRIPT_WINDOW = 15.0

# Claude model for frame description (image batches — cheaper, fast).
CLAUDE_MODEL = "claude-sonnet-4-6"

# Claude model for final strategy synthesis (long code generation — use best available).
SYNTHESIS_MODEL = "claude-opus-4-6"

# How many frames to send per Claude API call.
# Each call = 1 image analysis batch + 1 synthesis call at the end.
MAX_FRAMES_PER_BATCH = 8

# Resize frames to this width (px) before sending to the API.
# Reduces token cost without losing chart readability.
IMAGE_MAX_WIDTH = 1280

# ── Transcript-driven frame selection ──────────────────────────────────────────
# Cheap text-only model to analyze transcript and pick visually important moments.
FRAME_SELECTION_MODEL = "claude-haiku-4-5-20251001"

# Maximum frames to select from transcript analysis.
FRAME_SELECTION_MAX = 25

# Minimum seconds between two transcript-selected frames.
FRAME_SELECTION_MIN_INTERVAL = 5.0
