# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a personal CLI tool for generating and managing a Zettelkasten knowledge management system from various content sources. The tool generates markdown files compatible with Obsidian, with automatic concept extraction and bidirectional linking.

**Primary Use Cases:**
1. **Seed Workflow**: Bootstrap Zettelkasten from the Powerful Introvert Podcast RSS feed
2. **Update Workflow**: Add content from YouTube videos, podcast episodes, or blog articles

## Tech Stack

- **Language**: Python 3.9+
- **CLI Framework**: Typer with Rich for output
- **Transcription**: Local Whisper (openai-whisper package with PyTorch)
- **AI**: Anthropic Claude API for concept extraction
- **Dependencies**: feedparser, yt-dlp, requests, beautifulsoup4, pydantic, torch, anthropic

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
├── core/          # Core functionality (config, models)
├── processors/    # Content processors (audio, video, articles)
├── generators/    # Zettelkasten file generators
└── utils/         # Utility functions
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
4. Extract concepts using Claude API (Claude 3.5 Sonnet)
5. Generate Zettelkasten notes with bidirectional links
6. Save to vault directory

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
- **Concept Extraction**: Uses Anthropic Claude 3.5 Sonnet (requires API key, costs apply)
- Audio/video files and transcripts are stored locally (gitignored)
- The vault output directory is where Obsidian reads the Zettelkasten
- Whisper model downloads automatically on first use (~150MB for base model)
- Larger Whisper models (medium/large) provide better accuracy but are slower
