# video-analyzer

Turn YouTube videos into queryable knowledge sessions — extract transcripts, key frames, or presentation slides, then ask anything about them with your own files as context.

Works as a standalone CLI and as an MCP server compatible with any MCP client (Claude Code, Cursor, Windsurf, Continue, custom agents, etc.).

---

## Why not just paste a transcript into an LLM?

You can — and for some videos that's fine. video-analyzer starts there (transcript-only mode is free and instant) but goes further when you need it:

- **Visual context matters.** Transcripts say "look at this chart" or "notice the pattern here" — without the actual frame, an LLM is guessing. video-analyzer extracts the exact frames being referenced and describes them with a vision model, so nothing is lost.
- **Slide extraction.** Pull out the key completed visuals (diagrams, code, summaries) as standalone images you can reference or share — something a transcript alone can never give you.
- **Persistent sessions.** Process a video once, query it forever. No re-pasting, no token waste, no hitting context limits on long videos.
- **Context injection.** Ask questions with your own project files injected alongside the video knowledge — "implement what this video describes, using my existing interfaces." A raw transcript paste can't do that cleanly.
- **Source transparency.** Every answer tells you whether it's based on transcript alone or transcript + visual analysis, so you know what you're getting.

The tool gives you a spectrum: start with transcript-only (fast, free), upgrade to visual analysis when the content demands it.

---

## What it does

1. **Extracts** a video's transcript, key frames, or presentation slides — choose the level of analysis you need
2. **Describes** each frame with a vision-capable LLM, cross-referenced against the transcript
3. **Persists** a session at `~/.video-analyzer/{video_id}/` — runs once, cached forever
4. **Answers** any free-form question about the video, optionally with your own files as context

---

## Architecture

```
video-analyzer/
├── main.py                CLI — extract / slides / ask / sessions subcommands
├── server.py              MCP server — 5 tools for any MCP client
├── analyzer.py            Vision LLM describes frames in batches
├── asker.py               LLM answers questions with session + context
├── downloader.py          yt-dlp video download + youtube-transcript-api fetch
├── frame_extractor.py     ffmpeg scene-change detection + targeted extraction
├── transcript_selector.py Transcript analysis for frame/slide selection
├── session.py             Session persistence at ~/.video-analyzer/
├── context.py             Universal context loader (files, dirs, URLs, stdin)
├── config.py              Model names, thresholds, batch sizes
├── requirements.txt
├── .env.example
└── .gitignore
```

**Session storage** (global, outside the repo):

```
~/.video-analyzer/
└── {video_id}/
    ├── session.json    # metadata + transcript + frame descriptions
    ├── frames/         # extracted PNG frames (from extract)
    ├── slides/         # presentation-quality frames (from slides)
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

Two modes, from lightest to heaviest:

```bash
source venv/bin/activate

# Transcript only — fast, free, no video download
python main.py extract "https://youtu.be/dQw4w9WgXcQ" --transcript-only

# Full extraction — downloads video, extracts frames, describes with Vision
python main.py extract "https://youtu.be/dQw4w9WgXcQ"
```

Options:

```
--transcript-only   Fetch transcript only — no video download or frame analysis
--threshold 0.1     Scene change sensitivity 0–1 (default 0.1, lower = more frames)
--interval 3.0      Min seconds between frames (default 3.0)
--max-frames 25     Max frames from transcript analysis (default 25)
--force             Re-extract even if session already exists
--resume            Resume from last completed step
```

### Extract presentation slides

```bash
python main.py slides "https://youtu.be/dQw4w9WgXcQ"
```

Identifies complete diagrams, charts, code snippets, and summaries that would work as standalone slides. Extracts them into `~/.video-analyzer/{id}/slides/`.

Options:

```
--max-slides 15     Max slides to extract (default 15)
--force             Re-extract even if slides already exist
```

### Ask anything about a video

```bash
python main.py ask <session_id> "What are the main concepts covered?"

# Inject your own project files as context:
python main.py ask <session_id> "Implement the pattern from the video" \
    --context ./src/app.py \
    --context ./src/utils/

# Pipe in notes via stdin:
python main.py ask <session_id> "Compare with my notes" --stdin < notes.md
```

`--context` accepts: file paths, directory paths, HTTP/HTTPS URLs, or raw text strings. Repeatable.

### List all sessions

```bash
python main.py sessions
```

---

## MCP server

The MCP server exposes video-analyzer as a set of tools that any MCP-compatible client can call. The server handles video knowledge; the client provides conversation context.

Works with: Claude Code, Cursor, Windsurf, Continue, custom MCP agents, or any client that speaks the [Model Context Protocol](https://modelcontextprotocol.io).

### Tools exposed

| Tool                      | Description                                                                                                  |
| ------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `extract_transcript(url)` | Fetch transcript only — fast, free, no API cost. Default for most questions.                                 |
| `extract_video(url)`      | Full visual processing — download, extract frames, describe with Vision. Use when visual analysis is needed. |
| `extract_slides(url)`     | Extract presentation-quality slide frames. Returns paths to PNGs on disk.                                    |
| `get_session(session_id)` | Return session content with `analysis_source` metadata (transcript-only vs transcript+video).                |
| `list_sessions()`         | List all processed videos.                                                                                   |

The client picks the right tool based on context. For most questions `extract_transcript` is sufficient; `extract_video` when visual analysis is needed; `extract_slides` for screenshots or a deck.

### Register the MCP server

Add the server to your MCP client's config. Examples for common clients:

**Claude Code** (`~/.claude.json`):

```json
"mcpServers": {
  "video-analyzer": {
    "command": "/path/to/video-analyzer-llm/venv/bin/python",
    "args": ["/path/to/video-analyzer-llm/server.py"]
  }
}
```

**Cursor** (`.cursor/mcp.json` in your project):

```json
{
  "mcpServers": {
    "video-analyzer": {
      "command": "/path/to/video-analyzer-llm/venv/bin/python",
      "args": ["/path/to/video-analyzer-llm/server.py"]
    }
  }
}
```

**WSL** (MCP client running on Windows, server on Linux):

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

The server loads `ANTHROPIC_API_KEY` from the `.env` file automatically. Restart your client after updating the config.

### Example usage

Open your MCP client inside any project, then ask naturally:

```
"Summarise the key points from https://youtu.be/dQw4w9WgXcQ"
```

```
"Extract slides from https://youtu.be/dQw4w9WgXcQ and list what each one covers"
```

```
"Based on the architecture explained in https://youtu.be/dQw4w9WgXcQ,
 refactor my src/api/router.py to follow that pattern"
```

The client will:

1. Call `extract_transcript(url)` or `extract_video(url)` depending on what's needed — cached after the first run
2. Call `get_session(id)` — loads transcript (+ frame descriptions if available), with `analysis_source` metadata indicating what data the answer is based on
3. Read your project files for context
4. Answer your question, citing whether it drew from transcript alone or transcript + visual analysis

---

## Configuration (`config.py`)

| Setting                        | Default             | Description                                                   |
| ------------------------------ | ------------------- | ------------------------------------------------------------- |
| `SCENE_THRESHOLD`              | `0.1`               | Scene change sensitivity. Lower = more frames captured.       |
| `MIN_FRAME_INTERVAL`           | `3.0s`              | Minimum gap between frames.                                   |
| `TRANSCRIPT_WINDOW`            | `15.0s`             | Transcript context pulled around each frame (±15s).           |
| `CLAUDE_MODEL`                 | `claude-sonnet-4-6` | Model for frame descriptions (vision).                        |
| `SYNTHESIS_MODEL`              | `claude-opus-4-6`   | Model for `ask` synthesis (8192 tokens).                      |
| `FRAME_SELECTION_MODEL`        | `claude-haiku-4-5`  | Cheap text model for transcript-driven frame/slide selection. |
| `FRAME_SELECTION_MAX`          | `25`                | Max frames from transcript analysis.                          |
| `SLIDE_SELECTION_MAX`          | `15`                | Max slides to extract.                                        |
| `SLIDE_SELECTION_MIN_INTERVAL` | `10.0s`             | Min gap between slides (wider than frames for diversity).     |
| `MAX_FRAMES_PER_BATCH`         | `8`                 | Frames per vision API call.                                   |
| `IMAGE_MAX_WIDTH`              | `1280px`            | Frames resized to this width before API call.                 |

Models are configurable in `config.py`. The defaults use Anthropic's Claude, but can be swapped for any provider supported by the Anthropic SDK or a compatible wrapper.

---

## API key

The `ANTHROPIC_API_KEY` is used by:

- `extract` (full mode) — vision model for frame descriptions
- `slides` — one cheap text model call for transcript analysis
- `ask` — LLM for answering questions

These commands make **no** API calls and need no key:

- `extract --transcript-only` — fetches from YouTube only
- `get_session` / `list_sessions` — reads from disk

---

## Notes

- Sessions are **machine-local** (`~/.video-analyzer/`). Cloning the repo on a new machine means re-running `extract` once per video.
- The `output/` directory in the project root is legacy and ignored by git. All current session data lives at `~/.video-analyzer/`.
- `youtube-transcript-api` v1.2.4+ uses an instance-based API: `YouTubeTranscriptApi().fetch(video_id)`. If you see `AttributeError: get_transcript`, you're on an old version — `pip install -U youtube-transcript-api`.
