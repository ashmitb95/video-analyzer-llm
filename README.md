# video-analyzer

Turn instructional YouTube videos into queryable knowledge sessions — then ask anything about them, with your own codebase injected as context.

Built to work as both a standalone CLI and an MCP server for Claude Code.

---

## What it does

1. **Extracts** key frames from a video using scene-change detection + fallback time-sampling
2. **Describes** each frame with Claude Vision (Sonnet), cross-referenced against the transcript
3. **Persists** a session at `~/.video-analyzer/{video_id}/` — runs once, cached forever
4. **Answers** any free-form question about the video, optionally with your own files as context

---

## Architecture

```
video-analyzer/
├── main.py          CLI — extract / ask / sessions subcommands
├── server.py        MCP server — exposes 3 tools to Claude Code
├── analyzer.py      Pass 1: Claude Vision describes frames in batches
├── asker.py         Pass 2: Claude Opus answers questions with session + context
├── downloader.py    yt-dlp video download + youtube-transcript-api fetch
├── extractor.py     ffmpeg scene-change detection + fallback time sampling
├── session.py       Session persistence at ~/.video-analyzer/
├── context.py       Universal context loader (files, dirs, URLs, stdin)
├── config.py        Model names, thresholds, batch sizes
├── requirements.txt
├── .env.example
└── .gitignore
```

**Session storage** (global, outside the repo):
```
~/.video-analyzer/
└── {video_id}/
    ├── session.json    # metadata + transcript + frame descriptions
    ├── frames/         # extracted PNG frames
    └── video.*         # downloaded video file
```

---

## Prerequisites

- Python 3.11+
- `ffmpeg`

**Linux/WSL:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

---

## Setup

```bash
git clone git@github.com:ashmitb95/video-analyzer-llm.git
cd video-analyzer-llm

python3 -m venv venv
source venv/bin/activate          # Windows WSL: same command
pip install -r requirements.txt

cp .env.example .env
# Edit .env — add your Anthropic API key:
# ANTHROPIC_API_KEY=sk-ant-...
```

---

## CLI usage

### Extract a video (run once per video)

```bash
source venv/bin/activate
python main.py extract "https://youtu.be/RnP08K2SAZs"
```

Options:
```
--threshold 0.1     Scene change sensitivity 0–1 (default 0.1, lower = more frames)
--interval 3.0      Min seconds between frames (default 3.0)
--force             Re-extract even if session already exists
```

### Ask anything about a video

```bash
python main.py ask <session_id> "What is the entry trigger?"

# Inject your own codebase files as context:
python main.py ask <session_id> "Implement this as a BaseStrategy subclass" \
    --context ../algo-bot/backend/core/strategy.py \
    --context ../algo-bot/backend/core/liquidity_detector.py

# Inject a whole directory:
python main.py ask <session_id> "How does this relate?" \
    --context ../algo-bot/backend/core/

# Pipe in notes via stdin:
python main.py ask <session_id> "Summarise vs my notes" --stdin < my_notes.md
```

`--context` accepts: file paths, directory paths, HTTP/HTTPS URLs, or raw text strings. Repeatable.

### List all sessions

```bash
python main.py sessions
```

---

## MCP server (Claude Code integration)

The MCP server lets Claude Code call video-analyzer tools directly — no CLI needed. Claude Code provides repo context automatically from the conversation; the server provides the video knowledge.

### Tools exposed

| Tool | Description |
|---|---|
| `extract_video(url)` | Download, extract frames, describe, save session. Returns immediately if already cached. |
| `get_session(session_id)` | Return frame descriptions + transcript for a session. |
| `list_sessions()` | List all processed videos. |

### Register in Claude Code

Edit `~/.claude.json` and add a `mcpServers` key:

**Linux / WSL (Claude Code running on Windows):**
```json
"mcpServers": {
  "video-analyzer": {
    "command": "wsl",
    "args": [
      "-d", "Ubuntu-24.04",
      "/home/<you>/projects/video-analyzer-llm/venv/bin/python",
      "/home/<you>/projects/video-analyzer-llm/server.py"
    ]
  }
}
```

**macOS / native Linux:**
```json
"mcpServers": {
  "video-analyzer": {
    "command": "/Users/<you>/projects/video-analyzer-llm/venv/bin/python",
    "args": ["/Users/<you>/projects/video-analyzer-llm/server.py"]
  }
}
```

The server loads `ANTHROPIC_API_KEY` automatically from the `.env` file — no extra env config needed.

Restart Claude Code after editing `~/.claude.json`.

### Using it from Claude Code (example)

Open Claude Code inside any project (e.g. `algo-bot`), then just talk:

```
"Implement the liquidity sweep entry logic from https://youtu.be/RnP08K2SAZs
 as a new BaseStrategy subclass. Use the existing LiquidityDetector and TradeSignal."
```

Claude Code will:
1. Call `extract_video(url)` → cached after the first run
2. Call `get_session(id)` → loads frame descriptions + transcript
3. Read your repo files for context
4. Synthesise a concrete implementation against your exact interfaces

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `SCENE_THRESHOLD` | `0.1` | Scene change sensitivity. Lower = more frames captured. |
| `MIN_FRAME_INTERVAL` | `3.0s` | Minimum gap between frames. |
| `TRANSCRIPT_WINDOW` | `15.0s` | Transcript context pulled around each frame (±15s). |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Model for frame descriptions (vision). |
| `SYNTHESIS_MODEL` | `claude-opus-4-6` | Model for `ask` synthesis (8192 tokens). |
| `MAX_FRAMES_PER_BATCH` | `8` | Frames per Claude Vision API call. |
| `IMAGE_MAX_WIDTH` | `1280px` | Frames resized to this width before API call. |

---

## API key

The `ANTHROPIC_API_KEY` is only used during `extract_video` / `python main.py extract` (the frame description step calls Claude Vision). `get_session` and `list_sessions` read from disk — no API calls, no key needed.

Once a video is extracted and cached, it costs nothing to query.

---

## Notes

- Sessions are **machine-local** (`~/.video-analyzer/`). Cloning the repo on a new machine means re-running `extract` once per video (~2 min).
- The `output/` directory in the project root is legacy and ignored by git. All current session data lives at `~/.video-analyzer/`.
- `youtube-transcript-api` v1.2.4+ uses an instance-based API: `YouTubeTranscriptApi().fetch(video_id)`. If you see `AttributeError: get_transcript`, you're on an old version — `pip install -U youtube-transcript-api`.
