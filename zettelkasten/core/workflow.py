"""Main workflow orchestration for processing content into Zettelkasten."""

from pathlib import Path
from typing import List, Dict
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from zettelkasten.core.config import Config
from zettelkasten.core.models import ContentType, ProcessedContent, ZettelNote
from zettelkasten.utils.url_detector import detect_content_type, is_valid_url
from zettelkasten.utils.vault_scanner import (
    get_existing_concept_titles,
    get_inbox_files,
    parse_markdown_note,
)
from zettelkasten.processors.youtube_processor import YouTubeProcessor
from zettelkasten.processors.article_processor import ArticleProcessor
from zettelkasten.processors.transcription import TranscriptionService
from zettelkasten.processors.concept_extractor import ConceptExtractor
from zettelkasten.generators.zettel_generator import ZettelGenerator


console = Console()


class AddWorkflow:
    """Orchestrates the workflow for adding content to Zettelkasten."""

    def __init__(self, config: Config):
        self.config = config
        self.youtube_processor = YouTubeProcessor(config)
        self.article_processor = ArticleProcessor()
        self.transcription_service = TranscriptionService(
            config, model_size=config.whisper_model_size
        )
        self.concept_extractor = ConceptExtractor(config)
        self.zettel_generator = ZettelGenerator(config)

    def process_url(self, url: str, force: bool = False) -> List[Path]:
        """
        Process a URL and generate Zettelkasten notes.

        Args:
            url: URL to process
            force: Force reprocessing even if already exists

        Returns:
            List of paths to generated notes
        """
        # Validate URL
        if not is_valid_url(url):
            raise ValueError(f"Invalid URL: {url}")

        console.print(f"\n[bold cyan]Processing:[/bold cyan] {url}\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Step 1: Detect content type
            task = progress.add_task("Detecting content type...", total=None)
            content_type, metadata = detect_content_type(url)
            console.print(f"[green]✓[/green] Content type: {content_type.value}")
            progress.remove_task(task)

            # Step 2: Process content based on type
            task = progress.add_task("Downloading/extracting content...", total=None)
            processed_content = self._process_content(url, content_type, metadata)
            console.print(f"[green]✓[/green] Content extracted: {processed_content.title}")
            progress.remove_task(task)

            # Step 3: Get text content (transcribe if needed)
            task = progress.add_task("Getting text content...", total=None)
            text_content = self._get_text_content(processed_content)
            console.print(f"[green]✓[/green] Text ready ({len(text_content)} characters)")
            progress.remove_task(task)

            # Step 4: Extract concepts
            task = progress.add_task("Extracting concepts with GPT...", total=None)
            concepts = self.concept_extractor.extract_concepts(
                text=text_content,
                title=processed_content.title,
                source_url=url,
            )
            console.print(f"[green]✓[/green] Extracted {len(concepts)} concepts")
            progress.remove_task(task)

            # Step 5: Generate summary
            task = progress.add_task("Generating summary...", total=None)
            summary = self.concept_extractor.generate_summary(
                text=text_content,
                title=processed_content.title,
            )
            console.print(f"[green]✓[/green] Summary generated")
            progress.remove_task(task)

            # Step 6: Generate Zettelkasten notes
            task = progress.add_task("Creating Zettelkasten notes...", total=None)

            # Generate and save notes to staging area
            saved_paths = self.zettel_generator.generate_and_save_notes(
                content=processed_content,
                summary=summary,
                concepts=concepts,
                source_url=url,
                use_staging=True,  # Save to staging for review
            )

            console.print(f"[green]✓[/green] Created {len(saved_paths)} notes in staging")
            progress.remove_task(task)

            # Cleanup if needed
            if processed_content.audio_file and processed_content.audio_file.exists():
                self.youtube_processor.cleanup(processed_content.audio_file)

        return saved_paths

    def _process_content(
        self,
        url: str,
        content_type: ContentType,
        metadata: dict,
    ) -> ProcessedContent:
        """Process content based on type."""
        if content_type == ContentType.YOUTUBE:
            return self.youtube_processor.process(
                url=url,
                video_id=metadata.get("video_id"),
            )
        elif content_type == ContentType.ARTICLE:
            return self.article_processor.process(url=url)
        elif content_type == ContentType.PODCAST:
            # For now, treat podcast URLs as articles (extract show notes)
            # In the future, could implement specific podcast processors
            return self.article_processor.process(url=url)
        else:
            raise ValueError(f"Unsupported content type: {content_type}")

    def _get_text_content(self, content: ProcessedContent) -> str:
        """Get text content, transcribing audio if necessary."""
        if content.text_content:
            # Already have text (article)
            return content.text_content
        elif content.audio_file:
            # Need to transcribe audio
            console.print("  [dim]Transcribing audio (this may take a few minutes)...[/dim]")
            transcript = self.transcription_service.transcribe(content.audio_file)
            return transcript.text
        else:
            raise ValueError("No text or audio content available")


class ImportWorkflow:
    """Orchestrates the workflow for importing notes from inbox into Zettelkasten."""

    def __init__(self, config: Config):
        self.config = config
        self.concept_extractor = ConceptExtractor(config)
        self.zettel_generator = ZettelGenerator(config)
        self.config.ensure_directories()

    def process_inbox(self, archive: bool = True) -> Dict[str, List[Path]]:
        """
        Process all markdown files in the inbox directory.

        Args:
            archive: If True, move processed files to an archive folder.
                    If False, delete them after processing.

        Returns:
            Dict with 'processed' and 'failed' lists of file paths
        """
        inbox_files = get_inbox_files(self.config)

        if not inbox_files:
            console.print("[yellow]No files found in inbox.[/yellow]")
            return {"processed": [], "failed": []}

        console.print(f"\n[bold cyan]Processing {len(inbox_files)} file(s) from inbox...[/bold cyan]\n")

        processed = []
        failed = []

        # Get existing concepts once (for efficiency)
        existing_concepts = get_existing_concept_titles(self.config)

        for filepath in inbox_files:
            try:
                console.print(f"\n[bold]Processing:[/bold] {filepath.name}")
                result = self._process_single_note(filepath, existing_concepts)
                if result:
                    processed.append(filepath)
                    console.print(f"[green]✓[/green] Successfully processed {filepath.name}")

                    # Archive or delete the original file
                    if archive:
                        self._archive_file(filepath)
                    else:
                        filepath.unlink()
                else:
                    failed.append(filepath)
                    console.print(f"[red]✗[/red] Failed to process {filepath.name}")

            except Exception as e:
                failed.append(filepath)
                console.print(f"[red]✗[/red] Error processing {filepath.name}: {e}")

        return {"processed": processed, "failed": failed}

    def _process_single_note(
        self, filepath: Path, existing_concepts: List[str]
    ) -> bool:
        """
        Process a single note from inbox.

        Args:
            filepath: Path to the markdown file
            existing_concepts: List of existing concept titles in KB

        Returns:
            True if successful, False otherwise
        """
        # Parse the note
        parsed = parse_markdown_note(filepath)
        title = parsed["title"]
        content = parsed["content"]

        if not content:
            console.print(f"  [yellow]Warning: Empty content in {filepath.name}[/yellow]")
            return False

        # Determine note type using hybrid approach
        note_type = self._determine_note_type(filepath, parsed, content, title)
        console.print(f"  [dim]Detected as: {note_type}[/dim]")

        # Route to appropriate handler
        if note_type == "source":
            return self._process_as_source(filepath, title, content, existing_concepts)
        else:
            return self._process_as_concept(filepath, title, content, existing_concepts)

    def _determine_note_type(
        self, filepath: Path, parsed: Dict[str, str], content: str, title: str
    ) -> str:
        """
        Determine if note is a 'concept' or 'source' using hybrid approach.

        Priority:
        1. Folder structure (inbox/concepts/ or inbox/sources/)
        2. Frontmatter metadata (type: concept/source)
        3. Claude classification

        Args:
            filepath: Path to the file
            parsed: Parsed note data
            content: Note content
            title: Note title

        Returns:
            Either "concept" or "source"
        """
        inbox_path = self.config.get_inbox_path()

        # 1. Check folder structure
        try:
            relative_path = filepath.relative_to(inbox_path)
            first_folder = relative_path.parts[0] if len(relative_path.parts) > 1 else None

            if first_folder and first_folder.lower() in ["concepts", "concept"]:
                return "concept"
            elif first_folder and first_folder.lower() in ["sources", "source"]:
                return "source"
        except ValueError:
            pass  # File not in inbox path

        # 2. Check frontmatter metadata
        if "type" in parsed:
            note_type = parsed["type"].lower()
            if note_type in ["concept", "source"]:
                return note_type

        # Check for source indicators in metadata
        if "source" in parsed or "source_url" in parsed or "url" in parsed:
            return "source"

        # 3. Use Claude to classify
        console.print("  [dim]Classifying note with Claude...[/dim]")
        return self.concept_extractor.classify_note(content, title)

    def _process_as_concept(
        self, filepath: Path, title: str, content: str, existing_concepts: List[str]
    ) -> bool:
        """Process note as a concept (current behavior)."""
        # Find related concepts using Claude
        console.print("  [dim]Finding related concepts...[/dim]")
        related_concepts = self.concept_extractor.find_related_concepts(
            note_content=content, note_title=title, existing_concepts=existing_concepts
        )

        if related_concepts:
            console.print(
                f"  [green]✓[/green] Found {len(related_concepts)} related concept(s)"
            )
        else:
            console.print("  [dim]No related concepts found[/dim]")

        # Create a properly formatted permanent note
        note = self._create_permanent_note(
            title=title, content=content, related_concepts=related_concepts
        )

        # Save the note
        saved_path = self.zettel_generator.save_note(note)
        console.print(
            f"  [green]✓[/green] Saved to: {saved_path.relative_to(self.config.vault_path)}"
        )

        return True

    def _process_as_source(
        self, filepath: Path, title: str, content: str, existing_concepts: List[str]
    ) -> bool:
        """Process note as a source (extract concepts, generate summary)."""
        console.print("  [dim]Extracting concepts from source...[/dim]")

        # Extract concepts from the source content
        concepts = self.concept_extractor.extract_concepts(
            text=content,
            title=title,
            source_url="",  # No URL for imported sources
            max_concepts=10,
        )
        console.print(f"  [green]✓[/green] Extracted {len(concepts)} concept(s)")

        # Generate summary
        console.print("  [dim]Generating summary...[/dim]")
        summary = self.concept_extractor.generate_summary(text=content, title=title)
        console.print(f"  [green]✓[/green] Summary generated")

        # Create source note with ProcessedContent mock
        from zettelkasten.core.models import ContentType, ProcessedContent

        processed_content = ProcessedContent(
            url="",
            content_type=ContentType.ARTICLE,
            title=title,
            text_content=content,
            metadata={"imported": True},
        )

        # Generate and save notes
        saved_paths = self.zettel_generator.generate_and_save_notes(
            content=processed_content,
            summary=summary,
            concepts=concepts,
            source_url="",
        )

        console.print(
            f"  [green]✓[/green] Created {len(saved_paths)} note(s): 1 source + {len(concepts)} concepts"
        )

        return True

    def _create_permanent_note(
        self, title: str, content: str, related_concepts: List[str]
    ) -> ZettelNote:
        """
        Create a properly formatted permanent note.

        Args:
            title: Note title
            content: Note content
            related_concepts: List of related concept titles

        Returns:
            ZettelNote object
        """
        # Build note content with related concepts section
        lines = []
        lines.append(content)

        # Add related concepts section if any exist
        if related_concepts:
            lines.append("")
            lines.append("## Related Concepts")
            lines.append("")
            for concept in related_concepts:
                # Create wikilink - the generator will handle finding the actual filename
                lines.append(f"- [[{concept}]]")

        final_content = "\n".join(lines)

        # Create the ZettelNote
        note = ZettelNote(
            title=title,
            content=final_content,
            tags=["concept", "permanent-note", "imported"],
            links=related_concepts,
            created_at=datetime.now(),
        )

        return note

    def _archive_file(self, filepath: Path) -> None:
        """
        Move a file to the archive subdirectory within inbox.

        Args:
            filepath: Path to the file to archive
        """
        archive_dir = self.config.get_inbox_path() / "archive"
        archive_dir.mkdir(exist_ok=True)

        # Preserve subdirectory structure if file is in a subfolder
        relative_path = filepath.relative_to(self.config.get_inbox_path())
        archive_path = archive_dir / relative_path

        # Create parent directories if needed
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Move the file
        filepath.rename(archive_path)
