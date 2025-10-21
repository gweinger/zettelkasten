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
    # Deduplicate by the wiki link itself
    seen = set()
    unique_related = []
    for note in all_related:
        # Extract the wiki link for deduplication
        link_match = re.search(r'\[\[([^\]]+)\]\]', note)
        if link_match:
            link = link_match.group(1)
            if link not in seen:
                seen.add(link)
                unique_related.append(note)

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


if __name__ == "__main__":
    app()
