# Zettelkasten CLI

A personal CLI tool to generate and manage a Zettelkasten knowledge base from podcast audio, YouTube videos, and articles. Built to work with Obsidian.

## Overview

This tool processes content from various sources and generates interconnected markdown notes (Zettelkasten) with bidirectional links, making them ready for use in Obsidian.

## Features

### 1. Seed Workflow
Bootstrap your Zettelkasten from the Powerful Introvert Podcast:
- Downloads audio files from RSS feed
- Transcribes using **local Whisper** (runs on your machine, no API costs)
- Extracts key concepts using Claude 3.5 Sonnet
- Generates Zettelkasten files with bidirectional links

### 2. Update Workflow
Add new content to your existing Zettelkasten:
- YouTube videos (downloads audio, transcribes locally)
- Podcast episodes (Apple Podcasts, Spotify)
- Blog articles (extracts text)
- Processes and integrates with existing notes

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

### Seed from podcast RSS feed
```bash
zk seed
```

### Add content from URL
```bash
zk add <url>
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
