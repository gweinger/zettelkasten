# Zettelkasten CLI

A personal CLI tool to generate and manage a Zettelkasten knowledge base from podcast audio, YouTube videos, and articles. Built to work with Obsidian.

## Overview

This tool processes content from various sources and generates interconnected markdown notes (Zettelkasten) with bidirectional links, making them ready for use in Obsidian.

## Features

### 1. Seed Workflow
Bootstrap your Zettelkasten from a Podcast RSS Feed:
- Parses RSS feed for podcast episodes
- Downloads audio files using requests/yt-dlp
- Transcribes using **local Whisper** (runs on your machine, no API costs)
- Extracts key concepts and references using Claude 3.5 Sonnet
- Generates Zettelkasten markdown files with bidirectional wikilinks
- Saves to vault directory ready for Obsidian

### 2. Update Workflow
Add new content to your existing Zettelkasten:
- **YouTube videos**: Downloads audio and transcribes locally
- **Podcast episodes**: Handles various podcast sources
- **Blog articles**: Extracts and processes text content
- Identifies content type automatically from URL
- Extracts concepts and integrates with existing notes
- Generates interconnected markdown with bidirectional links

### 3. Additional Features
- **Quick note creation**: `zk new` command for creating notes quickly
- **Configuration management**: Easy setup with environment variables
- **Obsidian integration**: Generated files work seamlessly with Obsidian vaults
- **YAML frontmatter**: Automatic metadata for date, source, and tags
- **Bidirectional linking**: Wikilink-style connections between related concepts
- **Local processing**: No API costs for transcription (Whisper runs locally)

## Setup

1. Install dependencies:
```bash
pip install -e .
```

2. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

3. Add your Anthropic API key to `.env` (required for Claude concept extraction)
   - Transcription runs locally using Whisper - no API key needed!
   - Optionally configure `WHISPER_MODEL_SIZE` (tiny/base/small/medium/large)

## Usage

### Web UI (Recommended)

Run the web interface:
```bash
./run.sh
```

Then open http://127.0.0.1:8000 in your browser.

The web UI provides:
- Dashboard with vault statistics
- Add content from URLs
- Create new notes (concept, person, source, fleeting)
- Review and approve staged notes
- Browse notes and indexes

The run script automatically:
- Uses the correct Python version (python3)
- Checks for and optionally kills existing processes on port 8000
- Verifies the package is installed
- Starts the server with hot-reload enabled

### CLI Commands

#### Initialize a new vault
```bash
zk init
```

#### Seed from podcast RSS feed
```bash
zk seed
```

#### Add content from URL
```bash
zk add <url>
```

#### Create a new note
```bash
zk new
```

#### Show configuration
```bash
zk config --show
```

## Development

Install development dependencies:
```bash
pip install -e ".[dev]"
```

Run tests:
```bash
pytest
```

Format code:
```bash
black .
ruff check .
```
