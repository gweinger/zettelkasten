"""FastAPI web application for Zettelkasten UI."""

from pathlib import Path
from typing import List, Optional
import markdown
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from zettelkasten.core.config import Config
from zettelkasten.core.models import ContentType
from zettelkasten.core.workflow import AddWorkflow

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
        "total_concepts": len(permanent_notes),  # Include all notes (people are a subset)
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
            "vault_name": config.vault_name,
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

    # Extract frontmatter properties
    properties = extract_frontmatter_properties(content)

    # Remove frontmatter from content before rendering
    content_without_fm = remove_frontmatter(content)

    html_content = markdown.markdown(content_without_fm, extensions=['extra', 'codehilite'])

    # Convert wikilinks to HTML links
    html_content = convert_wikilinks(html_content, base_path="")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": title,
            "content": html_content,
            "properties": properties,
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
        # Try to find the note by filename in permanent-notes, sources/summaries, etc.
        filename = Path(note_path).name
        if not filename.endswith('.md'):
            filename = filename + '.md'

        search_dirs = [
            config.get_permanent_notes_path(),
            config.get_sources_path(),  # For source summaries
            config.get_sources_path().parent / "sources" / "summaries",  # Explicit summaries path
            config.get_fleeting_notes_path(),
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
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

    # Extract frontmatter properties
    properties = extract_frontmatter_properties(content)

    # Remove frontmatter from content before rendering
    content_without_fm = remove_frontmatter(content)

    # Render markdown
    html_content = markdown.markdown(content_without_fm, extensions=['extra', 'codehilite', 'fenced_code'])

    # Convert wikilinks to HTML links
    html_content = convert_wikilinks(html_content, base_path=str(full_path.parent.relative_to(config.vault_path)))

    return templates.TemplateResponse(
        "note.html",
        {
            "request": request,
            "title": title,
            "content": html_content,
            "note_path": note_path,
            "properties": properties,
        }
    )


@app.get("/add-url", response_class=HTMLResponse)
async def add_url_form(request: Request, error: Optional[str] = None):
    """Show the Add URL form."""
    return templates.TemplateResponse(
        "add_url.html",
        {
            "request": request,
            "vault_name": config.vault_name,
            "error": error,
        }
    )


@app.post("/add-url", response_class=HTMLResponse)
async def add_url_submit(request: Request, url: str = Form(...), force: Optional[str] = Form(None)):
    """Process URL submission."""
    force_bool = force == "true"

    try:
        # Validate API key
        if not config.anthropic_api_key or config.anthropic_api_key == "your_anthropic_api_key_here":
            error = "ANTHROPIC_API_KEY not configured. Please add your Anthropic API key to the .env file."
            return templates.TemplateResponse(
                "add_url.html",
                {
                    "request": request,
                    "vault_name": config.vault_name,
                    "error": error,
                }
            )

        # Create workflow and process URL
        workflow = AddWorkflow(config)
        saved_paths = workflow.process_url(url, force=force_bool)

        # Extract relative paths for display
        file_paths = [str(path.relative_to(config.vault_path)) for path in saved_paths]

        # Try to extract title from first file
        title = None
        if saved_paths:
            try:
                first_file_content = saved_paths[0].read_text()
                # Look for title in frontmatter or first heading
                lines = first_file_content.split('\n')
                for line in lines:
                    if line.startswith('title:'):
                        title = line.split(':', 1)[1].strip()
                        break
                    elif line.startswith('# '):
                        title = line[2:].strip()
                        break
            except Exception:
                pass

        return templates.TemplateResponse(
            "add_url_result.html",
            {
                "request": request,
                "vault_name": config.vault_name,
                "url": url,
                "title": title,
                "file_count": len(saved_paths),
                "file_paths": file_paths,
            }
        )

    except ValueError as e:
        # Show error on the form page
        return templates.TemplateResponse(
            "add_url.html",
            {
                "request": request,
                "vault_name": config.vault_name,
                "error": str(e),
            }
        )
    except Exception as e:
        # Show unexpected errors
        error = f"Unexpected error: {str(e)}"
        return templates.TemplateResponse(
            "add_url.html",
            {
                "request": request,
                "vault_name": config.vault_name,
                "error": error,
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


@app.get("/staging/view/{file_path:path}", response_class=HTMLResponse)
async def view_staging_file(request: Request, file_path: str):
    """View a specific file in staging area."""
    staging_path = config.get_staging_path()
    full_path = staging_path / file_path

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found in staging")

    # Read file content
    content = full_path.read_text()
    title = extract_title(content)

    # Extract properties
    properties = extract_frontmatter_properties(content)

    # Remove frontmatter and convert to HTML
    content_without_fm = remove_frontmatter(content)
    html_content = markdown.markdown(content_without_fm, extensions=['extra', 'codehilite'])
    html_content = convert_wikilinks(html_content, base_path="")

    return templates.TemplateResponse(
        "staging_file.html",
        {
            "request": request,
            "title": title,
            "file_path": file_path,
            "content": html_content,
            "properties": properties,
        }
    )


@app.get("/staging/edit/{file_path:path}", response_class=HTMLResponse)
async def edit_staging_file_form(request: Request, file_path: str):
    """Show edit form for staging file."""
    staging_path = config.get_staging_path()
    full_path = staging_path / file_path

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found in staging")

    content = full_path.read_text()
    title = extract_title(content)

    return templates.TemplateResponse(
        "staging_edit.html",
        {
            "request": request,
            "title": title,
            "file_path": file_path,
            "content": content,
            "error": None,
        }
    )


@app.post("/staging/edit/{file_path:path}", response_class=HTMLResponse)
async def edit_staging_file_save(request: Request, file_path: str, content: str = Form(...)):
    """Save edited staging file."""
    staging_path = config.get_staging_path()
    full_path = staging_path / file_path

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found in staging")

    try:
        # Write the updated content
        full_path.write_text(content)

        # Redirect back to view
        return RedirectResponse(url=f"/staging/view/{file_path}", status_code=303)
    except Exception as e:
        # Show error on edit form
        title = extract_title(content)
        return templates.TemplateResponse(
            "staging_edit.html",
            {
                "request": request,
                "title": title,
                "file_path": file_path,
                "content": content,
                "error": str(e),
            }
        )


@app.post("/staging/approve/{file_path:path}")
async def approve_staging_file(file_path: str):
    """Approve and move a single staging file to vault."""
    import shutil

    staging_path = config.get_staging_path()
    full_path = staging_path / file_path

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found in staging")

    try:
        # Read file to check merge info
        import re
        content = full_path.read_text()

        # Extract frontmatter to check for merge_into
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        is_merge = False
        merge_target = None

        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            for line in frontmatter.split('\n'):
                if line.startswith('merge_into:'):
                    merge_target = line.split(':', 1)[1].strip()
                if line.startswith('is_new:'):
                    is_new_val = line.split(':', 1)[1].strip()
                    is_merge = (is_new_val.lower() == 'false')

        if is_merge and merge_target:
            # Handle merge - this logic is from cli.py approve command
            from zettelkasten.cli import merge_notes_intelligently
            target_path = config.get_permanent_notes_path() / merge_target

            if target_path.exists():
                existing_content = target_path.read_text()
                new_content_start = content.find('---', 3) + 3
                new_content = content[new_content_start:].strip()

                # Remove merge banner
                if new_content.startswith('>'):
                    lines = new_content.split('\n')
                    new_content = '\n'.join([l for l in lines if not l.strip().startswith('>')])
                    new_content = new_content.strip()

                merged_content = merge_notes_intelligently(existing_content, new_content)
                target_path.write_text(merged_content)
                full_path.unlink()
            else:
                # Target not found, create new
                destination_dir = config.get_permanent_notes_path()
                destination = destination_dir / full_path.name
                shutil.move(str(full_path), str(destination))
        else:
            # Normal move - determine destination from path
            if "concepts" in full_path.parts or "permanent" in full_path.parts:
                destination_dir = config.get_permanent_notes_path()
            elif "sources" in full_path.parts:
                destination_dir = config.get_sources_path()
            else:
                destination_dir = config.get_permanent_notes_path()

            destination = destination_dir / full_path.name
            shutil.move(str(full_path), str(destination))

        # Rebuild indices
        from zettelkasten.generators.index_generator import IndexGenerator
        index_generator = IndexGenerator(config)
        index_generator.rebuild_indices()

        # Redirect back to staging list
        return RedirectResponse(url="/staging", status_code=303)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error approving file: {str(e)}")


@app.post("/staging/delete/{file_path:path}")
async def delete_staging_file(file_path: str):
    """Delete a staging file."""
    staging_path = config.get_staging_path()
    full_path = staging_path / file_path

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found in staging")

    try:
        full_path.unlink()
        return RedirectResponse(url="/staging", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")


def extract_frontmatter_properties(content: str) -> dict:
    """Extract all properties from YAML frontmatter as a dictionary."""
    import re

    # Match YAML frontmatter between --- delimiters
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return {}

    frontmatter_text = match.group(1)
    properties = {}

    # Parse YAML - handle both simple key: value and list formats
    lines = frontmatter_text.split('\n')
    current_key = None
    current_list = []

    for line in lines:
        # Check if line is a key: value pair
        if ':' in line and not line.startswith(' '):
            # Save previous list if any
            if current_key and current_list:
                properties[current_key] = current_list
                current_list = []

            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()

            if value:
                # Regular key: value pair
                properties[key] = value
                current_key = None
            else:
                # Might be start of a list
                current_key = key
                current_list = []

        elif line.startswith('  - ') and current_key:
            # List item
            item = line.strip()[2:].strip()
            current_list.append(item)

    # Save any remaining list
    if current_key and current_list:
        properties[current_key] = current_list

    return properties


def remove_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from content."""
    import re

    # Remove frontmatter
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if match:
        return content[match.end():]
    return content


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

        # Handle relative paths in source notes
        # If link starts with "summaries/" or "../", resolve it properly
        if link_target.startswith('../'):
            # Remove ../ prefix - our view_note will search for it
            link_target = link_target.replace('../', '')
        elif link_target.startswith('summaries/'):
            # This is a relative path from sources/ directory
            link_target = 'sources/' + link_target

        # Create URL-friendly path
        url = f"/note/{link_target}"

        return f'<a href="{url}" class="wikilink">{display_text}</a>'

    return re.sub(pattern, replace_wikilink, html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
