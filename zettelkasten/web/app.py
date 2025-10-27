"""FastAPI web application for Zettelkasten UI."""

from pathlib import Path
from typing import List, Optional
import markdown
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from zettelkasten.core.config import Config
from zettelkasten.core.models import ContentType

# Initialize FastAPI app
app = FastAPI(title="Zettelkasten Web UI", version="0.1.0")

# Get project root
project_root = Path(__file__).parent.parent.parent

# Mount static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Setup Jinja2 templates
templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

# Load config
config = Config.from_env()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page showing vault overview."""

    # Get vault statistics
    permanent_notes_path = config.get_permanent_notes_path()
    sources_path = config.get_sources_path()
    staging_path = config.get_staging_path()

    # Count notes
    permanent_notes = list(permanent_notes_path.glob("*.md"))
    # Exclude index files
    permanent_notes = [n for n in permanent_notes if n.stem.upper() not in ["INDEX", "PEOPLE-INDEX", "PERSON-INDEX"]]

    sources = list(sources_path.glob("*.md"))
    sources = [s for s in sources if s.stem.upper() != "INDEX"]

    staging_files = list(staging_path.glob("**/*.md"))

    # Count person notes (properly parse tags from frontmatter)
    person_notes = []
    for note_file in permanent_notes:
        content = note_file.read_text()
        tags = extract_tags_from_frontmatter(content)
        if "person" in tags or "contact" in tags:
            person_notes.append(note_file)

    stats = {
        "total_concepts": len(permanent_notes) - len(person_notes),
        "total_people": len(person_notes),
        "total_sources": len(sources),
        "staging_files": len(staging_files),
    }

    # Check for index files
    concept_index = permanent_notes_path / "INDEX.md"
    people_index = permanent_notes_path / "PEOPLE-INDEX.md"
    sources_index = config.get_sources_base_path() / "INDEX.md"

    indexes = {
        "concept_index_exists": concept_index.exists(),
        "people_index_exists": people_index.exists(),
        "sources_index_exists": sources_index.exists(),
    }

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "stats": stats,
            "indexes": indexes,
        }
    )


@app.get("/indexes/{index_type}", response_class=HTMLResponse)
async def view_index(request: Request, index_type: str):
    """View an index (concepts, people, or sources)."""

    if index_type == "concepts":
        index_path = config.get_permanent_notes_path() / "INDEX.md"
        title = "Concept Index"
    elif index_type == "people":
        index_path = config.get_permanent_notes_path() / "PEOPLE-INDEX.md"
        title = "People Index"
    elif index_type == "sources":
        index_path = config.get_sources_base_path() / "INDEX.md"
        title = "Sources Index"
    else:
        raise HTTPException(status_code=404, detail="Index not found")

    if not index_path.exists():
        raise HTTPException(status_code=404, detail=f"{title} does not exist. Run 'zk index' to create it.")

    # Read and render markdown
    content = index_path.read_text()
    html_content = markdown.markdown(content, extensions=['extra', 'codehilite'])

    # Convert wikilinks to HTML links
    html_content = convert_wikilinks(html_content, base_path="")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": title,
            "content": html_content,
        }
    )


@app.get("/note/{note_path:path}", response_class=HTMLResponse)
async def view_note(request: Request, note_path: str):
    """View a specific note."""

    # Construct full path - try direct path first
    full_path = config.vault_path / note_path
    if not full_path.suffix:
        full_path = full_path.with_suffix(".md")

    # If not found directly, search in common directories
    if not full_path.exists():
        # Try to find the note by filename in permanent-notes, sources, etc.
        filename = Path(note_path).name
        if not filename.endswith('.md'):
            filename = filename + '.md'

        search_dirs = [
            config.get_permanent_notes_path(),
            config.get_sources_path(),
            config.get_fleeting_notes_path(),
        ]

        for search_dir in search_dirs:
            potential_path = search_dir / filename
            if potential_path.exists():
                full_path = potential_path
                break

        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Note not found")

    # Read and render markdown
    content = full_path.read_text()

    # Extract title from frontmatter or first heading
    title = extract_title(content)

    # Render markdown
    html_content = markdown.markdown(content, extensions=['extra', 'codehilite', 'fenced_code'])

    # Convert wikilinks to HTML links
    html_content = convert_wikilinks(html_content, base_path=str(full_path.parent.relative_to(config.vault_path)))

    return templates.TemplateResponse(
        "note.html",
        {
            "request": request,
            "title": title,
            "content": html_content,
            "note_path": note_path,
        }
    )


@app.get("/staging", response_class=HTMLResponse)
async def view_staging(request: Request):
    """View files in staging area."""

    staging_path = config.get_staging_path()

    # Find all markdown files
    staged_files = list(staging_path.glob("**/*.md"))

    files_data = []
    for filepath in staged_files:
        relative_path = filepath.relative_to(staging_path)
        content = filepath.read_text()
        title = extract_title(content)

        files_data.append({
            "path": str(relative_path),
            "title": title,
            "filename": filepath.name,
        })

    return templates.TemplateResponse(
        "staging.html",
        {
            "request": request,
            "files": files_data,
            "count": len(files_data),
        }
    )


def extract_tags_from_frontmatter(content: str) -> List[str]:
    """Extract tags from YAML frontmatter."""
    import re

    # Match YAML frontmatter between --- delimiters
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return []

    frontmatter_text = match.group(1)
    tags = []

    # Parse YAML - handle both simple key: value and list formats
    lines = frontmatter_text.split('\n')
    in_tags = False

    for line in lines:
        # Check if this is the tags key
        if line.startswith('tags:'):
            value = line.split(':', 1)[1].strip()
            if value:
                # Inline format: tags: [tag1, tag2] or tags: tag1, tag2
                value_clean = value.strip('[]')
                tags = [t.strip() for t in value_clean.split(',') if t.strip()]
                return tags
            else:
                # List format starts on next lines
                in_tags = True
        elif in_tags:
            if line.startswith('  - '):
                # List item
                tag = line.strip()[2:].strip()
                tags.append(tag)
            elif line and not line.startswith(' '):
                # End of tags list
                break

    return tags


def extract_title(content: str) -> str:
    """Extract title from markdown content."""
    import re

    # Try frontmatter first
    fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        frontmatter = fm_match.group(1)
        for line in frontmatter.split('\n'):
            if line.startswith('title:'):
                return line.split(':', 1)[1].strip()

    # Try first heading
    heading_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if heading_match:
        return heading_match.group(1).strip()

    return "Untitled"


def convert_wikilinks(html: str, base_path: str = "") -> str:
    """Convert [[wikilinks]] to HTML links."""
    import re

    # Pattern: [[path/to/note|Display Text]] or [[path/to/note]]
    pattern = r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]'

    def replace_wikilink(match):
        link_target = match.group(1)
        display_text = match.group(2) if match.group(2) else link_target

        # Clean up the link target
        # Remove .md extension if present
        if link_target.endswith('.md'):
            link_target = link_target[:-3]

        # Create URL-friendly path
        url = f"/note/{link_target}"

        return f'<a href="{url}" class="wikilink">{display_text}</a>'

    return re.sub(pattern, replace_wikilink, html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
