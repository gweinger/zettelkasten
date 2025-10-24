"""Main CLI interface for the Zettelkasten tool."""

import warnings
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

import typer
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
        help="Type of note: concept, source, or fleeting",
    ),
) -> None:
    """
    Create a new note with timestamp and proper structure.

    Creates a new markdown file with:
    - Timestamped filename
    - YAML frontmatter with metadata
    - Title heading
    - Stubbed sections for content
    - Automatic index update
    """
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
        elif note_type in ["fleeting", "fleeting-note"]:
            directory = config.get_fleeting_notes_path()
            tags = ["fleeting", "fleeting-note"]
        else:
            console.print(f"[bold red]Error:[/bold red] Invalid note type '{note_type}'")
            console.print("Valid types: concept, source, fleeting")
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
        lines.append("## Description")
        lines.append("")
        lines.append("<!-- Add your notes here -->")
        lines.append("")

        if note_type in ["concept", "permanent", "permanent-note"]:
            lines.append("## Key Quotes")
            lines.append("")
            lines.append("<!-- Add relevant quotes here -->")
            lines.append("")
            lines.append("## Sources")
            lines.append("")
            lines.append("<!-- Link to source notes here -->")
            lines.append("")

        lines.append("## Related Notes")
        lines.append("")
        lines.append("<!-- Link to related notes here -->")
        lines.append("")

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

            # Generate summary from Claude
            console.print("[dim]Generating summary from Claude...[/dim]")
            generator = OrphanNoteGenerator(config)
            updated_content = generator.fill_empty_note(orphan.filepath)

            # Write the updated content
            orphan.filepath.write_text(updated_content)

            console.print(f"\n[bold green]✓ Filled empty note:[/bold green]")
            console.print(f"  [cyan]{orphan.filepath.relative_to(config.vault_path)}[/cyan]")
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
                    updated_content = generator.fill_empty_note(orphan.filepath)
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


if __name__ == "__main__":
    app()
