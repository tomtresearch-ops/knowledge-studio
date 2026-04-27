# Knowledge Studio (YouTube Intelligence System)

A personal intelligence wire service that processes YouTube videos, articles, newsletters, and reports - extracts transcripts, generates AI summaries, and organizes content into a searchable knowledge base.

## How Tom Uses This

**Tom is not a coder.** He uses Claude Code as a natural language interface to modify this app.

**Tom uses dictation.** His input will have typos, misheard words, and odd formatting. Don't ask for clarification on obvious dictation errors — just interpret what he meant. He often won't correct these because editing in the terminal is cumbersome and he's focused on the idea, not the spelling.

**Common dictation mistakes — fix silently:**
- "Tori", "Torrey", "Tory" → **Tauri**
- "specifically", "gigantic", "genetic", "genic" → **agentic**
- "chain log" → **changelog**
- "queue" → sometimes means "Q"
- "deaf" → **dev**
- "favor" → **favorite**

His requests will sound like:
- "Add a new source type for YouTube videos"
- "Make the capture panel wider"
- "Add a button to send to Claude"
- "Put the processed content in a collapsible section"

**What he's NOT asking for:**
- Git commands, build processes, debugging
- Code explanations or technical deep-dives

**Your job:** Translate his content/feature requests into actual code changes.

**You are running inside the app.** Claude Code is embedded in the Knowledge Studio desktop app via an xterm.js terminal panel. Tom talks to you from within the same app you're modifying. When he says something looks broken, he's looking at it right now in the UI above your terminal. After you make changes and rebuild, he sees the results without switching windows.

## Backend (Flask)

```
app.py              - Flask backend on port 5001 (~285KB)
youtube_processor.py - Video processing, transcript extraction, AI summarization
library.html        - Main library UI
interface.html      - Processing interface
prompts/current_best/ - Category-specific summary prompts
youtube_intelligence.db - SQLite database
```

### Quick Start

```bash
# Start everything (recommended)
./start_and_keep_running.sh

# Access the app
open http://localhost:5001
```

### Database

SQLite at `youtube_intelligence.db` - main tables: videos, channels, bookmarks, highlights, notes

### API Patterns

Flask routes in `app.py`. Most return JSON. Key endpoints:
- `/api/library` - Get all content
- `/api/videos/{id}` - Video CRUD
- `/api/channels` - Channel management
- `/api/search` - Full-text search
- `/api/queue` - Processing queue
- `/api/highlights` - Highlights/annotations
- `/api/notes` - Notes
- `/api/bookmarks` - Bookmarks

### How Frontend Talks to Backend

HTML files contain JavaScript that makes fetch() calls:
```javascript
const response = await fetch('http://localhost:5001/api/library');
const data = await response.json();
```

## Desktop App (Tauri) — Active

The app runs as a Tauri desktop app with Claude Code embedded inside it. Located in `knowledge-studio-desktop/`.

### Tech Stack

- Tauri v2 (Rust backend)
- React + TypeScript frontend (Vite)
- Flask backend (`app.py`) still runs on port 5001 — Tauri spawns it automatically
- Embedded Claude Code terminal via xterm.js + portable-pty
- SQLite (same database)

### Tauri Frontend Components

```
knowledge-studio-desktop/src/
├── App.tsx              - Main app shell, nav, sidebar counts, Claude panel
├── App.css              - All styling
├── components/
│   ├── Library.tsx      - Content browser with search/filter/sort
│   ├── ItemModal.tsx    - Detail view for a video or article
│   ├── HighlightsModal.tsx - Highlights viewer with star/favorite toggle
│   ├── Sidebar.tsx      - Sidebar with counts (clickable sections)
│   ├── Channels.tsx     - Channel subscriptions and feeds
│   ├── Intelligence.tsx - Intelligence briefs
│   ├── Capture.tsx      - URL capture and processing queue
│   ├── Stats.tsx        - Analytics dashboard
│   └── EmbeddedTerminal.tsx - Claude Code terminal (xterm.js)
```

### Embedding Claude Code Terminal

If you need to add an embedded Claude Code terminal, here's what works and what doesn't:

#### Don't Do This:
1. **Don't use `--print` mode** - Strips all tools (Edit, Bash). Useless.
2. **Don't capture PTY output without a terminal emulator** - Claude outputs ANSI sequences and terminal UI. Without xterm.js, you get garbled text and infinite loops.
3. **Don't try to detect completion by parsing output** - No clean markers. Idle timeouts and regex all fail.

#### Do This:
Use **xterm.js** (terminal emulator) + **portable-pty** (Rust PTY).

**Dependencies:**
- Frontend: `@xterm/xterm`, `@xterm/addon-fit`, `@xterm/addon-web-links`
- Backend: `portable-pty = "0.8"`, `lazy_static = "1.4"`

**Architecture:**
- `pty_spawn` - Creates PTY, spawns `claude --dangerously-skip-permissions`, reader thread emits output via Tauri events
- `pty_write` - Sends keystrokes to PTY
- `pty_resize` - Syncs dimensions
- `pty_kill` - Cleanup

**Reference implementation:** See Command Center's `src/components/EmbeddedTerminal/EmbeddedTerminal.tsx` and `src-tauri/src/lib.rs` (search for `pty_spawn`).

The key insight: VS Code's terminal uses xterm.js for the same reason. You can't dump raw terminal output to a div - you need something that interprets VT100/ANSI sequences.

### Data Persistence

Don't rely solely on localStorage - it can get wiped between builds. Use Tauri file storage as primary, localStorage as fallback.

## Content Processing

- **Screenshot capture**: Drop screenshots in `screenshots/` folder, auto-processed
- **Content categorization**: 3 types - `explainer`, `interview`, `tools_workflows`
- **AI summaries**: Claude Haiku for processing, category-specific prompts in `prompts/current_best/`

## When Making Changes

1. `app.py` is large - search for route names before editing
2. Prompts live in `prompts/current_best/` - one per content type
3. Backend changes: edit `app.py`, Flask auto-reloads
4. Frontend changes: edit files in `knowledge-studio-desktop/src/`, then `npm run build` in `knowledge-studio-desktop/` — the Tauri app needs a restart to pick up new builds
5. Backups in `backups/` folder - create one before major changes
6. The UI Tom sees is the Tauri React app, not the old HTML files (library.html, interface.html, etc.)
