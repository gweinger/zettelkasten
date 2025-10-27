# Zettelkasten Web UI

A local web-based interface for browsing and managing your Zettelkasten vault.

## Features

### Phase 1 (Current)
- **Home Dashboard**: Overview of your vault with statistics
  - Total concepts, people, sources, and staging files
  - Quick navigation to all sections
- **Index Browsing**: Browse your indexes
  - Concepts Index
  - People Index
  - Sources Index
- **Note Viewer**: View individual notes
  - Full markdown rendering
  - Wikilink support (clickable `[[links]]`)
  - Code syntax highlighting
- **Staging Area**: View files waiting for review

### Coming in Phase 2
- Add content from URLs
- Approve/edit/delete staging files
- Create new notes from web UI
- Search functionality
- Real-time file watching

## Running the Web UI

### Start the Server

```bash
# From the project root
python3 -m uvicorn zettelkasten.web.app:app --reload --host 127.0.0.1 --port 8000
```

### Access the UI

Open your browser to: **http://127.0.0.1:8000**

### Stop the Server

Press `Ctrl+C` in the terminal where the server is running.

## Development

### Project Structure

```
zettelkasten/web/
├── app.py                 # FastAPI application
├── templates/             # Jinja2 HTML templates
│   ├── base.html         # Base template
│   ├── home.html         # Home page
│   ├── index.html        # Index viewer
│   ├── note.html         # Note viewer
│   └── staging.html      # Staging area
└── static/               # Static assets
    └── css/
        └── style.css     # Styles
```

### Tech Stack

- **Backend**: FastAPI
- **Templating**: Jinja2
- **Markdown**: python-markdown
- **Server**: Uvicorn with auto-reload
- **Styling**: Custom CSS

## Tips

- The `--reload` flag enables auto-reload on code changes during development
- All changes to markdown files in your vault are immediately visible (just refresh)
- Wikilinks work between all notes - click any `[[link]]` to navigate
- The web UI reads directly from your vault - no database needed
