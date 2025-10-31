"""FastAPI web application for Zettelkasten UI."""

from pathlib import Path
from typing import List, Optional
import markdown
from fastapi import FastAPI, Request, HTTPException, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from zettelkasten.core.config import Config
from zettelkasten.core.models import ContentType
from zettelkasten.core.workflow import AddWorkflow

# Initialize FastAPI app
app = FastAPI(title="Zettelkasten Web UI", version="0.1.0")

# Add session middleware for flash messages
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-here-change-in-production")

# Get project root
project_root = Path(__file__).parent.parent.parent

# Mount static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Load config first (needed for episodes path)
config = Config.from_env()

# Note: Episodes are served via custom routes (/episodes for management, /episode-media for files)
# We don't mount /episodes as static files because that would prevent the /episodes routes from working

# Setup Jinja2 templates
templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))


# Flash message helpers
def set_flash(request: Request, message: str, category: str = "info"):
    """Set a flash message in the session."""
    if "flash_messages" not in request.session:
        request.session["flash_messages"] = []
    request.session["flash_messages"].append({"message": message, "category": category})


def get_flashed_messages(request: Request) -> List[dict]:
    """Get and clear flash messages from the session."""
    messages = request.session.pop("flash_messages", [])
    return messages


# Background task for reindexing
def rebuild_indices_task():
    """Rebuild indices in the background."""
    try:
        from zettelkasten.generators.index_generator import IndexGenerator
        index_generator = IndexGenerator(config)
        index_generator.rebuild_indices()
        print("✓ Indices rebuilt successfully")
    except Exception as e:
        print(f"✗ Error rebuilding indices: {e}")


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with custom error page."""
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "vault_name": config.vault_name,
            "error_message": exc.detail,
            "error_detail": None,
        },
        status_code=exc.status_code
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions with custom error page."""
    import traceback
    error_detail = traceback.format_exc()

    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "vault_name": config.vault_name,
            "error_message": "An unexpected error occurred. Please check the technical details below or contact support.",
            "error_detail": error_detail,
        },
        status_code=500
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page showing vault overview."""
    from zettelkasten.utils.episode_manager import EpisodeManager

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

    # Count episodes
    episode_manager = EpisodeManager(config)
    episodes = episode_manager.list_episodes()

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
        "total_episodes": len(episodes),
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
            "active_section": "home",
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
            "active_section": index_type,
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
        # Check if this is an episodes path (e.g., "episodes/Grant Harris/index")
        if note_path.startswith("episodes/"):
            # Extract episode name from path
            path_parts = note_path.split('/')
            if len(path_parts) >= 2:
                episode_name = path_parts[1]
                # Search for episode in all configured directories
                episode_path = config.find_episode_path(episode_name)
                if episode_path:
                    # Reconstruct the full path within the found episode directory
                    remaining_path = '/'.join(path_parts[2:]) if len(path_parts) > 2 else ''
                    if remaining_path:
                        full_path = episode_path / remaining_path
                    else:
                        full_path = episode_path
                    if not full_path.suffix:
                        full_path = full_path.with_suffix(".md")

            # If still not found, try the old way (sources/episodes/)
            if not full_path.exists():
                sources_base = config.get_sources_base_path()
                full_path = sources_base / note_path
                if not full_path.suffix:
                    full_path = full_path.with_suffix(".md")
        else:
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

    # Check if this is a text file (not markdown)
    is_text_file = full_path.suffix.lower() == '.txt'
    download_url = None

    # Read and render content
    content = full_path.read_text()

    # Extract title from frontmatter or first heading
    title = extract_title(content)

    # Extract frontmatter properties
    properties = extract_frontmatter_properties(content)

    # Remove frontmatter from content before rendering
    content_without_fm = remove_frontmatter(content)

    if is_text_file:
        # For text files, render as preformatted text with download link
        # Generate download URL pointing to the static episodes mount
        if note_path.startswith("episodes/"):
            from urllib.parse import quote
            parts = note_path.split('/')
            if len(parts) >= 3:
                episode_dir = parts[1]
                filename = parts[-1]
                download_url = f"/episodes/{quote(episode_dir)}/{quote(filename)}"

        # Wrap content in <pre> tags for plain text display
        html_content = f'<pre style="white-space: pre-wrap; word-wrap: break-word;">{content_without_fm}</pre>'
    else:
        # Render markdown
        html_content = markdown.markdown(content_without_fm, extensions=['extra', 'codehilite', 'fenced_code'])

    # Convert wikilinks to HTML links
    # Try to get relative path, but handle episodes in additional directories
    try:
        base_path = str(full_path.parent.relative_to(config.vault_path))
    except ValueError:
        # File is outside vault (e.g., in additional episode directory)
        base_path = ""
    html_content = convert_wikilinks(html_content, base_path=base_path)

    # If this is an episode page, fix media file links
    is_episode = note_path.startswith("episodes/")
    episode_name = None
    is_episode_index = False
    if is_episode:
        html_content = fix_episode_media_links(html_content, note_path)
        # Extract episode name from path (e.g., "episodes/Grant Harris/index" -> "Grant Harris")
        path_parts = note_path.split('/')
        if len(path_parts) >= 2:
            episode_name = path_parts[1]
            # Check if this is the index page (no file after episode name, or explicitly index)
            is_episode_index = len(path_parts) == 2 or (len(path_parts) == 3 and path_parts[2] == "index")

    return templates.TemplateResponse(
        "note.html",
        {
            "request": request,
            "title": title,
            "content": html_content,
            "note_path": note_path,
            "properties": properties,
            "download_url": download_url,
            "is_text_file": is_text_file,
            "flash_messages": get_flashed_messages(request),
            "is_episode": is_episode,
            "episode_name": episode_name,
            "is_episode_index": is_episode_index,
        }
    )


@app.post("/episode/{episode_name}/rss-link", response_class=HTMLResponse)
async def rss_link_episode(request: Request, episode_name: str):
    """Link an episode to RSS feed data."""
    try:
        from zettelkasten.utils.rss_manager import RSSManager

        rss_manager = RSSManager(config)

        # Try to find matching episode in RSS
        rss_episode = rss_manager.find_matching_episode(episode_name)
        if not rss_episode:
            set_flash(request, f"⚠ No matching RSS data found for '{episode_name}'", "warning")
            return RedirectResponse(url=f"/note/episodes/{episode_name}/index", status_code=303)

        # Find episode directory
        episode_path = config.find_episode_path(episode_name)
        if not episode_path:
            set_flash(request, f"❌ Episode directory not found: {episode_name}", "error")
            return RedirectResponse(url=f"/note/episodes/{episode_name}/index", status_code=303)

        # Update index.md with RSS data
        index_file = episode_path / "index.md"
        if not index_file.exists():
            set_flash(request, f"❌ index.md not found", "error")
            return RedirectResponse(url=f"/note/episodes/{episode_name}/index", status_code=303)

        import yaml
        content = index_file.read_text(encoding='utf-8')
        parts = content.split('---')
        if len(parts) < 3:
            set_flash(request, f"❌ Invalid frontmatter", "error")
            return RedirectResponse(url=f"/note/episodes/{episode_name}/index", status_code=303)

        frontmatter_str = parts[1]
        body = '---'.join(parts[2:])
        frontmatter = yaml.safe_load(frontmatter_str) or {}

        # Add RSS metadata
        frontmatter['rss_title'] = rss_episode['title']
        frontmatter['rss_description'] = rss_episode['description'][:500]
        frontmatter['rss_date'] = rss_episode['pub_date']

        # Write back updated frontmatter
        new_frontmatter = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
        updated_content = f"---\n{new_frontmatter}---{body}"
        index_file.write_text(updated_content, encoding='utf-8')

        set_flash(request, f"✓ RSS data updated for '{episode_name}'", "success")
        return RedirectResponse(url=f"/note/episodes/{episode_name}/index", status_code=303)

    except Exception as e:
        set_flash(request, f"❌ Error: {str(e)}", "error")
        return RedirectResponse(url=f"/note/episodes/{episode_name}/index", status_code=303)


@app.post("/episode/{episode_name}/refresh", response_class=HTMLResponse)
async def refresh_episode(request: Request, episode_name: str, background_tasks: BackgroundTasks):
    """Full refresh of an episode (remove and re-import)."""
    try:
        from zettelkasten.utils.episode_manager import EpisodeManager

        episode_manager = EpisodeManager(config)

        # Find episode directory
        episode_path = config.find_episode_path(episode_name)
        if not episode_path:
            set_flash(request, f"❌ Episode directory not found: {episode_name}", "error")
            return RedirectResponse(url="/episodes", status_code=303)

        # Check if index.md exists
        index_file = episode_path / "index.md"
        if not index_file.exists():
            set_flash(request, f"❌ Episode not indexed: {episode_name}", "error")
            return RedirectResponse(url="/episodes", status_code=303)

        # Get current episode number from frontmatter
        import yaml
        content = index_file.read_text(encoding='utf-8')
        parts = content.split('---')
        current_episode_number = None
        if len(parts) >= 3:
            frontmatter = yaml.safe_load(parts[1]) or {}
            current_episode_number = frontmatter.get('episode_number')

        # Delete index.md
        index_file.unlink()

        # Re-import with same episode number
        episode_manager.import_existing_episode(episode_name, episode_number=current_episode_number)

        # Rebuild indices
        from zettelkasten.generators.index_generator import IndexGenerator
        index_gen = IndexGenerator(config)
        index_gen.rebuild_indices()

        set_flash(request, f"✓ Episode '{episode_name}' refreshed successfully", "success")
        return RedirectResponse(url=f"/note/episodes/{episode_name}/index", status_code=303)

    except Exception as e:
        set_flash(request, f"❌ Error refreshing episode: {str(e)}", "error")
        return RedirectResponse(url="/episodes", status_code=303)


@app.post("/episode/{episode_name}/remove", response_class=HTMLResponse)
async def remove_episode(request: Request, episode_name: str, background_tasks: BackgroundTasks):
    """Remove episode from index (keeps files intact)."""
    try:
        # Find episode directory
        episode_path = config.find_episode_path(episode_name)
        if not episode_path:
            set_flash(request, f"❌ Episode directory not found: {episode_name}", "error")
            return RedirectResponse(url="/episodes", status_code=303)

        # Delete index.md
        index_file = episode_path / "index.md"
        if index_file.exists():
            index_file.unlink()

        # Rebuild indices to remove from index
        from zettelkasten.generators.index_generator import IndexGenerator
        index_gen = IndexGenerator(config)
        index_gen.rebuild_indices()

        set_flash(request, f"✓ Episode '{episode_name}' removed from index (files preserved)", "success")
        return RedirectResponse(url="/episodes", status_code=303)

    except Exception as e:
        set_flash(request, f"❌ Error removing episode: {str(e)}", "error")
        return RedirectResponse(url="/episodes", status_code=303)


# Workflow Routes
@app.get("/workflows", response_class=HTMLResponse)
async def workflows_main(request: Request):
    """Show the main workflows page."""
    return templates.TemplateResponse(
        "workflows.html",
        {
            "request": request,
            "vault_name": config.vault_name,
            "active_section": "workflows",
        }
    )


@app.get("/workflows/interview-questions", response_class=HTMLResponse)
async def workflow_interview_questions(request: Request):
    """Show the generate interview questions workflow page."""
    return templates.TemplateResponse(
        "workflow_interview_questions.html",
        {
            "request": request,
            "vault_name": config.vault_name,
            "active_section": "interview-questions",
        }
    )


@app.post("/workflows/interview-questions", response_class=HTMLResponse)
async def generate_interview_questions_workflow(
    request: Request,
    guest_name: str = Form(...),
):
    """Generate interview questions for an episode."""
    try:
        from zettelkasten.utils.interview_generator import InterviewQuestionGenerator

        # Find episode directory
        episode_path = config.find_episode_path(guest_name)
        if not episode_path:
            return templates.TemplateResponse(
                "workflow_interview_questions.html",
                {
                    "request": request,
                    "error": f"❌ Episode directory not found for '{guest_name}'",
                    "vault_name": config.vault_name,
                    "active_section": "interview-questions",
                }
            )

        # Look for prep transcript
        transcript_file = None
        for potential_name in ["prep conversation transcript.txt", "prep conversation transcript.md", "prep-transcript.txt"]:
            potential_file = episode_path / potential_name
            if potential_file.exists():
                transcript_file = potential_file
                break

        # Check for wildcard match if not found
        if not transcript_file:
            import glob
            for pattern in ["*pre*.txt", "*pre*.md", "*prep*.txt", "*prep*.md"]:
                matches = list(episode_path.glob(pattern))
                if matches:
                    transcript_file = matches[0]
                    break

        # Require transcript
        if not transcript_file or not transcript_file.exists():
            return templates.TemplateResponse(
                "workflow_interview_questions.html",
                {
                    "request": request,
                    "error": f"❌ Prep conversation transcript not found for '{guest_name}'. Expected one of: prep conversation transcript.txt, prep-transcript.txt, or *pre*.txt",
                    "vault_name": config.vault_name,
                    "active_section": "interview-questions",
                }
            )

        # Generate questions
        generator = InterviewQuestionGenerator(config)
        questions = generator.generate_questions(
            guest_name=guest_name,
            transcript_path=transcript_file,
        )

        # Save to file
        questions_file = episode_path / "interview questions.md"
        generator.save_questions(questions, questions_file)

        # Ensure episode index.md exists
        generator.ensure_episode_index(guest_name, episode_path)

        # Create person note if it doesn't exist (with background from transcript)
        generator.ensure_person_note(guest_name, transcript_path=transcript_file)

        # Rebuild indices to add the episode and person to the knowledge base
        from zettelkasten.generators.index_generator import IndexGenerator
        index_generator = IndexGenerator(config)
        index_generator.rebuild_indices()

        set_flash(request, f"✓ Interview questions generated and saved for '{guest_name}'", "success")
        return RedirectResponse(url=f"/note/episodes/{guest_name}/index", status_code=303)

    except Exception as e:
        return templates.TemplateResponse(
            "workflow_interview_questions.html",
            {
                "request": request,
                "error": f"❌ Error generating questions: {str(e)}",
                "vault_name": config.vault_name,
                "active_section": "interview-questions",
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
            "active_section": "add-url",
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
                    "active_section": "add-url",
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
                "active_section": "add-url",
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
                "active_section": "add-url",
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
                "active_section": "add-url",
            }
        )


@app.get("/episodes", response_class=HTMLResponse)
async def view_episodes(request: Request):
    """View episodes landing page."""
    from zettelkasten.utils.episode_manager import EpisodeManager

    episode_manager = EpisodeManager(config)
    episode_names = episode_manager.list_episodes()

    # Get episode details
    episodes_data = []
    for episode_name in episode_names:
        episode_path = config.find_episode_path(episode_name)
        if episode_path:
            index_file = episode_path / "index.md"
            if index_file.exists():
                content = index_file.read_text()
                # Parse YAML frontmatter to get episode metadata
                properties = extract_frontmatter_properties(content)

                # Ensure episode_number is an integer for proper sorting
                ep_num = properties.get("episode_number", 999)
                if isinstance(ep_num, str):
                    try:
                        ep_num = int(ep_num)
                    except (ValueError, TypeError):
                        ep_num = 999

                episodes_data.append({
                    "directory_name": episode_name,
                    "title": properties.get("title", episode_name),
                    "episode_number": ep_num,
                    "guest_name": properties.get("guest_name", ""),
                    "summary": properties.get("summary", ""),
                })

    # Count published vs planning episodes
    published_episodes = len([e for e in episodes_data if e.get("episode_number", 999) != 999])
    planning_episodes = len([e for e in episodes_data if e.get("episode_number", 999) == 999])

    stats = {
        "total_episodes": len(episodes_data),
        "published_episodes": published_episodes,
        "planning_episodes": planning_episodes,
    }

    # Sort by episode_number in descending order (newest first)
    episodes_data.sort(key=lambda x: int(x["episode_number"]) if isinstance(x["episode_number"], (int, float)) else 0, reverse=True)

    return templates.TemplateResponse(
        "episodes.html",
        {
            "request": request,
            "episodes": episodes_data,
            "stats": stats,
            "vault_name": config.vault_name,
            "active_section": "episodes",
        }
    )


@app.post("/episodes/import", response_class=HTMLResponse)
async def import_episode(
    request: Request,
    background_tasks: BackgroundTasks,
    episode_dir: str = Form(...),
    episode_number: Optional[int] = Form(None),
):
    """Import an episode directory."""
    from zettelkasten.utils.episode_manager import EpisodeManager

    try:
        episode_manager = EpisodeManager(config)
        episode_path, episode, file_mapping = episode_manager.import_existing_episode(
            episode_dir,
            episode_number=episode_number,
        )

        # Schedule index rebuild
        background_tasks.add_task(rebuild_indices_task)

        # Redirect to episodes page with success message
        set_flash(
            request,
            f"✓ Episode '{episode_dir}' imported successfully (Episode {episode.episode_number})",
            "success",
        )
        return RedirectResponse(url="/episodes", status_code=303)

    except ValueError as e:
        return templates.TemplateResponse(
            "episodes.html",
            {
                "request": request,
                "episodes": [],
                "stats": {"total_episodes": 0, "published_episodes": 0, "planning_episodes": 0},
                "vault_name": config.vault_name,
                "active_section": "episodes",
                "error": str(e),
            }
        )
    except Exception as e:
        error = f"Unexpected error: {str(e)}"
        return templates.TemplateResponse(
            "episodes.html",
            {
                "request": request,
                "episodes": [],
                "stats": {"total_episodes": 0, "published_episodes": 0, "planning_episodes": 0},
                "vault_name": config.vault_name,
                "active_section": "episodes",
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
            "flash_messages": get_flashed_messages(request),
            "active_section": "staging",
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
            "active_section": "staging",
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
            "active_section": "staging",
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
                "active_section": "staging",
            }
        )


@app.post("/staging/approve/{file_path:path}")
async def approve_staging_file(request: Request, file_path: str, background_tasks: BackgroundTasks):
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

        # Schedule index rebuild as background task
        background_tasks.add_task(rebuild_indices_task)

        # Set flash message
        set_flash(request, "✓ File approved successfully. Rebuilding indices in background...", "success")

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


@app.get("/create-note", response_class=HTMLResponse)
async def create_note_form(request: Request, error: Optional[str] = None):
    """Show the Create Note form."""
    return templates.TemplateResponse(
        "create_note.html",
        {
            "request": request,
            "vault_name": config.vault_name,
            "error": error,
            "active_section": "create-note",
        }
    )


@app.post("/create-note", response_class=HTMLResponse)
async def create_note_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    note_type: str = Form(...),
    auto_fill: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    reference_urls: Optional[str] = Form(None),
):
    """Process note creation."""
    from datetime import datetime
    from zettelkasten.generators.note_content_generator import NoteContentGenerator

    auto_fill_bool = auto_fill == "true"

    # Parse reference URLs (one per line)
    urls_list = None
    if reference_urls and reference_urls.strip():
        urls_list = [url.strip() for url in reference_urls.strip().split('\n') if url.strip()]

    try:
        # Check for duplicate notes (only for concept and person notes)
        if note_type in ["concept", "permanent", "permanent-note", "person", "contact"]:
            from zettelkasten.utils.vault_scanner import find_matching_concept

            existing_note = find_matching_concept(title, config)
            if existing_note:
                error = f"A note with a similar title already exists: '{existing_note['title']}' at {existing_note['filepath']}"
                return templates.TemplateResponse(
                    "create_note.html",
                    {
                        "request": request,
                        "vault_name": config.vault_name,
                        "error": error,
                        "active_section": "create-note",
                    }
                )

        # Validate API key if auto_fill is enabled
        if auto_fill_bool and (not config.anthropic_api_key or config.anthropic_api_key == "your_anthropic_api_key_here"):
            error = "ANTHROPIC_API_KEY not configured. Auto-fill requires an Anthropic API key in the .env file."
            return templates.TemplateResponse(
                "create_note.html",
                {
                    "request": request,
                    "vault_name": config.vault_name,
                    "error": error,
                    "active_section": "create-note",
                }
            )

        # Create timestamp
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y%m%d%H%M%S")

        # Generate filename
        slug = title.lower().replace(" ", "-")
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        filename = f"{timestamp_str}-{slug}.md"

        # Determine directory based on type
        note_type = note_type.lower()
        if note_type in ["concept", "permanent", "permanent-note"]:
            directory = config.get_permanent_notes_path()
            tags = ["concept", "permanent-note"]
        elif note_type in ["source", "literature"]:
            directory = config.get_sources_path()
            tags = ["source"]
        elif note_type in ["person", "contact"]:
            directory = config.get_permanent_notes_path()
            tags = ["person", "contact"]
        elif note_type in ["fleeting", "fleeting-note"]:
            directory = config.get_fleeting_notes_path()
            tags = ["fleeting", "fleeting-note"]
        else:
            error = f"Invalid note type '{note_type}'"
            return templates.TemplateResponse(
                "create_note.html",
                {
                    "request": request,
                    "vault_name": config.vault_name,
                    "error": error,
                    "active_section": "create-note",
                }
            )

        # Ensure directory exists
        directory.mkdir(parents=True, exist_ok=True)

        filepath = directory / filename

        # Check if file already exists
        if filepath.exists():
            error = f"File already exists: {filepath}"
            return templates.TemplateResponse(
                "create_note.html",
                {
                    "request": request,
                    "vault_name": config.vault_name,
                    "error": error,
                    "active_section": "create-note",
                }
            )

        # Build note content
        lines = []
        lines.append("---")
        lines.append(f"title: {title}")
        lines.append(f"created: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"tags: [{', '.join(tags)}]")
        lines.append("---")
        lines.append("")
        lines.append(f"# {title}")
        lines.append("")

        # Generate content based on note type and auto_fill flag
        content_generator = NoteContentGenerator(config)

        if note_type in ["concept", "permanent", "permanent-note"]:
            backlink_sources = None
            if auto_fill_bool:
                # Find backlinks from existing notes
                from zettelkasten.utils.orphan_finder import OrphanFinder
                finder = OrphanFinder(config.vault_path)
                backlink_sources = finder.find_backlinks(title)

            note_lines = content_generator.generate_concept_note_content(
                title,
                backlink_sources,
                auto_fill=auto_fill_bool,
                user_description=description,
                reference_urls=urls_list,
            )
            lines.extend(note_lines)

        elif note_type in ["source", "literature"]:
            note_lines = content_generator.generate_source_note_content(auto_fill=auto_fill_bool)
            lines.extend(note_lines)

        elif note_type in ["person", "contact"]:
            # Generate person note with URL context support
            note_lines = content_generator.generate_person_note_content(
                title,
                auto_fill=auto_fill_bool,
                research_data=None,
                user_description=description,
                reference_urls=urls_list,
            )
            lines.extend(note_lines)

        elif note_type in ["fleeting", "fleeting-note"]:
            note_lines = content_generator.generate_fleeting_note_content()
            lines.extend(note_lines)

        # Write file
        filepath.write_text("\n".join(lines))

        # Schedule index rebuild as background task
        background_tasks.add_task(rebuild_indices_task)

        # Set flash message
        set_flash(request, f"✓ Note created successfully: {filename}. Rebuilding indices in background...", "success")

        # Redirect to view the new note
        relative_path = filepath.relative_to(config.vault_path)
        return RedirectResponse(url=f"/note/{relative_path}", status_code=303)

    except Exception as e:
        error = f"Error creating note: {str(e)}"
        return templates.TemplateResponse(
            "create_note.html",
            {
                "request": request,
                "vault_name": config.vault_name,
                "error": error,
                "active_section": "create-note",
            }
        )


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


@app.get("/episode-media/{episode_name}/{file_path:path}")
async def serve_episode_media(episode_name: str, file_path: str):
    """
    Serve media files from episode directories, searching all configured episode paths.
    """
    # Search for the episode in all configured directories
    episode_path = config.find_episode_path(episode_name)

    if episode_path is None:
        raise HTTPException(status_code=404, detail=f"Episode directory not found: {episode_name}")

    # Construct full file path
    full_file_path = episode_path / file_path

    if not full_file_path.exists() or not full_file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    # Serve the file
    return FileResponse(full_file_path)


def fix_episode_media_links(html: str, note_path: str) -> str:
    """
    Fix relative links in episode pages to point to the /episode-media/ route.

    Converts links like <a href="file.mp4">file.mp4</a> to <a href="/episode-media/Grant Harris/file.mp4">file.mp4</a>
    """
    import re
    from urllib.parse import quote

    # Extract episode directory from note_path (e.g., "episodes/Grant Harris/index" -> "Grant Harris")
    parts = note_path.split('/')
    if len(parts) >= 2:
        episode_dir = parts[1]
    else:
        return html

    # Pattern to match <a href="relative-file">...</a>
    # We need to be more specific and look for file extensions
    # Exclude .md files so they go through the /note/ route for rendering
    pattern = r'<a href="([^"]+\.(mp4|wav|mp3|txt|png|jpg|jpeg|webp|pdf))">([^<]+)</a>'

    def replace_link(match):
        href = match.group(1)
        link_text = match.group(3)

        # Skip absolute URLs
        if href.startswith(('http://', 'https://', '/')):
            return match.group(0)

        # This is a relative file link - convert to /episode-media/ URL
        # URL-encode the episode directory name and filename
        encoded_episode = quote(episode_dir)
        encoded_file = quote(href)
        new_href = f"/episode-media/{encoded_episode}/{encoded_file}"

        return f'<a href="{new_href}">{link_text}</a>'

    return re.sub(pattern, replace_link, html, flags=re.IGNORECASE)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
