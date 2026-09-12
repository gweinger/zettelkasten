# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a personal tool for generating and managing a Zettelkasten knowledge management system from various content sources. It generates markdown files compatible with Obsidian, with automatic concept extraction and bidirectional linking.

It ships with **two interfaces**: a `zk` Typer CLI and a **FastAPI web app** (`zettelkasten/web/app.py`), which is the primary day-to-day interface. Generated notes pass through a **staging area** where they are reviewed/edited/approved before being written into the vault.

**Primary Use Cases:**
1. **Seed Workflow**: Bootstrap Zettelkasten from a podcast RSS feed
2. **Update Workflow**: Add content from YouTube videos, podcast episodes, or blog articles
3. **Episode & person management**: Manage podcast episodes (RSS linking, refresh), generate person/guest research notes, and generate interview questions

## Tech Stack

- **Language**: Python 3.9+
- **CLI Framework**: Typer with Rich for output
- **Web App**: FastAPI + Uvicorn, server-rendered with Jinja2 templates (`zettelkasten/web/templates/`)
- **Transcription**: Local Whisper (openai-whisper package with PyTorch)
- **AI**: Anthropic Claude API for concept extraction and content generation
- **Dependencies**: feedparser, yt-dlp, requests, beautifulsoup4, pydantic, torch, anthropic, fastapi, uvicorn, jinja2, markdown

## Development Commands

### Setup
```bash
# Install package in editable mode with dependencies
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Set up environment variables
cp .env.example .env
# Then edit .env to add your ANTHROPIC_API_KEY (for Claude concept extraction)
# Whisper runs locally, no API key needed for transcription
```

### Running the Web App (primary interface)
```bash
# Start the FastAPI web app on http://127.0.0.1:8000 (with --reload)
./run.sh
# Equivalent to:
python3 -m uvicorn zettelkasten.web.app:app --host 127.0.0.1 --port 8000 --reload
```

### Running the CLI
```bash
# Seed Zettelkasten from podcast RSS feed
zk seed

# Add content from a URL
zk add <url>

# Initialize a new vault
zk init

# Show configuration
zk config --show

# Other commands: zk new, zk approve, zk staging, zk index, zk process-inbox,
# zk clean-inbox, zk vault, zk research-person, zk orphans, zk rss, zk episode,
# zk generate-questions
```

### Development Tools
```bash
# Format code
black .

# Lint code
ruff check .

# Type checking
mypy zettelkasten/

# Run tests
pytest

# Run tests with coverage
pytest --cov=zettelkasten
```

## Project Architecture

### Directory Structure
```
zettelkasten/
├── cli.py         # Typer CLI entry point (zk command)
├── core/          # Core functionality (config, models, workflow)
├── processors/    # Content processors (transcription, concepts, youtube, articles)
├── generators/    # Zettelkasten file generators (zettel, index, orphan, person research, note content)
├── utils/         # Utility helpers (episode_manager, rss_manager, interview_generator, orphan_finder, vault_scanner, url_detector)
└── web/           # FastAPI web app (app.py) + Jinja2 templates/
```

### Key Workflows

**Seed Workflow (RSS → Zettelkasten):**
1. Parse RSS feed for podcast episodes
2. Download audio files using requests/yt-dlp
3. Transcribe audio using local Whisper (runs on your machine)
4. Extract key concepts and references using Claude API
5. Generate Zettelkasten markdown files with bidirectional links
6. Save to vault directory for Obsidian

**Update Workflow (URL → Zettelkasten):**
1. Identify content type from URL (YouTube, podcast, article)
2. Download/extract content appropriately:
   - YouTube: yt-dlp for audio
   - Podcasts: API or audio download
   - Articles: beautifulsoup4 for text extraction
3. Process content:
   - Audio/Video: Transcribe locally using Whisper (no API calls)
   - Articles: Text already extracted
4. Extract concepts using Claude API (see model note below)
5. Generate Zettelkasten notes with bidirectional links
6. Save to vault directory (via the staging area when using the web app)

**Staging Workflow (web app):**
Generated notes are written to a staging area first. From the web UI (`/staging`) they can be viewed, edited, approved (moved into the vault), or deleted. The CLI mirrors this with `zk staging` and `zk approve`.

### Configuration Management

Configuration is managed via:
- Environment variables (`.env` file)
- `zettelkasten/core/config.py` using Pydantic models
- Key settings:
  - `ANTHROPIC_API_KEY`: Required for Claude concept extraction
  - `WHISPER_MODEL_SIZE`: Local Whisper model (tiny/base/small/medium/large)
  - `PODCAST_RSS_FEED`: RSS feed URL
  - Paths: vault, downloads, transcripts directories

### Output Format

Generated Zettelkasten files follow Obsidian markdown conventions:
- YAML frontmatter with metadata (date, source, tags)
- Wikilink-style bidirectional links: `[[Note Title]]`
- Unique filenames using timestamps or slugified titles
- Organized by content type or topic

## Important Notes

- This is a personal tool for the Powerful Introvert Podcast by Greg Weinger
- **Transcription**: Runs locally using Whisper (no API costs, requires GPU/CPU)
- **Claude models (hardcoded in code, no central config)**: concept extraction, note content, and index generation use `claude-3-haiku-20240307`; interview question generation uses `claude-opus-4-1-20250805`. These IDs are string literals scattered across `processors/concept_extractor.py`, `generators/note_content_generator.py`, `generators/index_generator.py`, and `utils/interview_generator.py` — update all call sites when changing models (consider centralizing). Requires `ANTHROPIC_API_KEY`; costs apply.
- Audio/video files and transcripts are stored locally (gitignored)
- The vault output directory is where Obsidian reads the Zettelkasten
- Whisper model downloads automatically on first use (~150MB for base model)
- Larger Whisper models (medium/large) provide better accuracy but are slower
