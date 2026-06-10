# screenscribe

**Turn any video into something your agent can act on.**

The best how-to knowledge — live demos, conference talks, tutorials, walkthroughs — is trapped in video: you can watch it, but you can't *use* it. screenscribe pulls what's actually on screen (code, diagrams, steps, data) into structured, queryable knowledge and hands it to an LLM or agent as a first-class input. So "watch this 20-minute tutorial" becomes "here's exactly what it shows — now do it."

**Gemini watches the video and picks the key moments; your agent reasons over the frames and transcript.** Standalone CLI + MCP server (Claude Code, Cursor, Windsurf, any MCP client). Needs only a Gemini key — transcript-only mode needs no key at all.

---

## Why it matters

Transcripts give you the words. The value in technical video is almost always *visual* — the code on screen, the diagram, the UI, the step nobody narrates.

- **Watch → execute.** Point an agent at a tutorial and have it do the thing: *"based on the architecture in this video, refactor my router to match."* The video becomes an input to your build, not a tab you alt-tab to.
- **Surfaces what's shown, not just said** — Gemini watches the video (frames + audio) and pulls out the moments that matter; your agent views the extracted frames directly.
- **Structured + timestamped output** an agent acts on, not prose to re-digest.
- **Agent-native** — an MCP server, so video drops straight into your coding loop.
- **Persistent sessions** — process a video once, query it forever; no re-pasting, no context-limit pain.
- **Source transparency** — `get_session` tells you whether the data is transcript-only, whole-video analysis, or extracted frames.

It's a spectrum: start free with the transcript, add a cheap whole-video analysis, or extract the actual frames when you need the images.

---

## What it does

1. **Selects** the moments that matter — Gemini watches the whole video and returns the timestamps where something visually important is on screen.
2. **Extracts** those moments as PNG frames (ffmpeg), snapped to the settled visual and de-duplicated — images your agent can open and read directly.
3. **Persists** a session at `~/.video-analyzer/{video_id}/` — runs once, cached forever.
4. **Hands off to your agent**, which reasons over the transcript, the whole-video analysis, and the frames — answering, generating, or acting.

---

## How it works

screenscribe is built on **Gemini**, which natively watches the video (frames + audio):

- **Frame selection.** The YouTube URL is handed to Gemini, which returns the precise timestamps where something visually important is on screen. This makes selection accurate and content-agnostic — it works on any video, not just screen recordings. Cheap (~$0.02–0.05 per video at low media resolution) and fast.
- **Whole-video analysis.** Gemini can also return a structured understanding of the entire video — summary, timestamped sections, key moments, on-screen text — in one cheap call.

ffmpeg extracts Gemini's chosen timestamps, snapping each forward to the moment the on-screen visual has settled and de-duplicating near-identical frames via perceptual hashing. The resulting PNGs are for **your agent** to view — there's no separate description model in the loop. A free **transcript layer** runs alongside: fetch a video's transcript instantly and for free, no key required.

### Levels of analysis

Pick the depth you need — lighter to heavier:

| Level | Command / tool | Cost | What you get |
| ----- | -------------- | ---- | ------------ |
| Transcript | `extract --transcript-only` / `extract_transcript` | free, no key | the words, no visuals |
| **Whole-video analysis** | **`analyze` / `analyze_video`** | **~$0.03** | **Gemini watches the entire video → summary, timestamped sections, key moments, on-screen text — no frames, no download** |
| Frames | `extract` / `extract_frames(style="keyframes")` | ~$0.03 | the key frames as PNGs your agent opens and reads |
| Slides | `slides` / `extract_frames(style="slides")` | ~$0.03 | complete, standalone on-screen visuals as PNGs |

`analyze` is usually the sweet spot: whole-video understanding for the price of a transcript. Reach for `extract`/`slides` when you specifically need the frame **images** on disk for your agent to look at.

---

## Architecture

```
screenscribe/
├── pyproject.toml         Package metadata + console scripts (screenscribe, screenscribe-mcp)
├── src/screenscribe/
│   ├── main.py            CLI — extract / analyze / slides / sessions subcommands
│   ├── server.py          MCP server — 6 tools for any MCP client
│   ├── downloader.py      yt-dlp video download + youtube-transcript-api fetch
│   ├── frame_extractor.py ffmpeg extraction + snap-to-stable + perceptual dedup
│   ├── ffmpeg_paths.py    Resolves ffmpeg/ffprobe — system binary, else bundled static-ffmpeg
│   ├── gemini_selector.py Gemini watches the video to pick frames
│   ├── gemini_analyzer.py Gemini whole-video structured analysis (analyze tier)
│   ├── transcript_selector.py Selection helpers (timestamp parsing, validate/filter)
│   ├── session.py         Session persistence at ~/.video-analyzer/
│   └── config.py          Gemini model + selection thresholds
├── tests/
├── .env.example
└── .gitignore
```

**Session storage** (global, outside the repo):

```
~/.video-analyzer/
└── {video_id}/
    ├── session.json    # metadata + transcript + extracted frame paths
    ├── frames/         # extracted PNG key frames (from extract)
    ├── slides/         # standalone slide frames (from slides)
    └── video.*         # downloaded video file
```

---

## Quick start

Requires [`uv`](https://docs.astral.sh/uv/) (or plain `pip`). **No `ffmpeg` install needed** — a static binary is fetched automatically the first time it's required (your system `ffmpeg` is used instead if you have one).

**Try it in 10 seconds, no API key:**

```bash
# Transcript only — fast, free, no key, no video download
uvx screenscribe extract "https://youtu.be/dQw4w9WgXcQ" --transcript-only
uvx screenscribe sessions
```

**Add a Gemini key for the visual tiers.** screenscribe reads it from your shell environment first, so if you already export it, nothing else to do:

```bash
export GEMINI_API_KEY=...   # Gemini — watches the video to pick frames + analyze

uvx screenscribe analyze "https://youtu.be/dQw4w9WgXcQ"   # whole-video analysis (~$0.03)
```

That's the only key needed. Transcript mode needs none; everything visual (`extract`, `slides`, `analyze`) needs `GEMINI_API_KEY`. ([Get one from Google AI Studio](https://aistudio.google.com/apikey).)

> A `.env` file in the working directory also works — handy for project-local keys. Shell-exported keys take precedence over `.env`.

**Add to your agent as an MCP server (one line):**

```bash
claude mcp add screenscribe -- uvx screenscribe-mcp
```

(Other clients: see [Register the MCP server](#register-the-mcp-server) below.)

<details>
<summary><b>Run from source (development)</b></summary>

```bash
git clone git@github.com:ashmitb95/video-analyzer-llm.git
cd video-analyzer-llm
python3 -m venv venv && source venv/bin/activate
pip install -e .

cp .env.example .env   # add your Gemini key, or export it in your shell
screenscribe sessions
pytest
```

</details>

---

## CLI usage

### Extract frames from a video (run once per video)

```bash
# Transcript only — fast, free, no key, no video download
screenscribe extract "https://youtu.be/dQw4w9WgXcQ" --transcript-only

# Frames — downloads the video and extracts Gemini-selected key frames as PNGs
screenscribe extract "https://youtu.be/dQw4w9WgXcQ"
```

(Prefix any command with `uvx ` to run without installing, e.g. `uvx screenscribe extract …`.)

Options:

```
--transcript-only   Fetch transcript only — no key, no video download or frames
--max-frames 25     Max frames Gemini selects (default 25)
--focus "..."       Focus selection on specific content (e.g. "architecture diagrams")
--time-range 5:00-15:00   Restrict to a portion (seconds or MM:SS)
--timestamps 5:30,10:00   Extract at exact timestamps, bypass AI selection (no key needed)
--force             Re-extract even if session already exists
```

### Analyze a whole video (cheap, no frames)

```bash
screenscribe analyze "https://youtu.be/dQw4w9WgXcQ"
```

Gemini watches the entire video and produces a structured analysis — summary, timestamped sections, key moments, and on-screen text — saved to `~/.video-analyzer/{id}/gemini_analysis.json`. No download or frame extraction. Options: `--focus`, `--time-range`, `--force`.

### Extract presentation slides

```bash
screenscribe slides "https://youtu.be/dQw4w9WgXcQ"
```

Identifies complete, self-contained visuals — diagrams, scenes, charts, code, summaries — that work as standalone images, and extracts them into `~/.video-analyzer/{id}/slides/`.

Options:

```
--max-slides 15     Max slides to extract (default 15)
--focus / --time-range / --timestamps   (same as extract)
--force             Re-extract even if slides already exist
```

### List all sessions

```bash
screenscribe sessions
```

---

## MCP server

The MCP server exposes screenscribe as a set of tools that any MCP-compatible client can call. The server handles video knowledge; **the client (your agent) does the reasoning** — including viewing the extracted frame images.

Works with: Claude Code, Cursor, Windsurf, Continue, custom MCP agents, or any client that speaks the [Model Context Protocol](https://modelcontextprotocol.io).

### Tools exposed

| Tool                      | Description                                                                                                  |
| ------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `extract_transcript(url)` | Fetch transcript only — fast, free, no key. Default for most questions.                                      |
| `analyze_video(url)`      | Gemini watches the whole video → structured analysis (summary, sections, key moments). Cheap; no frames.     |
| `extract_frames(url, style)` | Gemini picks moments, ffmpeg extracts PNGs the agent opens and reads. `style="keyframes"` (default) or `"slides"`. |
| `get_video_analysis(id)`  | Read Gemini's whole-video analysis for a session.                                                            |
| `get_session(session_id)` | Return session content (transcript, Gemini analysis, extracted frame paths) with `analysis_source` metadata. |
| `list_sessions()`         | List all processed videos.                                                                                   |

The client picks the right tool based on context. For most questions `extract_transcript` or `analyze_video` is sufficient; `extract_frames` when it needs to *see* what's on screen.

### Register the MCP server

No paths, no venv, no JSON surgery — `uvx` runs the published package on demand.

**Claude Code** (one line):

```bash
claude mcp add screenscribe -- uvx screenscribe-mcp
```

**Cursor / Windsurf / Continue** (`.cursor/mcp.json` or your client's MCP config):

```json
{
  "mcpServers": {
    "screenscribe": {
      "command": "uvx",
      "args": ["screenscribe-mcp"]
    }
  }
}
```

Pass the key through if your client doesn't inherit your shell environment — add an `"env"` block:

```json
{
  "mcpServers": {
    "screenscribe": {
      "command": "uvx",
      "args": ["screenscribe-mcp"],
      "env": { "GEMINI_API_KEY": "..." }
    }
  }
}
```

The server reads `GEMINI_API_KEY` from the environment (or a `.env` in the working directory). Restart your client after updating the config.

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

1. Call `extract_transcript(url)`, `analyze_video(url)`, or `extract_frames(url)` depending on what's needed — cached after the first run.
2. Call `get_session(id)` — loads transcript, any Gemini analysis, and the extracted frame paths, with `analysis_source` metadata indicating what data is available.
3. Open the frame images and read your project files for context.
4. Answer (or generate), citing whether it drew from transcript alone, whole-video analysis, or extracted frames.

---

## Configuration (`src/screenscribe/config.py`)

| Setting                        | Default             | Description                                                   |
| ------------------------------ | ------------------- | ------------------------------------------------------------- |
| `IMAGE_MAX_WIDTH`              | `1280px`            | Frames resized to this width before saving.                   |
| `FRAME_SELECTION_MAX`          | `25`                | Max frames Gemini selects.                                    |
| `FRAME_SELECTION_MIN_INTERVAL` | `5.0s`              | Min gap between selected frames.                              |
| `SLIDE_SELECTION_MAX`          | `15`                | Max slides to extract.                                        |
| `SLIDE_SELECTION_MIN_INTERVAL` | `10.0s`             | Min gap between slides (wider than frames for diversity).     |
| `GEMINI_MODEL`                 | `gemini-3.5-flash`  | Gemini model that watches the video.                          |
| `GEMINI_MEDIA_RESOLUTION_LOW`  | `True`              | Low-res video sampling (~100 tok/s) — cheaper; set `False` for finer visual detail. |
| `MAX_INLINE_TRANSCRIPT_CHARS`  | `100000`            | Max transcript chars `get_session` returns inline before pointing to the file instead. `None` = unlimited. |

---

## API keys

screenscribe uses a single key:

- **`GEMINI_API_KEY` (Gemini)** — watches the video to select frames (`extract`, `slides`) and produce whole-video analysis (`analyze`). Get one from [Google AI Studio](https://aistudio.google.com/apikey).

These need **no** key and make no API calls:

- `extract --transcript-only` / `extract_transcript` — fetches the transcript from YouTube only
- `extract --timestamps ...` — extract at exact timestamps, bypassing AI selection
- `get_session` / `list_sessions` — read from disk

Reasoning over the result — answering questions, generating code — is done by **your agent**, not by screenscribe, so no separate model key is required.

---

## Notes

- Works on **any kind of video** — selection is content-agnostic. Use `--focus` (or a tool's `focus`) to steer toward a specific subject.
- `get_session` returns the **full transcript** (no silent truncation). For very long videos it returns a preview plus a `transcript_path` to the on-disk file and a `transcript_truncated` flag, rather than dropping data silently.
- Sessions are **machine-local** (`~/.video-analyzer/`). Installing on a new machine means re-running `extract` once per video.
- `youtube-transcript-api` v1.2.4+ uses an instance-based API: `YouTubeTranscriptApi().fetch(video_id)`. If you see `AttributeError: get_transcript`, you're on an old version — `pip install -U youtube-transcript-api`.
