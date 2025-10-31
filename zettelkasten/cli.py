"""Main CLI interface for the Zettelkasten tool."""

import warnings
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

import typer
import requests
from rich.console import Console
from pathlib import Path
from typing import Optional

from zettelkasten.core.config import Config
from zettelkasten.core.workflow import AddWorkflow, ImportWorkflow
from zettelkasten.generators.index_generator import IndexGenerator
from zettelkasten.generators.orphan_generator import OrphanNoteGenerator
from zettelkasten.utils.orphan_finder import OrphanFinder

app = typer.Typer(help="Zettelkasten CLI - Generate and manage your knowledge base")
console = Console()


def _perform_person_research(name: str) -> dict:
    """
    Perform web research on a person and gather professional information.

    Searches for:
    - Professional summary and background
    - Website and LinkedIn profile
    - Social media presence
    - Programs and ventures

    Args:
        name: Name of the person to research

    Returns:
        Dictionary with research findings
    """
    try:
        # Import here to avoid circular imports
        from zettelkasten.processors.concept_extractor import ConceptExtractor

        research_data = {
            'name': name,
            'summary': None,
            'background': None,
            'expertise': None,
            'digital_presence': {},
            'programs_ventures': [],
            'research_performed': False,
        }

        # Note: This function is designed to be called from the CLI
        # It uses WebSearch and WebFetch from the tools available to Claude
        # The actual implementation happens in the agent/assistant context
        # For now, return empty data structure that will be populated if called from Claude

        return research_data

    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Could not perform research: {e}")
        return {
            'name': name,
            'summary': None,
            'background': None,
            'expertise': None,
            'digital_presence': {},
            'programs_ventures': [],
            'research_performed': False,
        }


def merge_notes_intelligently(existing_content: str, new_content: str) -> str:
    """
    Merge two notes section by section instead of simple append.

    Sections handled:
    - Description (after title): Appended as new paragraph
    - Key Quotes: Merged together
    - Source/Sources: Combined into Sources section
    - Related Notes: Merged and deduplicated

    Args:
        existing_content: The existing note content
        new_content: The new content to merge in

    Returns:
        Merged note content
    """
    import re

    def parse_sections(content: str) -> dict:
        """Parse note into sections."""
        sections = {
            'frontmatter': '',
            'title': '',
            'description': '',
            'key_quotes': [],
            'sources': [],
            'related_notes': []
        }

        # Extract frontmatter
        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if fm_match:
            sections['frontmatter'] = fm_match.group(0)
            content = content[fm_match.end():]

        # Remove merge banner if present (lines starting with >)
        lines = content.split('\n')
        clean_lines = []
        in_banner = False
        for line in lines:
            if line.strip().startswith('> **⚠️ MERGE**'):
                in_banner = True
                continue
            if in_banner and line.strip().startswith('>'):
                continue
            if in_banner and not line.strip():
                in_banner = False
                continue
            clean_lines.append(line)
        content = '\n'.join(clean_lines)

        # Extract title
        title_match = re.match(r'^#\s+(.+?)\n\n', content, re.MULTILINE)
        if title_match:
            sections['title'] = title_match.group(1).strip()
            content = content[title_match.end():]

        # Split into sections by ## headers
        lines = content.split('\n')
        current_section = 'description'
        current_lines = []
        skip_mode = False

        for line in lines:
            # Skip old "## Additional Content" sections and horizontal rules
            if line.strip() == '---' and current_section == 'related_notes':
                skip_mode = True
                continue
            if skip_mode and line.startswith('## Additional Content'):
                # Reset - parse content after this as if it's a new note
                current_section = 'description'
                current_lines = []
                skip_mode = False
                continue
            if skip_mode and line.startswith('# '):
                # Found a title in additional content - skip it and continue
                skip_mode = False
                continue
            if skip_mode:
                continue

            if line.startswith('## '):
                # Save previous section
                if current_section == 'description' and current_lines:
                    sections['description'] = '\n'.join(current_lines).strip()
                elif current_section == 'key_quotes' and current_lines:
                    # Extract quotes (lines starting with >)
                    for l in current_lines:
                        l = l.strip()
                        if l.startswith('>'):
                            sections['key_quotes'].append(l)
                elif current_section == 'sources' and current_lines:
                    sections['sources'].extend([l.strip() for l in current_lines if l.strip() and not l.strip().startswith('#')])
                elif current_section == 'related_notes' and current_lines:
                    # Extract wiki links
                    for l in current_lines:
                        l = l.strip()
                        if l.startswith('-') and '[[' in l:
                            sections['related_notes'].append(l)

                current_lines = []

                # Determine new section
                header = line.lower()
                if 'key quote' in header:
                    current_section = 'key_quotes'
                elif 'source' in header:
                    current_section = 'sources'
                elif 'related note' in header:
                    current_section = 'related_notes'
                else:
                    current_section = 'other'
            else:
                current_lines.append(line)

        # Save last section
        if current_section == 'description' and current_lines:
            sections['description'] = '\n'.join(current_lines).strip()
        elif current_section == 'key_quotes' and current_lines:
            # Extract quotes (lines starting with >)
            for line in current_lines:
                line = line.strip()
                if line.startswith('>'):
                    sections['key_quotes'].append(line)
        elif current_section == 'sources' and current_lines:
            sections['sources'].extend([l.strip() for l in current_lines if l.strip() and not l.strip().startswith('#')])
        elif current_section == 'related_notes' and current_lines:
            # Extract wiki links
            for line in current_lines:
                line = line.strip()
                if line.startswith('-') and '[[' in line:
                    sections['related_notes'].append(line)

        return sections

    # Parse both notes
    existing = parse_sections(existing_content)
    new = parse_sections(new_content)

    # Build merged content
    lines = []

    # Frontmatter (keep existing)
    if existing['frontmatter']:
        lines.append(existing['frontmatter'].rstrip())
        lines.append('')

    # Title
    if existing['title']:
        lines.append(f"# {existing['title']}")
        lines.append('')

    # Description - merge both
    if existing['description']:
        lines.append(existing['description'])
        lines.append('')
    if new['description']:
        lines.append(new['description'])
        lines.append('')

    # Key Quotes - combine all quotes
    all_quotes = existing['key_quotes'] + new['key_quotes']
    if all_quotes:
        lines.append('## Key Quotes')
        lines.append('')
        for quote in all_quotes:
            lines.append(quote)
            lines.append('')

    # Sources - combine, deduplicate, and change to plural
    all_sources = existing['sources'] + new['sources']
    if all_sources:
        lines.append('## Sources')
        lines.append('')
        # Group sources - look for From: or URL: patterns
        current_source_group = []
        seen_urls = set()

        for source in all_sources:
            # Clean up "From:" prefix if present
            source = source.replace('From: ', '')
            if source and not source.startswith('##'):
                if source.startswith('URL:'):
                    # End of a source group
                    url = source.replace('URL:', '').strip()

                    # Only add if we haven't seen this URL before
                    if url not in seen_urls:
                        seen_urls.add(url)
                        current_source_group.append(source)
                        # Write the group
                        for line in current_source_group:
                            lines.append(line)
                        lines.append('')

                    # Reset for next group
                    current_source_group = []
                else:
                    current_source_group.append(source)

        # Handle any remaining sources
        if current_source_group:
            for line in current_source_group:
                lines.append(line)
            lines.append('')

    # Related Notes - merge and deduplicate
    all_related = existing['related_notes'] + new['related_notes']
    # Deduplicate by display text, keeping the most recent link (largest timestamp)
    seen_links = {}  # dedup_key -> (note, timestamp)

    for note in all_related:
        # Extract the wiki link for deduplication
        link_match = re.search(r'\[\[([^\]]+)\]\]', note)
        if link_match:
            link = link_match.group(1)
            # Check if link has display text (path|display)
            if '|' in link:
                # Use display text as dedup key (the part after |)
                dedup_key = link.split('|', 1)[1].strip()
                # Extract timestamp from path for comparison
                path_part = link.split('|', 1)[0]
                timestamp_match = re.search(r'(\d{14})', path_part)
                timestamp = timestamp_match.group(1) if timestamp_match else '00000000000000'
            else:
                # No display text, use the whole link as key
                dedup_key = link.strip()
                timestamp = '00000000000000'  # No timestamp

            # Keep the link with the largest (most recent) timestamp
            if dedup_key not in seen_links or timestamp > seen_links[dedup_key][1]:
                seen_links[dedup_key] = (note, timestamp)

    # Extract just the notes, sorted by their dedup key for consistency
    unique_related = [note for note, _ in sorted(seen_links.values(), key=lambda x: x[0])]

    if unique_related:
        lines.append('## Related Notes')
        lines.append('')
        for note in unique_related:
            lines.append(note)
        lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


@app.command()
def seed(
    rss_feed: Optional[str] = typer.Option(
        None,
        "--rss-feed",
        "-r",
        help="RSS feed URL (defaults to .env configuration)",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Limit number of episodes to process",
    ),
) -> None:
    """
    Bootstrap Zettelkasten from Powerful Introvert Podcast RSS feed.

    Downloads audio, generates transcripts, extracts concepts, and creates Zettelkasten files.
    """
    console.print("[bold green]Starting seed workflow...[/bold green]")
    console.print("This will download podcast episodes, transcribe them, and generate Zettelkasten files.")

    # TODO: Implement seed workflow
    console.print("[yellow]Not yet implemented[/yellow]")


@app.command()
def add(
    url: str = typer.Argument(..., help="URL to process (YouTube, podcast, or article)"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force reprocessing even if already exists",
    ),
) -> None:
    """
    Add content from a URL to your Zettelkasten.

    Supports YouTube videos, podcast episodes (Apple/Spotify), and blog articles.
    """
    try:
        # Load configuration
        config = Config.from_env()

        # Validate API key
        if not config.anthropic_api_key or config.anthropic_api_key == "your_anthropic_api_key_here":
            console.print(
                "[bold red]Error:[/bold red] ANTHROPIC_API_KEY not configured in .env file"
            )
            console.print("Please add your Anthropic API key to the .env file")
            raise typer.Exit(1)

        # Create workflow and process URL
        workflow = AddWorkflow(config)
        saved_paths = workflow.process_url(url, force=force)

        # Display results
        console.print("\n[bold green]Success![/bold green]")
        console.print(f"\nGenerated {len(saved_paths)} notes in staging area:")
        for path in saved_paths:
            relative_path = path.relative_to(config.vault_path)
            console.print(f"  [cyan]→[/cyan] {relative_path}")

        console.print(f"\n[dim]Staging location: {config.get_staging_path()}[/dim]")
        console.print("[yellow]Review and edit the notes, then run 'zk approve' to add them to your vault.[/yellow]")

    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {e}")
        console.print("\n[dim]Please check your configuration and try again.[/dim]")
        raise typer.Exit(1)


@app.command()
def new(
    title: str = typer.Argument(..., help="Title for the new note"),
    note_type: str = typer.Option(
        "concept",
        "--type",
        "-t",
        help="Type of note: concept, source, person, or fleeting",
    ),
    no_fill: bool = typer.Option(
        False,
        "--no-fill",
        help="Create empty template without auto-filling description and backlinks",
    ),
    no_research: bool = typer.Option(
        False,
        "--no-research",
        help="For person notes: create without web research (use with --type person)",
    ),
) -> None:
    """
    Create a new note with timestamp and proper structure.

    By default, creates notes with:
    - Timestamped filename
    - YAML frontmatter with metadata
    - Title heading
    - Auto-generated description (for concept notes)
    - Auto-discovered backlinks (for concept notes)
    - Automatic index update

    For concept notes:
    - Generates description using Claude
    - Finds and adds existing backlinks from other notes
    - Requires ANTHROPIC_API_KEY for description generation

    For person notes:
    - Performs web research and populates professional information
    - Extracts website, LinkedIn, social media presence
    - Lists programs and ventures
    - Use --no-research to skip research

    Use --no-fill flag to create empty templates instead.
    """
    # Set fill to opposite of no_fill
    fill = not no_fill
    try:
        from datetime import datetime
        from pathlib import Path

        # Load configuration
        config = Config.from_env()

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
            console.print(f"[bold red]Error:[/bold red] Invalid note type '{note_type}'")
            console.print("Valid types: concept, source, person, fleeting")
            raise typer.Exit(1)

        # Ensure directory exists
        directory.mkdir(parents=True, exist_ok=True)

        filepath = directory / filename

        # Check if file already exists
        if filepath.exists():
            console.print(f"[bold yellow]Warning:[/bold yellow] File already exists: {filepath}")
            raise typer.Exit(1)

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

        # Generate content based on note type and fill flag
        if note_type in ["concept", "permanent", "permanent-note"]:
            # For concept notes, use NoteContentGenerator for consistency
            from zettelkasten.generators.note_content_generator import NoteContentGenerator

            backlink_sources = None
            if fill:
                # Validate API key
                if not config.anthropic_api_key or config.anthropic_api_key == "your_anthropic_api_key_here":
                    console.print(
                        "[bold red]Error:[/bold red] ANTHROPIC_API_KEY not configured for --fill"
                    )
                    raise typer.Exit(1)

                # Find backlinks from existing notes
                from zettelkasten.utils.orphan_finder import OrphanFinder
                finder = OrphanFinder(config.vault_path)
                backlink_sources = finder.find_backlinks(title)

                if backlink_sources:
                    console.print(f"[dim]Found {len(backlink_sources)} note(s) that reference this concept[/dim]")

            content_generator = NoteContentGenerator(config)
            note_lines = content_generator.generate_concept_note_content(
                title, backlink_sources, auto_fill=fill
            )
            lines.extend(note_lines)

        elif note_type in ["source", "literature"]:
            from zettelkasten.generators.note_content_generator import NoteContentGenerator

            content_generator = NoteContentGenerator(config)
            note_lines = content_generator.generate_source_note_content(auto_fill=fill)
            lines.extend(note_lines)

        elif note_type in ["person", "contact"]:
            from zettelkasten.generators.note_content_generator import NoteContentGenerator

            research_data = None
            if fill and not no_research:
                # Perform web research on the person
                console.print(f"[dim]Researching {title}...[/dim]")
                research_data = _perform_person_research(title)
                if research_data.get('research_performed'):
                    console.print("[green]✓[/green] Research complete")
                elif research_data.get('summary'):
                    console.print("[yellow]⚠[/yellow] Partial research completed")

            content_generator = NoteContentGenerator(config)
            note_lines = content_generator.generate_person_note_content(
                title, auto_fill=fill, research_data=research_data
            )
            lines.extend(note_lines)

        elif note_type in ["fleeting", "fleeting-note"]:
            from zettelkasten.generators.note_content_generator import NoteContentGenerator

            content_generator = NoteContentGenerator(config)
            note_lines = content_generator.generate_fleeting_note_content()
            lines.extend(note_lines)

        # Write file
        filepath.write_text("\n".join(lines))

        console.print(f"[bold green]✓[/bold green] Created note: [cyan]{filepath.relative_to(config.vault_path)}[/cyan]")

        # Rebuild indices
        console.print("\n[dim]Rebuilding indices...[/dim]")
        try:
            from zettelkasten.generators.index_generator import IndexGenerator
            index_generator = IndexGenerator(config)
            indices = index_generator.rebuild_indices()
            console.print("[green]✓[/green] Indices updated")
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Warning: Could not rebuild indices: {e}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def approve(
    pattern: Optional[str] = typer.Argument(
        None,
        help="Pattern to match files (e.g., '*.md' or specific filename). If not provided, approves all staged files.",
    ),
    delete: bool = typer.Option(
        False,
        "--delete",
        "-d",
        help="Delete files from staging instead of moving them",
    ),
) -> None:
    """
    Review and approve staged notes, moving them to the vault.

    After processing content with 'zk add', notes are saved to staging/
    for review. Use this command to move reviewed notes to their final
    location in the vault (permanent-notes/ or sources/).
    """
    try:
        import shutil

        config = Config.from_env()
        staging_path = config.get_staging_path()

        # Find all markdown files in staging
        if pattern:
            # Use provided pattern
            if "*" in pattern:
                staged_files = list(staging_path.glob(f"**/{pattern}"))
            else:
                # Exact filename match
                staged_files = list(staging_path.glob(f"**/{pattern}"))
        else:
            # Get all markdown files
            staged_files = list(staging_path.glob("**/*.md"))

        if not staged_files:
            console.print("[yellow]No files found in staging area.[/yellow]")
            return

        console.print(f"\n[bold cyan]Found {len(staged_files)} file(s) in staging:[/bold cyan]\n")

        approved_count = 0
        deleted_count = 0

        for filepath in staged_files:
            relative_path = filepath.relative_to(staging_path)
            console.print(f"\n[bold]File:[/bold] {relative_path}")

            if delete:
                # Delete the file
                filepath.unlink()
                deleted_count += 1
                console.print(f"  [red]✗[/red] Deleted")
            else:
                # Check if this is a merge operation
                import re
                content = filepath.read_text()

                # Extract frontmatter
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
                    # This is a merge operation
                    target_path = config.get_permanent_notes_path() / merge_target
                    if target_path.exists():
                        # Read the existing note
                        existing_content = target_path.read_text()

                        # Extract new content (skip frontmatter and merge banner)
                        new_content_start = content.find('---', 3) + 3  # Skip first ---...---
                        new_content = content[new_content_start:].strip()

                        # Remove merge banner if present
                        if new_content.startswith('>'):
                            lines = new_content.split('\n')
                            # Skip lines starting with '>' (the banner)
                            new_content = '\n'.join([l for l in lines if not l.strip().startswith('>')])
                            new_content = new_content.strip()

                        # Intelligent section-by-section merge
                        merged_content = merge_notes_intelligently(existing_content, new_content)
                        target_path.write_text(merged_content)

                        # Delete the staging file
                        filepath.unlink()
                        approved_count += 1
                        console.print(f"  [blue]🔀[/blue] Merged into {merge_target}")
                    else:
                        console.print(f"  [yellow]⚠[/yellow] Target not found: {merge_target}, creating new instead")
                        # Fall back to creating new
                        destination_dir = config.get_permanent_notes_path()
                        destination = destination_dir / filepath.name
                        shutil.move(str(filepath), str(destination))
                        approved_count += 1
                        console.print(f"  [green]✓[/green] Created at {destination.relative_to(config.vault_path)}")
                else:
                    # Normal move operation
                    if "concepts" in filepath.parts:
                        destination_dir = config.get_permanent_notes_path()
                    elif "sources" in filepath.parts:
                        destination_dir = config.get_sources_path()
                    else:
                        destination_dir = config.vault_path

                    destination = destination_dir / filepath.name
                    shutil.move(str(filepath), str(destination))
                    approved_count += 1
                    console.print(f"  [green]✓[/green] Moved to {destination.relative_to(config.vault_path)}")

        # Summary
        console.print(f"\n[bold green]Complete![/bold green]")
        if approved_count > 0:
            console.print(f"Approved and moved: [green]{approved_count}[/green] file(s)")
        if deleted_count > 0:
            console.print(f"Deleted: [red]{deleted_count}[/red] file(s)")

        # Rebuild indices if any files were approved
        if approved_count > 0:
            console.print("\n[cyan]Rebuilding indices...[/cyan]")
            try:
                index_generator = IndexGenerator(config)
                indices = index_generator.rebuild_indices()
                console.print("[green]✓[/green] Indices updated")
            except Exception as e:
                console.print(f"[yellow]⚠[/yellow] Warning: Could not rebuild indices: {e}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def staging(
    show_content: bool = typer.Option(
        False,
        "--show-content",
        "-c",
        help="Show first few lines of each file",
    ),
    clean: bool = typer.Option(
        False,
        "--clean",
        help="Delete all files in the staging area",
    ),
) -> None:
    """
    List all files currently in the staging area.

    Shows files waiting for review before being approved into the vault.
    Use --clean to delete all staged files.
    """
    try:
        config = Config.from_env()
        staging_path = config.get_staging_path()

        # Find all markdown files in staging
        staged_files = list(staging_path.glob("**/*.md"))

        if not staged_files:
            console.print("[yellow]No files in staging area.[/yellow]")
            console.print("\n[dim]Process URLs with 'zk add <url>' to generate notes in staging.[/dim]")
            return

        # Handle clean option
        if clean:
            console.print(f"\n[bold yellow]⚠️  Warning:[/bold yellow] About to delete {len(staged_files)} file(s) from staging.\n")

            # Show what will be deleted
            for filepath in staged_files:
                relative_path = filepath.relative_to(staging_path)
                console.print(f"[red]✗[/red] {relative_path}")

            # Confirm deletion
            confirm = typer.confirm("\nAre you sure you want to delete all staged files?")
            if not confirm:
                console.print("[yellow]Cancelled.[/yellow]")
                return

            # Delete all files
            deleted_count = 0
            for filepath in staged_files:
                filepath.unlink()
                deleted_count += 1

            console.print(f"\n[bold green]Complete![/bold green]")
            console.print(f"Deleted: [red]{deleted_count}[/red] file(s)")
            return

        # List files in staging
        console.print(f"\n[bold cyan]Staging Area ({len(staged_files)} file(s)):[/bold cyan]\n")

        for filepath in staged_files:
            relative_path = filepath.relative_to(staging_path)
            console.print(f"[cyan]→[/cyan] {relative_path}")

            if show_content:
                # Show first 3 lines of content
                try:
                    with open(filepath, "r") as f:
                        lines = f.readlines()[:5]
                        for line in lines:
                            console.print(f"  [dim]{line.rstrip()}[/dim]")
                except Exception:
                    pass
                console.print()

        console.print(f"\n[dim]Staging location: {staging_path}[/dim]")
        console.print("[yellow]Run 'zk approve' to move these files to your vault.[/yellow]")
        console.print("[yellow]Run 'zk staging --clean' to delete all staged files.[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def init(
    vault_path: Path = typer.Option(
        "./vault",
        "--vault-path",
        "-v",
        help="Path to create Obsidian vault",
    ),
) -> None:
    """
    Initialize a new Zettelkasten vault with default structure.
    """
    console.print(f"[bold green]Initializing vault at:[/bold green] {vault_path}")

    # TODO: Implement vault initialization
    console.print("[yellow]Not yet implemented[/yellow]")


@app.command()
def index() -> None:
    """
    Rebuild index pages for concepts and sources.

    Generates two index files:
    - permanent-notes/INDEX.md: Alphabetical list of all concepts
    - sources/INDEX.md: Sources grouped by type (YouTube, Article, Podcast)
    """
    try:
        # Load configuration
        config = Config.from_env()

        console.print("[bold green]Rebuilding indices...[/bold green]\n")

        # Create index generator and rebuild
        generator = IndexGenerator(config)
        indices = generator.rebuild_indices()

        # Display results
        if indices:
            console.print("[bold green]Success![/bold green]\n")
            console.print("Generated index files:")
            for index_name, index_path in indices.items():
                console.print(f"  [cyan]→[/cyan] {index_path.relative_to(config.vault_path)}")
            console.print(f"\n[dim]Vault location: {config.vault_path}[/dim]")
        else:
            console.print("[yellow]No notes found to index.[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def process_inbox(
    delete: bool = typer.Option(
        False,
        "--delete",
        "-d",
        help="Delete processed files instead of archiving them",
    ),
) -> None:
    """
    Process notes from the inbox folder into your Zettelkasten.

    Analyzes each note, finds related concepts from your existing KB,
    adds proper formatting and links, then saves as a permanent note.
    Processed files are archived by default (or deleted with --delete).
    """
    try:
        # Load configuration
        config = Config.from_env()

        # Validate API key
        if not config.anthropic_api_key or config.anthropic_api_key == "your_anthropic_api_key_here":
            console.print(
                "[bold red]Error:[/bold red] ANTHROPIC_API_KEY not configured in .env file"
            )
            console.print("Please add your Anthropic API key to the .env file")
            raise typer.Exit(1)

        # Create workflow and process inbox
        workflow = ImportWorkflow(config)
        results = workflow.process_inbox(archive=not delete)

        # Display summary
        processed_count = len(results["processed"])
        failed_count = len(results["failed"])

        console.print("\n[bold green]Processing Complete![/bold green]\n")
        console.print(f"Successfully processed: [green]{processed_count}[/green] file(s)")
        if failed_count > 0:
            console.print(f"Failed: [red]{failed_count}[/red] file(s)")

        if processed_count > 0:
            console.print(f"\n[dim]Notes saved to: {config.get_permanent_notes_path()}[/dim]")
            if not delete:
                console.print(f"[dim]Processed files archived to: {config.get_inbox_path() / 'archive'}[/dim]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def clean_inbox() -> None:
    """
    Clean the inbox folders (concepts and sources), leaving archive untouched.

    Recursively removes all files and subdirectories from inbox/concepts/
    and inbox/sources/ but preserves the archive directory and README.md.
    """
    try:
        import shutil

        config = Config.from_env()
        inbox_path = config.get_inbox_path()

        concepts_dir = inbox_path / "concepts"
        sources_dir = inbox_path / "sources"

        deleted_items = 0

        # Clean concepts directory recursively
        if concepts_dir.exists():
            for item in concepts_dir.iterdir():
                if item.is_file():
                    item.unlink()
                    deleted_items += 1
                elif item.is_dir():
                    shutil.rmtree(item)
                    deleted_items += 1

        # Clean sources directory recursively
        if sources_dir.exists():
            for item in sources_dir.iterdir():
                if item.is_file():
                    item.unlink()
                    deleted_items += 1
                elif item.is_dir():
                    shutil.rmtree(item)
                    deleted_items += 1

        console.print(f"[bold green]Inbox cleaned![/bold green]")
        console.print(f"Removed {deleted_items} item(s) from concepts/ and sources/")
        console.print(f"\n[dim]Archive preserved at: {inbox_path / 'archive'}[/dim]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def config(
    show: bool = typer.Option(
        False,
        "--show",
        "-s",
        help="Show current configuration",
    ),
) -> None:
    """
    Manage configuration settings.
    """
    if show:
        try:
            cfg = Config.from_env()
            console.print("[bold]Current Configuration:[/bold]\n")

            # API Key (masked)
            api_key = cfg.anthropic_api_key
            if api_key and api_key != "your_anthropic_api_key_here":
                masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
                console.print(f"Anthropic API Key: [green]{masked_key}[/green]")
            else:
                console.print("Anthropic API Key: [red]Not configured[/red]")

            # Whisper model
            console.print(f"Whisper Model: {cfg.whisper_model_size}")

            # RSS Feed
            console.print(f"Podcast RSS Feed: {cfg.podcast_rss_feed or '[dim]Not set[/dim]'}")

            # Paths
            console.print(f"\nVault Path: [cyan]{cfg.vault_path}[/cyan]")
            console.print(f"Downloads Path: [cyan]{cfg.downloads_path}[/cyan]")
            console.print(f"Transcripts Path: [cyan]{cfg.transcripts_path}[/cyan]")

        except Exception as e:
            console.print(f"[bold red]Error loading configuration:[/bold red] {e}")
    else:
        console.print("Use --show to display current configuration")


@app.command()
def vault(
    action: str = typer.Argument(
        ...,
        help="Git action: status, commit, push, pull, log, or diff",
    ),
    message: Optional[str] = typer.Option(
        None,
        "--message",
        "-m",
        help="Commit message (for 'commit' action)",
    ),
    auto_add: bool = typer.Option(
        True,
        "--auto-add/--no-auto-add",
        help="Automatically add all changes before committing",
    ),
) -> None:
    """
    Manage vault version control with git.

    Examples:
        zk vault status              # Show vault git status
        zk vault commit -m "message" # Commit changes
        zk vault push                # Push to remote
        zk vault pull                # Pull from remote
        zk vault log                 # Show commit history
        zk vault diff                # Show uncommitted changes
    """
    import subprocess

    try:
        config = Config.from_env()
        vault_path = config.vault_path

        # Check if vault is a git repository
        git_dir = vault_path / ".git"
        if not git_dir.exists():
            console.print("[bold red]Error:[/bold red] Vault is not a git repository")
            console.print(f"\nInitialize it with: cd {vault_path} && git init")
            raise typer.Exit(1)

        # Map actions to git commands
        if action == "status":
            result = subprocess.run(
                ["git", "-C", str(vault_path), "status"],
                capture_output=True,
                text=True,
            )
            console.print(result.stdout)
            if result.returncode != 0:
                console.print(f"[red]{result.stderr}[/red]")
                raise typer.Exit(result.returncode)

        elif action == "commit":
            if not message:
                console.print("[bold red]Error:[/bold red] Commit message required")
                console.print("Use: zk vault commit -m \"your message\"")
                raise typer.Exit(1)

            # Auto-add changes if enabled
            if auto_add:
                console.print("[dim]Adding all changes...[/dim]")
                subprocess.run(
                    ["git", "-C", str(vault_path), "add", "."],
                    check=True,
                )

            # Commit
            result = subprocess.run(
                ["git", "-C", str(vault_path), "commit", "-m", message],
                capture_output=True,
                text=True,
            )
            console.print(result.stdout)
            if result.returncode != 0:
                console.print(f"[red]{result.stderr}[/red]")
                raise typer.Exit(result.returncode)
            else:
                console.print("[green]✓[/green] Changes committed successfully")

        elif action == "push":
            console.print("[dim]Pushing to remote...[/dim]")
            result = subprocess.run(
                ["git", "-C", str(vault_path), "push"],
                capture_output=True,
                text=True,
            )
            console.print(result.stdout)
            if result.returncode != 0:
                console.print(f"[red]{result.stderr}[/red]")
                raise typer.Exit(result.returncode)
            else:
                console.print("[green]✓[/green] Pushed to remote successfully")

        elif action == "pull":
            console.print("[dim]Pulling from remote...[/dim]")
            result = subprocess.run(
                ["git", "-C", str(vault_path), "pull"],
                capture_output=True,
                text=True,
            )
            console.print(result.stdout)
            if result.returncode != 0:
                console.print(f"[red]{result.stderr}[/red]")
                raise typer.Exit(result.returncode)
            else:
                console.print("[green]✓[/green] Pulled from remote successfully")

        elif action == "log":
            result = subprocess.run(
                ["git", "-C", str(vault_path), "log", "--oneline", "--graph", "--decorate", "-20"],
                capture_output=True,
                text=True,
            )
            console.print(result.stdout)
            if result.returncode != 0:
                console.print(f"[red]{result.stderr}[/red]")
                raise typer.Exit(result.returncode)

        elif action == "diff":
            result = subprocess.run(
                ["git", "-C", str(vault_path), "diff"],
                capture_output=True,
                text=True,
            )
            if result.stdout:
                console.print(result.stdout)
            else:
                console.print("[dim]No uncommitted changes[/dim]")
            if result.returncode != 0:
                console.print(f"[red]{result.stderr}[/red]")
                raise typer.Exit(result.returncode)

        else:
            console.print(f"[bold red]Error:[/bold red] Unknown action '{action}'")
            console.print("\nSupported actions: status, commit, push, pull, log, diff")
            raise typer.Exit(1)

    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Git error:[/bold red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def research_person(
    name: Optional[str] = typer.Argument(
        None,
        help="Name of the person note to research and populate (e.g., 'Vinh Giang')",
    ),
) -> None:
    """
    Research and populate a person note with professional information.

    This command performs web research on a specific person and populates their
    note with:
    - Professional summary
    - Background information
    - Areas of expertise
    - Digital presence (website, LinkedIn, social media)
    - Programs and ventures

    The person's note must already exist in your permanent-notes directory.

    Example:
        zk research-person "Vinh Giang"
    """
    try:
        from pathlib import Path
        import re

        if not name:
            console.print("[bold red]Error:[/bold red] Person name required")
            console.print("Usage: zk research-person \"Name\"")
            raise typer.Exit(1)

        config = Config.from_env()

        # Find the person note
        permanent_notes_path = config.get_permanent_notes_path()
        person_notes = list(permanent_notes_path.glob("**/*.md"))

        target_note = None
        for note_path in person_notes:
            with open(note_path, 'r') as f:
                first_line = f.readline()
                # Check for title match (case insensitive)
                if f"# {name}" in f.read() or first_line.strip() == f"# {name}":
                    target_note = note_path
                    break

        # Also try filename matching if title matching didn't work
        if not target_note:
            slug = name.lower().replace(" ", "-")
            slug = "".join(c for c in slug if c.isalnum() or c == "-")
            for note_path in person_notes:
                if slug in note_path.name.lower():
                    target_note = note_path
                    break

        if not target_note:
            console.print(f"[bold red]Error:[/bold red] Person note for '{name}' not found")
            console.print(f"Please create it first with: zk new \"{name}\" --type person")
            raise typer.Exit(1)

        console.print(f"\n[bold cyan]Researching:[/bold cyan] {name}")
        console.print(f"[dim]{target_note.relative_to(config.vault_path)}[/dim]")
        console.print()

        # Perform research
        console.print("[dim]Searching for professional information...[/dim]")
        research_data = _perform_person_research(name)

        if not research_data.get('research_performed') and not research_data.get('summary'):
            console.print("[yellow]⚠[/yellow] Web research not available in this context")
            console.print("[dim]Note: Research is performed when using 'zk new \"Name\" --type person'[/dim]")
            console.print("[dim]Or can be performed interactively by asking Claude to research the person[/dim]")
            raise typer.Exit(1)

        # Read existing note
        existing_content = target_note.read_text()

        # Generate new content with research data
        from zettelkasten.generators.note_content_generator import NoteContentGenerator

        content_generator = NoteContentGenerator(config)
        new_content_lines = content_generator.generate_person_note_content(
            name, auto_fill=True, research_data=research_data
        )

        # Merge with existing frontmatter
        lines = []

        # Extract and keep frontmatter
        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', existing_content, re.DOTALL)
        if fm_match:
            lines.append("---")
            lines.append(fm_match.group(1))
            lines.append("---")
            lines.append("")
        else:
            # No frontmatter, this shouldn't happen but handle it
            lines.append("---")
            lines.append(f"title: {name}")
            from datetime import datetime
            lines.append(f"created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("tags: [person, contact]")
            lines.append("---")
            lines.append("")

        # Add title and content
        lines.append(f"# {name}")
        lines.append("")
        lines.extend(new_content_lines)

        # Write updated note
        updated_content = "\n".join(lines)
        target_note.write_text(updated_content)

        console.print(f"\n[bold green]✓[/bold green] Updated person note")
        console.print(f"[dim]{target_note.relative_to(config.vault_path)}[/dim]")
        console.print("[yellow]Review and edit to add more details if needed.[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def orphans(
    action: str = typer.Argument(
        "list",
        help="Action: list, fill, or fill-all",
    ),
    name: Optional[str] = typer.Argument(
        None,
        help="Name of empty note (required for 'fill' action)",
    ),
    batch: bool = typer.Option(
        False,
        "--batch",
        "-b",
        help="Batch mode: fill all without prompting",
    ),
) -> None:
    """
    Find and fill empty concept notes with AI-generated summaries.

    Empty notes are stub files in permanent-notes/ that only have frontmatter
    and a title but no content. This command helps you find them and fill them
    with AI-generated summaries of the concept.

    Examples:
        zk orphans list               # Show all empty notes
        zk orphans fill "Concept"     # Fill specific empty note with summary
        zk orphans fill-all --batch   # Fill all empty notes without prompting
    """
    try:
        config = Config.from_env()

        # Validate API key for fill actions
        if action in ["fill", "fill-all"]:
            if not config.anthropic_api_key or config.anthropic_api_key == "your_anthropic_api_key_here":
                console.print(
                    "[bold red]Error:[/bold red] ANTHROPIC_API_KEY not configured in .env file"
                )
                console.print("Please add your Anthropic API key to the .env file")
                raise typer.Exit(1)

        # Initialize orphan finder
        finder = OrphanFinder(config.vault_path)

        if action == "list":
            # List all empty notes
            orphans_list = finder.find_orphans_with_context()

            if not orphans_list:
                console.print("[yellow]No empty notes found![/yellow]")
                console.print("\n[dim]All concept notes have content.[/dim]")
                return

            console.print(f"\n[bold cyan]Found {len(orphans_list)} empty note(s):[/bold cyan]\n")

            for orphan in orphans_list:
                console.print(f"[bold]{orphan['title']}[/bold]")
                console.print(f"  [dim]{orphan['relative_path']}[/dim]")

            console.print(f"\n[yellow]Run 'zk orphans fill \"Name\"' to fill a specific empty note.[/yellow]")

        elif action == "fill":
            if not name:
                console.print("[bold red]Error:[/bold red] Concept name required for 'fill' action")
                console.print("Usage: zk orphans fill \"Concept Name\"")
                raise typer.Exit(1)

            # Find the specific empty note
            orphans_list = finder.find_all_orphans()
            orphan = None
            for o in orphans_list:
                if o.title.lower() == name.lower():
                    orphan = o
                    break

            if not orphan:
                console.print(f"[bold red]Error:[/bold red] Empty note '{name}' not found")
                console.print("\nRun 'zk orphans list' to see all empty notes")
                raise typer.Exit(1)

            console.print(f"\n[bold cyan]Filling note:[/bold cyan] {orphan.title}")
            console.print(f"[dim]{orphan.filepath.relative_to(config.vault_path)}[/dim]")
            console.print()

            # Find backlinks to this concept from other notes
            console.print("[dim]Finding backlinks from other notes...[/dim]")
            backlink_sources = finder.find_backlinks(orphan.title)
            if backlink_sources:
                console.print(f"[dim]Found {len(backlink_sources)} note(s) that reference this concept[/dim]")

            # Generate summary from Claude
            console.print("[dim]Generating summary from Claude...[/dim]")
            generator = OrphanNoteGenerator(config)
            updated_content = generator.fill_empty_note(orphan.filepath, backlink_sources)

            # Write the updated content
            orphan.filepath.write_text(updated_content)

            console.print(f"\n[bold green]✓ Filled empty note:[/bold green]")
            console.print(f"  [cyan]{orphan.filepath.relative_to(config.vault_path)}[/cyan]")
            if backlink_sources:
                console.print(f"[dim]Added {len(backlink_sources)} backlink(s) to Related Notes[/dim]")
            console.print("[yellow]Review and edit the note to add more details if needed.[/yellow]")

        elif action == "fill-all":
            # Find all empty notes
            orphans_list = finder.find_all_orphans()

            if not orphans_list:
                console.print("[yellow]No empty notes found![/yellow]")
                return

            console.print(f"\n[bold cyan]Found {len(orphans_list)} empty note(s)[/bold cyan]\n")

            if not batch:
                # Show list and ask for confirmation
                for orphan in orphans_list:
                    console.print(f"  [cyan]→[/cyan] {orphan.title}")

                confirm = typer.confirm("\nFill all empty notes?")
                if not confirm:
                    console.print("[yellow]Cancelled.[/yellow]")
                    return

            # Generate and fill all notes
            generator = OrphanNoteGenerator(config)

            filled_count = 0
            failed_count = 0

            for orphan in orphans_list:
                try:
                    console.print(f"\n[dim]Filling: {orphan.title}...[/dim]")

                    # Find backlinks to this concept from other notes
                    backlink_sources = finder.find_backlinks(orphan.title)
                    if backlink_sources:
                        console.print(f"[dim]  Found {len(backlink_sources)} backlink(s)[/dim]")

                    updated_content = generator.fill_empty_note(orphan.filepath, backlink_sources)
                    orphan.filepath.write_text(updated_content)
                    console.print(f"[green]✓[/green] {orphan.filepath.relative_to(config.vault_path)}")
                    filled_count += 1
                except Exception as e:
                    console.print(f"[red]✗[/red] Failed to fill '{orphan.title}': {e}")
                    failed_count += 1

            # Summary
            console.print(f"\n[bold green]Complete![/bold green]")
            console.print(f"Filled: [green]{filled_count}[/green] note(s)")
            if failed_count > 0:
                console.print(f"Failed: [red]{failed_count}[/red] note(s)")

        else:
            console.print(f"[bold red]Error:[/bold red] Unknown action '{action}'")
            console.print("\nSupported actions: list, fill, fill-all")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def rss(
    action: str = typer.Argument(
        "status",
        help="Action: status, download, update, list, link, generate-episode-rss, or sync-all",
    ),
    episode_name: Optional[str] = typer.Argument(
        None,
        help="Episode name/directory (for link and generate-episode-rss actions)",
    ),
    url: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="RSS feed URL (for download/update)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force overwrite of existing file",
    ),
    rss_title: Optional[str] = typer.Option(
        None,
        "--title",
        "-t",
        help="Override RSS episode title (for generate-episode-rss)",
    ),
) -> None:
    """
    Manage podcast RSS feed and link episodes.

    Download and manage a local copy of the podcast RSS feed for reference,
    link episodes to RSS data, and generate episode-specific RSS files.

    Examples:
        zk rss status                              # Show RSS feed status
        zk rss download                            # Download RSS feed
        zk rss update                              # Update existing feed
        zk rss list                                # List episodes in feed
        zk rss link "Grant Harris"                 # Link episode to RSS feed
        zk rss generate-episode-rss "Grant Harris" # Generate episode.rss file
        zk rss sync-all                            # Sync all episodes with RSS
    """
    try:
        from zettelkasten.utils.rss_manager import RSSManager

        config = Config.from_env()
        rss_manager = RSSManager(config)

        if action == "status":
            console.print("\n[bold cyan]RSS Feed Status[/bold cyan]\n")

            # Check if feed file exists
            if rss_manager.rss_feed_file.exists():
                try:
                    info = rss_manager.get_feed_info()
                    console.print(f"[green]✓ Local feed found[/green]")
                    console.print(f"  [cyan]Location:[/cyan] {info['file_path']}")
                    console.print(f"  [cyan]Podcast:[/cyan] {info['podcast_title']}")
                    console.print(f"  [cyan]Episodes:[/cyan] {info['episode_count']}")
                    console.print(f"  [cyan]Size:[/cyan] {info['file_size_kb']:.1f} KB")
                    console.print(f"  [cyan]Last updated:[/cyan] {info['last_modified'].strftime('%Y-%m-%d %H:%M:%S')}")
                except Exception as e:
                    console.print(f"[red]✗ Error reading feed:[/red] {e}")
            else:
                console.print(f"[yellow]ℹ No local feed found[/yellow]")
                console.print(f"  Location: {rss_manager.rss_feed_file}")

            # Show configured feed URL
            if rss_manager.rss_feed_url:
                console.print(f"\n[cyan]Configured URL:[/cyan]")
                console.print(f"  {rss_manager.rss_feed_url}")
            else:
                console.print(f"\n[yellow]⚠ No RSS feed URL configured[/yellow]")
                console.print(f"  Set PODCAST_RSS_FEED in .env file")
            console.print()

        elif action == "download":
            feed_url = url or rss_manager.rss_feed_url
            if not feed_url:
                console.print("[bold red]Error:[/bold red] No URL provided")
                console.print("  Either pass --url or set PODCAST_RSS_FEED in .env")
                raise typer.Exit(1)

            # Check if file exists
            if rss_manager.rss_feed_file.exists() and not force:
                console.print("[bold red]Error:[/bold red] RSS feed file already exists")
                console.print(f"  {rss_manager.rss_feed_file}")
                console.print("  Use --force to overwrite")
                raise typer.Exit(1)

            console.print(f"\n[bold cyan]Downloading RSS feed[/bold cyan]")
            console.print(f"[dim]URL: {feed_url}[/dim]\n")

            try:
                file_path, info = rss_manager.download_feed(url=feed_url, overwrite=force)
                console.print(f"[green]✓ Feed downloaded successfully[/green]")
                console.print(f"  [cyan]Location:[/cyan] {file_path}")
                console.print(f"  [cyan]Podcast:[/cyan] {info['podcast_title']}")
                console.print(f"  [cyan]Episodes:[/cyan] {info['episode_count']}")
                console.print(f"  [cyan]Size:[/cyan] {info['file_size_kb']:.1f} KB")
                console.print()

            except requests.RequestException as e:
                console.print(f"[bold red]Error:[/bold red] Failed to download feed")
                console.print(f"  {e}")
                raise typer.Exit(1)

        elif action == "update":
            if not rss_manager.rss_feed_url:
                console.print("[bold red]Error:[/bold red] No RSS feed URL configured")
                console.print("  Set PODCAST_RSS_FEED in .env")
                raise typer.Exit(1)

            console.print(f"\n[bold cyan]Updating RSS feed[/bold cyan]")
            console.print(f"[dim]URL: {rss_manager.rss_feed_url}[/dim]\n")

            try:
                file_path, info = rss_manager.download_feed(overwrite=True)
                console.print(f"[green]✓ Feed updated successfully[/green]")
                console.print(f"  [cyan]Location:[/cyan] {file_path}")
                console.print(f"  [cyan]Podcast:[/cyan] {info['podcast_title']}")
                console.print(f"  [cyan]Episodes:[/cyan] {info['episode_count']}")
                console.print(f"  [cyan]Size:[/cyan] {info['file_size_kb']:.1f} KB")
                console.print()

            except requests.RequestException as e:
                console.print(f"[bold red]Error:[/bold red] Failed to update feed")
                console.print(f"  {e}")
                raise typer.Exit(1)

        elif action == "list":
            if not rss_manager.rss_feed_file.exists():
                console.print("[bold red]Error:[/bold red] No local RSS feed found")
                console.print(f"  Run: zk rss download")
                raise typer.Exit(1)

            try:
                episodes = rss_manager.list_episodes()
                console.print(f"\n[bold cyan]Episodes in RSS feed ({len(episodes)})[/bold cyan]\n")

                for idx, ep in enumerate(episodes, 1):
                    console.print(f"[bold]{idx}.[/bold] {ep['title']}")
                    if ep['pub_date']:
                        console.print(f"   [dim]{ep['pub_date']}[/dim]")
                    if ep['duration']:
                        console.print(f"   [cyan]Duration:[/cyan] {ep['duration']}")
                console.print()

            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                raise typer.Exit(1)

        elif action == "link":
            if not episode_name:
                console.print("[bold red]Error:[/bold red] Episode name required for 'link' action")
                console.print("Usage: zk rss link \"Episode Name\"")
                raise typer.Exit(1)

            if not rss_manager.rss_feed_file.exists():
                console.print("[bold red]Error:[/bold red] No local RSS feed found")
                console.print("  Run: zk rss download")
                raise typer.Exit(1)

            console.print(f"\n[bold cyan]Linking episode to RSS feed[/bold cyan]")
            console.print(f"[dim]Episode: {episode_name}[/dim]\n")

            try:
                # Find matching episode in RSS feed
                rss_episode = rss_manager.find_matching_episode(episode_name)
                if not rss_episode:
                    console.print(f"[bold red]Error:[/bold red] No matching episode found in RSS feed")
                    console.print(f"  Searched for: {episode_name}")
                    raise typer.Exit(1)

                # Find episode directory
                episode_path = config.find_episode_path(episode_name)
                if not episode_path:
                    console.print(f"[bold red]Error:[/bold red] Episode directory not found")
                    console.print(f"  Searched for: {episode_name}")
                    raise typer.Exit(1)

                # Read current index.md
                index_file = episode_path / "index.md"
                if not index_file.exists():
                    console.print(f"[bold red]Error:[/bold red] index.md not found in episode directory")
                    raise typer.Exit(1)

                # Parse YAML frontmatter
                import yaml
                content = index_file.read_text(encoding='utf-8')
                parts = content.split('---')
                if len(parts) < 3:
                    console.print(f"[bold red]Error:[/bold red] Invalid frontmatter in index.md")
                    raise typer.Exit(1)

                frontmatter_str = parts[1]
                body = '---'.join(parts[2:])
                frontmatter = yaml.safe_load(frontmatter_str) or {}

                # Add RSS metadata
                frontmatter['rss_title'] = rss_episode['title']
                frontmatter['rss_description'] = rss_episode['description'][:500]  # Truncate long descriptions
                frontmatter['rss_date'] = rss_episode['pub_date']

                # Write back updated frontmatter
                new_frontmatter = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
                updated_content = f"---\n{new_frontmatter}---{body}"
                index_file.write_text(updated_content, encoding='utf-8')

                console.print(f"[green]✓ Episode linked successfully[/green]")
                console.print(f"  [cyan]Episode:[/cyan] {rss_episode['title']}")
                console.print(f"  [cyan]Published:[/cyan] {rss_episode['pub_date']}")
                console.print(f"  [cyan]Updated:[/cyan] {index_file}")
                console.print()

            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                raise typer.Exit(1)

        elif action == "sync-all":
            if not rss_manager.rss_feed_file.exists():
                console.print("[bold red]Error:[/bold red] No local RSS feed found")
                console.print("  Run: zk rss download")
                raise typer.Exit(1)

            console.print(f"\n[bold cyan]Syncing all episodes with RSS feed[/bold cyan]\n")

            try:
                from zettelkasten.utils.episode_manager import EpisodeManager
                import yaml

                episode_manager = EpisodeManager(config)
                episodes = episode_manager.list_episodes()

                if not episodes:
                    console.print("[yellow]No episodes found to sync[/yellow]")
                    raise typer.Exit(0)

                linked_count = 0
                rss_generated_count = 0
                failed_episodes = []

                for episode_name in episodes:
                    try:
                        # Try to link to RSS
                        rss_episode = rss_manager.find_matching_episode(episode_name)
                        episode_path = config.find_episode_path(episode_name)

                        if rss_episode and episode_path:
                            index_file = episode_path / "index.md"
                            if index_file.exists():
                                # Link RSS data
                                content = index_file.read_text(encoding='utf-8')
                                parts = content.split('---')
                                if len(parts) >= 3:
                                    frontmatter_str = parts[1]
                                    body = '---'.join(parts[2:])
                                    frontmatter = yaml.safe_load(frontmatter_str) or {}

                                    frontmatter['rss_title'] = rss_episode['title']
                                    frontmatter['rss_description'] = rss_episode['description'][:500]
                                    frontmatter['rss_date'] = rss_episode['pub_date']

                                    new_frontmatter = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
                                    updated_content = f"---\n{new_frontmatter}---{body}"
                                    index_file.write_text(updated_content, encoding='utf-8')

                                    linked_count += 1

                                    # Generate episode.rss
                                    output_path = episode_path / "episode.rss"
                                    rss_manager.create_episode_rss(rss_episode, output_path)
                                    rss_generated_count += 1

                    except Exception as e:
                        failed_episodes.append((episode_name, str(e)))

                console.print(f"[green]✓ Sync complete[/green]")
                console.print(f"  [cyan]Linked:[/cyan] {linked_count} episodes")
                console.print(f"  [cyan]RSS files generated:[/cyan] {rss_generated_count}")

                if failed_episodes:
                    console.print(f"\n[yellow]⚠ {len(failed_episodes)} episodes failed:[/yellow]")
                    for name, error in failed_episodes:
                        console.print(f"  [dim]{name}: {error}[/dim]")

                console.print()

            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                raise typer.Exit(1)

        elif action == "generate-episode-rss":
            if not episode_name:
                console.print("[bold red]Error:[/bold red] Episode name required for 'generate-episode-rss' action")
                console.print("Usage: zk rss generate-episode-rss \"Episode Name\"")
                raise typer.Exit(1)

            if not rss_manager.rss_feed_file.exists():
                console.print("[bold red]Error:[/bold red] No local RSS feed found")
                console.print("  Run: zk rss download")
                raise typer.Exit(1)

            console.print(f"\n[bold cyan]Generating episode RSS file[/bold cyan]")
            console.print(f"[dim]Episode: {episode_name}[/dim]\n")

            try:
                # Find matching episode in RSS feed
                rss_episode = rss_manager.find_matching_episode(episode_name)
                if not rss_episode:
                    console.print(f"[bold red]Error:[/bold red] No matching episode found in RSS feed")
                    console.print(f"  Searched for: {episode_name}")
                    raise typer.Exit(1)

                # Find episode directory
                episode_path = config.find_episode_path(episode_name)
                if not episode_path:
                    console.print(f"[bold red]Error:[/bold red] Episode directory not found")
                    console.print(f"  Searched for: {episode_name}")
                    raise typer.Exit(1)

                # Use override title if provided
                if rss_title:
                    rss_episode['title'] = rss_title

                # Generate episode.rss file
                output_path = episode_path / "episode.rss"
                rss_manager.create_episode_rss(rss_episode, output_path)

                console.print(f"[green]✓ Episode RSS file generated[/green]")
                console.print(f"  [cyan]Title:[/cyan] {rss_episode['title']}")
                console.print(f"  [cyan]File:[/cyan] {output_path}")
                console.print(f"  [cyan]Size:[/cyan] {output_path.stat().st_size} bytes")
                console.print()

            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                raise typer.Exit(1)

        else:
            console.print(f"[bold red]Error:[/bold red] Unknown action '{action}'")
            console.print("\nSupported actions: status, download, update, list, link, generate-episode-rss, sync-all")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def episode(
    action: str = typer.Argument(
        "list",
        help="Action: new, list, show, import, or remove",
    ),
    name: Optional[str] = typer.Argument(
        None,
        help="Episode name (guest name or title for 'new' and 'show' actions)",
    ),
    title: Optional[str] = typer.Option(
        None,
        "--title",
        "-t",
        help="Episode title (defaults to guest name)",
    ),
    episode_number: Optional[int] = typer.Option(
        None,
        "--number",
        "-n",
        help="Episode number",
    ),
    summary: Optional[str] = typer.Option(
        None,
        "--summary",
        "-s",
        help="Brief episode summary",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force removal without confirmation (for 'remove' action)",
    ),
) -> None:
    """
    Manage podcast episodes.

    Create new episode directories with all necessary files and templates,
    list existing episodes, show details of a specific episode, import
    existing episode directories, or remove episodes from the index.

    Examples:
        zk episode new "Amanda Wild" --title "Leadership" --number 42
        zk episode list
        zk episode show "Amanda Wild"
        zk episode import "Grant Harris"
        zk episode remove "Anna Gradie"
        zk episode remove "Anna Gradie" --force
    """
    try:
        from zettelkasten.core.models import Episode
        from zettelkasten.utils.episode_manager import EpisodeManager

        config = Config.from_env()
        episode_manager = EpisodeManager(config)

        if action == "new":
            if not name:
                console.print("[bold red]Error:[/bold red] Episode name required for 'new' action")
                console.print("Usage: zk episode new \"Guest Name\" [--title TITLE] [--number NUM]")
                raise typer.Exit(1)

            # Create Episode model
            episode_model = Episode(
                title=title or name,
                guest_name=name,
                episode_number=episode_number,
                summary=summary,
            )

            # Create episode directory
            console.print(f"\n[bold cyan]Creating episode:[/bold cyan] {episode_model.title}")
            if episode_model.guest_name:
                console.print(f"[dim]Guest: {episode_model.guest_name}[/dim]")
            console.print()

            try:
                episode_dir = episode_manager.create_episode_directory(episode_model)
                console.print(f"[bold green]✓ Created episode directory:[/bold green]")
                console.print(f"  [cyan]{episode_dir}[/cyan]")
                console.print()

                # List created files
                console.print("[bold]Created files:[/bold]")
                console.print(f"  [green]→[/green] index.md")
                if episode_model.prep_transcript:
                    console.print(f"  [green]→[/green] {episode_model.prep_transcript}")
                if episode_model.interview_questions:
                    console.print(f"  [green]→[/green] {episode_model.interview_questions}")
                if episode_model.rss_description:
                    console.print(f"  [green]→[/green] {episode_model.rss_description}")
                if episode_model.youtube_description:
                    console.print(f"  [green]→[/green] {episode_model.youtube_description}")
                if episode_model.substack_description:
                    console.print(f"  [green]→[/green] {episode_model.substack_description}")
                console.print(f"  [green]→[/green] promos/")
                console.print()

                console.print("[yellow]Next steps:[/yellow]")
                console.print(f"  1. Edit the episode files in: {episode_dir}")
                console.print(f"  2. Add media files (video, audio, transcripts) to the episode directory")
                console.print(f"  3. Update index.md with production details")

            except ValueError as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                raise typer.Exit(1)

        elif action == "list":
            episodes = episode_manager.list_episodes()

            if not episodes:
                console.print("[yellow]No episodes found.[/yellow]")
                console.print("\n[dim]Create a new episode with:[/dim]")
                console.print("[dim]  zk episode new \"Guest Name\"[/dim]")
                return

            console.print(f"\n[bold cyan]Episodes ({len(episodes)}):[/bold cyan]\n")
            for ep in episodes:
                console.print(f"  [green]→[/green] {ep}")
            console.print()

        elif action == "show":
            if not name:
                console.print("[bold red]Error:[/bold red] Episode name required for 'show' action")
                console.print("Usage: zk episode show \"Episode Name\"")
                raise typer.Exit(1)

            episode_dir = config.get_episode_dir(name)
            if not episode_dir.exists():
                console.print(f"[bold red]Error:[/bold red] Episode '{name}' not found")
                console.print("\nRun 'zk episode list' to see all episodes")
                raise typer.Exit(1)

            # Show episode directory contents
            console.print(f"\n[bold cyan]Episode:[/bold cyan] {name}")
            console.print(f"[dim]{episode_dir}[/dim]\n")

            console.print("[bold]Files:[/bold]")
            for file in sorted(episode_dir.rglob("*")):
                if file.is_file():
                    rel_path = file.relative_to(episode_dir)
                    console.print(f"  [green]→[/green] {rel_path}")
            console.print()

        elif action == "import":
            if not name:
                console.print("[bold red]Error:[/bold red] Episode name required for 'import' action")
                console.print("Usage: zk episode import \"Episode Directory Name\"")
                raise typer.Exit(1)

            console.print(f"\n[bold cyan]Importing episode:[/bold cyan] {name}")
            console.print(f"[dim]Scanning directory for files...[/dim]\n")

            try:
                episode_dir, episode, file_mapping = episode_manager.import_existing_episode(
                    name,
                    episode_number=episode_number
                )

                console.print(f"[bold green]✓ Successfully imported episode![/bold green]")
                console.print(f"  [cyan]{episode_dir}[/cyan]\n")

                # Show detected files
                console.print("[bold]Detected files:[/bold]")
                if episode.episode_number:
                    console.print(f"  [yellow]Episode Number:[/yellow] {episode.episode_number}")

                if file_mapping['video']:
                    size_mb = file_mapping['video'].stat().st_size / (1024 * 1024)
                    console.print(f"  [green]→[/green] Video: {file_mapping['video'].name} ({size_mb:.1f} MB)")

                if file_mapping['audio']:
                    size_mb = file_mapping['audio'].stat().st_size / (1024 * 1024)
                    console.print(f"  [green]→[/green] Audio: {file_mapping['audio'].name} ({size_mb:.1f} MB)")

                if file_mapping['transcript']:
                    console.print(f"  [green]→[/green] Transcript: {file_mapping['transcript'].name}")

                if file_mapping['promos']:
                    console.print(f"  [green]→[/green] Promos: {len(file_mapping['promos'])} image(s) moved to promos/")

                console.print()
                console.print("[bold]Created files:[/bold]")
                console.print(f"  [green]→[/green] index.md")
                console.print(f"  [green]→[/green] prep conversation transcript.txt")
                console.print(f"  [green]→[/green] interview questions.md")
                console.print(f"  [green]→[/green] RSS description.md")
                console.print(f"  [green]→[/green] YouTube description.md")
                console.print(f"  [green]→[/green] Substack description.md")
                console.print()

                # Check if RSS data was linked
                try:
                    from zettelkasten.utils.rss_manager import RSSManager
                    rss_manager = RSSManager(config)
                    if rss_manager.rss_feed_file.exists():
                        rss_episode = rss_manager.find_matching_episode(name)
                        if rss_episode:
                            console.print("[bold green]✓ RSS feed data linked:[/bold green]")
                            console.print(f"  [cyan]Title:[/cyan] {rss_episode['title']}")
                            console.print(f"  [cyan]Published:[/cyan] {rss_episode['pub_date']}")
                            console.print()
                except Exception:
                    pass

                console.print("[yellow]Next steps:[/yellow]")
                console.print(f"  1. Review index.md and update episode metadata")
                console.print(f"  2. Fill in the description templates (RSS, YouTube, Substack)")
                console.print(f"  3. Add interview questions to interview questions.md")

                # Rebuild indices to include the new episode
                console.print()
                console.print("[dim]Rebuilding indices...[/dim]")
                from zettelkasten.generators.index_generator import IndexGenerator
                index_gen = IndexGenerator(config)
                index_gen.rebuild_indices()
                console.print("[green]✓ Indices updated[/green]")

            except ValueError as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                raise typer.Exit(1)

        elif action == "remove":
            if not name:
                console.print("[bold red]Error:[/bold red] Episode name required for 'remove' action")
                console.print("Usage: zk episode remove \"Episode Name\" [--force]")
                raise typer.Exit(1)

            console.print(f"\n[bold cyan]Removing episode from index:[/bold cyan] {name}")

            try:
                # Find episode directory
                episode_path = config.find_episode_path(name)
                if not episode_path:
                    console.print(f"[bold red]Error:[/bold red] Episode '{name}' not found")
                    raise typer.Exit(1)

                index_file = episode_path / "index.md"
                if not index_file.exists():
                    console.print(f"[bold red]Error:[/bold red] index.md not found in episode directory")
                    console.print(f"  Path: {episode_path}")
                    raise typer.Exit(1)

                # Show what will be deleted
                console.print(f"[dim]Episode path: {episode_path}[/dim]")
                console.print(f"[dim]Will delete: {index_file}[/dim]\n")

                # Confirm deletion
                if not force:
                    console.print("[yellow]⚠ This will remove the episode from the index[/yellow]")
                    console.print("[yellow]The episode directory and other files will remain unchanged[/yellow]")
                    confirm = typer.confirm("Are you sure you want to remove this episode from the index?")
                    if not confirm:
                        console.print("[dim]Cancelled[/dim]")
                        raise typer.Exit(0)

                # Delete the index file
                index_file.unlink()
                console.print(f"[green]✓ Episode removed from index[/green]")
                console.print(f"  [dim]{index_file}[/dim]\n")

                # Rebuild indices
                console.print("[dim]Rebuilding indices...[/dim]")
                from zettelkasten.generators.index_generator import IndexGenerator
                index_gen = IndexGenerator(config)
                index_gen.rebuild_indices()
                console.print("[green]✓ Indices updated[/green]")
                console.print()

            except ValueError as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                raise typer.Exit(1)
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                raise typer.Exit(1)

        else:
            console.print(f"[bold red]Error:[/bold red] Unknown action '{action}'")
            console.print("\nSupported actions: new, list, show, import, remove")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def generate_questions(
    guest_name: str = typer.Argument(
        ...,
        help="Name of the guest/interviewee",
    ),
    transcript_path: Optional[str] = typer.Option(
        None,
        "--transcript",
        "-t",
        help="Path to the prep conversation transcript (optional)",
    ),
    background: Optional[str] = typer.Option(
        None,
        "--background",
        "-b",
        help="Guest background information (optional)",
    ),
    key_topics: Optional[str] = typer.Option(
        None,
        "--topics",
        "-k",
        help="Key topics to discuss (optional)",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (optional, will save questions to file)",
    ),
) -> None:
    """
    Generate interview questions for a podcast episode using Claude AI.

    Analyzes the guest's background and creates thoughtful interview questions
    based on the podcast's theme and SEO keywords.

    Examples:
        zk generate-questions "Guest Name"
        zk generate-questions "Guest Name" --transcript path/to/prep-transcript.txt
        zk generate-questions "Guest Name" --background "Background info" --topics "Topic 1, Topic 2"
        zk generate-questions "Guest Name" --output interview-questions.md
    """
    try:
        from zettelkasten.utils.interview_generator import InterviewQuestionGenerator

        config = Config.from_env()
        generator = InterviewQuestionGenerator(config)

        console.print(f"\n[bold cyan]Generating interview questions for:[/bold cyan] {guest_name}")
        console.print()

        # Find the prep transcript file
        transcript_file = None
        if transcript_path:
            # User provided explicit path
            transcript_file = Path(transcript_path)
            if not transcript_file.exists():
                console.print(f"[bold red]Error:[/bold red] Transcript file not found: {transcript_path}")
                raise typer.Exit(1)
        else:
            # Try to find prep transcript in episode directory
            episode_path = config.find_episode_path(guest_name)
            if not episode_path:
                console.print(f"[bold red]Error:[/bold red] Episode directory not found for '{guest_name}'")
                console.print("[dim]Use --transcript to specify the prep conversation transcript path[/dim]")
                raise typer.Exit(1)

            # Look for prep transcript file with common naming patterns
            for potential_name in ["prep conversation transcript.txt", "prep conversation transcript.md", "prep-transcript.txt"]:
                potential_file = episode_path / potential_name
                if potential_file.exists():
                    transcript_file = potential_file
                    break

            # Also check for any file matching pattern like "*pre*.txt" or "*prep*.txt"
            if not transcript_file:
                import glob
                for pattern in ["*pre*.txt", "*pre*.md", "*prep*.txt", "*prep*.md"]:
                    matches = list(episode_path.glob(pattern))
                    if matches:
                        transcript_file = matches[0]
                        break

        # Require transcript
        if not transcript_file or not transcript_file.exists():
            console.print(f"[bold red]Error:[/bold red] Prep conversation transcript not found for '{guest_name}'")
            console.print("[dim]Expected one of these files in the episode directory:[/dim]")
            console.print("[dim]  - prep conversation transcript.txt[/dim]")
            console.print("[dim]  - prep-transcript.txt[/dim]")
            console.print("[dim]  - Any file matching *pre*.txt or *prep*.txt[/dim]")
            console.print("[dim]Or use --transcript to specify the path explicitly[/dim]")
            raise typer.Exit(1)

        console.print(f"[dim]Using transcript: {transcript_file}[/dim]")
        console.print("[dim]Analyzing transcript and generating questions with Claude...[/dim]")
        console.print()

        questions = generator.generate_questions(
            guest_name=guest_name,
            transcript_path=transcript_file,
            background=background,
            key_topics=key_topics,
        )

        # Display the questions
        console.print(questions)
        console.print()

        # Determine where to save
        save_path = None

        # If output path specified, use that
        if output:
            save_path = Path(output)
        else:
            # Try to find episode directory and save there
            episode_path = config.find_episode_path(guest_name)
            if episode_path:
                save_path = episode_path / "interview questions.md"

        # Save to file if path determined
        if save_path:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            generator.save_questions(questions, save_path)
            console.print(f"[bold green]✓ Questions saved to:[/bold green] {save_path}")
            console.print()
        else:
            console.print("[dim]Tip: Use --output to save questions to a file[/dim]")
            console.print()

        # Ensure episode index.md exists
        episode_path = config.find_episode_path(guest_name)
        if episode_path:
            generator.ensure_episode_index(guest_name, episode_path)

        # Create person note if it doesn't exist
        generator.ensure_person_note(guest_name)

        # Rebuild indices to add the episode and person to the knowledge base
        console.print("[dim]Rebuilding indices to add episode and person...[/dim]")
        from zettelkasten.generators.index_generator import IndexGenerator
        index_generator = IndexGenerator(config)
        index_generator.rebuild_indices()
        console.print(f"[bold green]✓ Indices rebuilt[/bold green]")

    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
