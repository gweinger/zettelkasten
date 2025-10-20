"""Generate Zettelkasten notes from processed content."""

from pathlib import Path
from typing import List, Optional
from zettelkasten.core.models import (
    ZettelNote,
    ProcessedContent,
    Concept,
    ContentType,
)
from zettelkasten.core.config import Config
from zettelkasten.processors.concept_extractor import ConceptExtractor


class ZettelGenerator:
    """Generate Zettelkasten markdown files."""

    def __init__(self, config: Config):
        self.config = config
        self.config.ensure_directories()
        # Initialize concept extractor for intelligent matching
        self.concept_extractor = ConceptExtractor(config)

    def generate_source_note(
        self,
        content: ProcessedContent,
        summary: str,
        concepts: List[Concept],
    ) -> ZettelNote:
        """
        Generate a source note (literature note) for the content.

        Args:
            content: The processed content
            summary: Summary of the content
            concepts: Extracted concepts

        Returns:
            ZettelNote for the source
        """
        # Build the note content
        lines = []

        # Summary section
        lines.append("## Summary")
        lines.append("")
        lines.append(summary)
        lines.append("")

        # Key concepts section
        if concepts:
            lines.append("## Key Concepts")
            lines.append("")
            for concept in concepts:
                lines.append(f"- [[{concept.name}]]")
            lines.append("")

        # Metadata section
        lines.append("## Source Information")
        lines.append("")
        lines.append(f"- **URL**: {content.url}")
        lines.append(f"- **Type**: {content.content_type.value}")

        # Add source-specific metadata
        if content.metadata:
            if content.content_type == ContentType.YOUTUBE:
                if content.metadata.get("uploader"):
                    lines.append(f"- **Creator**: {content.metadata['uploader']}")
                if content.metadata.get("upload_date"):
                    lines.append(f"- **Published**: {content.metadata['upload_date']}")
                if content.metadata.get("duration"):
                    duration_min = int(content.metadata["duration"]) // 60
                    lines.append(f"- **Duration**: {duration_min} minutes")
            elif content.content_type == ContentType.ARTICLE:
                if content.metadata.get("author"):
                    lines.append(f"- **Author**: {content.metadata['author']}")
                if content.metadata.get("site_name"):
                    lines.append(f"- **Site**: {content.metadata['site_name']}")

        note_content = "\n".join(lines)

        # Create tags
        tags = ["source", content.content_type.value]
        if content.metadata.get("tags"):
            tags.extend(content.metadata["tags"][:5])  # Limit to 5 tags

        # Get concept names for linking
        concept_links = [concept.name for concept in concepts]

        return ZettelNote(
            title=content.title,
            content=note_content,
            tags=tags,
            links=concept_links,
            source_url=content.url,
            source_type=content.content_type,
            metadata=content.metadata,
        )

    def generate_concept_notes(
        self,
        concepts: List[Concept],
        source_title: str,
        source_url: str,
    ) -> List[ZettelNote]:
        """
        Generate individual notes for each concept.

        Args:
            concepts: List of concepts to generate notes for
            source_title: Title of the source content
            source_url: URL of the source

        Returns:
            List of ZettelNote objects, one per concept
        """
        notes = []

        for concept in concepts:
            # Build concept note content
            lines = []

            # Description
            lines.append(concept.description)
            lines.append("")

            # Quotes section
            if concept.quotes:
                lines.append("## Key Quotes")
                lines.append("")
                for quote in concept.quotes:
                    lines.append(f"> {quote}")
                    lines.append("")

            # Source reference
            lines.append("## Source")
            lines.append("")
            lines.append(f"From: [[{source_title}]]")
            lines.append(f"URL: {source_url}")
            lines.append("")

            note_content = "\n".join(lines)

            # Links include source and related concepts
            links = [source_title] + concept.related_concepts

            note = ZettelNote(
                title=concept.name,
                content=note_content,
                tags=["concept", "permanent-note"],
                links=links,
                source_url=source_url,
                metadata={
                    "source_title": source_title,
                    "related_concepts": concept.related_concepts,
                },
                # Add merge tracking from concept
                merge_target=concept.merge_target,
                is_new=concept.is_new,
            )

            notes.append(note)

        return notes

    def save_note(self, note: ZettelNote, use_staging: bool = False) -> Path:
        """
        Save a note to the vault in the appropriate directory.

        Args:
            note: The note to save
            use_staging: If True, save to staging directory instead of final location

        Returns:
            Path to the saved file
        """
        filename = note.get_filename()

        # Determine directory based on note tags
        if use_staging:
            # Save to staging directory with subdirectories
            if "source" in note.tags:
                directory = self.config.get_staging_path() / "sources"
            elif "concept" in note.tags or "permanent-note" in note.tags:
                directory = self.config.get_staging_path() / "concepts"
            else:
                directory = self.config.get_staging_path()
        else:
            # Save to final location
            if "source" in note.tags:
                # Source/literature notes go in sources/
                directory = self.config.get_sources_path()
            elif "concept" in note.tags or "permanent-note" in note.tags:
                # Concept/permanent notes go in permanent-notes/
                directory = self.config.get_permanent_notes_path()
            elif "fleeting" in note.tags or "fleeting-note" in note.tags:
                # Fleeting notes go in fleeting-notes/
                directory = self.config.get_fleeting_notes_path()
            else:
                # Default to vault root
                directory = self.config.vault_path

        # Ensure directory exists
        directory.mkdir(parents=True, exist_ok=True)
        filepath = directory / filename

        # Write markdown content
        markdown = note.to_markdown()
        filepath.write_text(markdown)

        return filepath

    def save_notes(self, notes: List[ZettelNote], use_staging: bool = False) -> List[Path]:
        """
        Save multiple notes to the vault.

        Args:
            notes: List of notes to save
            use_staging: If True, save to staging directory instead of final location

        Returns:
            List of paths to saved files
        """
        return [self.save_note(note, use_staging=use_staging) for note in notes]

    def note_exists(self, title: str) -> bool:
        """
        Check if a note with the given title already exists.

        Args:
            title: Note title to check

        Returns:
            True if note exists, False otherwise
        """
        # Simple check - looks for files containing the slugified title
        slug = title.lower().replace(" ", "-")
        slug = "".join(c for c in slug if c.isalnum() or c == "-")

        for filepath in self.config.vault_path.glob("*.md"):
            if slug in filepath.stem:
                return True

        return False

    def generate_and_save_notes(
        self,
        content: ProcessedContent,
        summary: str,
        concepts: List[Concept],
        source_url: str,
        use_staging: bool = False,
    ) -> List[Path]:
        """
        Generate notes with proper filename-based links and save them.

        This creates all notes, gets their filenames, then updates the links
        to use actual filenames instead of titles.

        Args:
            content: Processed content
            summary: Generated summary
            concepts: Extracted concepts
            source_url: Source URL
            use_staging: If True, save to staging directory instead of final location

        Returns:
            List of saved file paths
        """
        from datetime import datetime

        # Create a timestamp for this batch
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        # Check for duplicate concepts using intelligent matching
        for concept in concepts:
            existing = self.concept_extractor.find_matching_concept_intelligent(
                concept.name, concept.description, self.config
            )
            if existing:
                # Mark concept for merging into existing note
                concept.is_new = False
                concept.merge_target = Path(existing["filepath"]).name
                print(f"  → Will merge '{concept.name}' into existing: {concept.merge_target}")
            else:
                concept.is_new = True
                print(f"  → Will create new concept: '{concept.name}'")

        # Build filename mapping: title -> filename (without .md)
        filename_map = {}

        # Source note filename
        source_slug = content.title.lower().replace(" ", "-")
        source_slug = "".join(c for c in source_slug if c.isalnum() or c == "-")
        source_filename = f"{timestamp}-{source_slug}"
        filename_map[content.title] = source_filename

        # Concept note filenames - use existing filenames if merging
        for concept in concepts:
            if not concept.is_new and concept.merge_target:
                # Use existing filename (without .md extension)
                filename_map[concept.name] = concept.merge_target.replace('.md', '')
            else:
                # Create new filename
                concept_slug = concept.name.lower().replace(" ", "-")
                concept_slug = "".join(c for c in concept_slug if c.isalnum() or c == "-")
                concept_filename = f"{timestamp}-{concept_slug}"
                filename_map[concept.name] = concept_filename

        # Generate source note with filename-based links
        source_note = self._generate_source_note_with_filenames(
            content=content,
            summary=summary,
            concepts=concepts,
            filename_map=filename_map,
        )

        # Generate concept notes with filename-based links
        concept_notes = self._generate_concept_notes_with_filenames(
            concepts=concepts,
            source_title=content.title,
            source_url=source_url,
            filename_map=filename_map,
        )

        # Save all notes
        all_notes = [source_note] + concept_notes
        return self.save_notes(all_notes, use_staging=use_staging)

    def _generate_source_note_with_filenames(
        self,
        content: ProcessedContent,
        summary: str,
        concepts: List[Concept],
        filename_map: dict,
    ) -> ZettelNote:
        """Generate source note using filename-based links."""
        lines = []

        lines.append("## Summary")
        lines.append("")
        lines.append(summary)
        lines.append("")

        if concepts:
            lines.append("## Key Concepts")
            lines.append("")
            for concept in concepts:
                # Use filename instead of title with path to permanent-notes
                filename = filename_map.get(concept.name, concept.name)
                lines.append(f"- [[permanent-notes/{filename}|{concept.name}]]")
            lines.append("")

        lines.append("## Source Information")
        lines.append("")
        lines.append(f"- **URL**: {content.url}")
        lines.append(f"- **Type**: {content.content_type.value}")

        if content.metadata:
            if content.content_type == ContentType.YOUTUBE:
                if content.metadata.get("uploader"):
                    lines.append(f"- **Creator**: {content.metadata['uploader']}")
                if content.metadata.get("upload_date"):
                    lines.append(f"- **Published**: {content.metadata['upload_date']}")
                if content.metadata.get("duration"):
                    duration_min = int(content.metadata["duration"]) // 60
                    lines.append(f"- **Duration**: {duration_min} minutes")
            elif content.content_type == ContentType.ARTICLE:
                if content.metadata.get("author"):
                    lines.append(f"- **Author**: {content.metadata['author']}")
                if content.metadata.get("site_name"):
                    lines.append(f"- **Site**: {content.metadata['site_name']}")
                # Add link to saved article full text
                if content.metadata.get("article_file"):
                    from pathlib import Path
                    article_path = Path(content.metadata["article_file"])
                    # Use relative path from vault root
                    lines.append(f"- **Full Text**: [View saved article](file:///{article_path.resolve()})")

        note_content = "\n".join(lines)

        tags = ["source", content.content_type.value]
        if content.metadata.get("tags"):
            tags.extend(content.metadata["tags"][:5])

        # Links using filenames with paths and display names
        concept_links = [f"permanent-notes/{filename_map.get(c.name, c.name)}|{c.name}" for c in concepts]

        return ZettelNote(
            title=content.title,
            content=note_content,
            tags=tags,
            links=concept_links,
            source_url=content.url,
            source_type=content.content_type,
            metadata=content.metadata,
        )

    def _generate_concept_notes_with_filenames(
        self,
        concepts: List[Concept],
        source_title: str,
        source_url: str,
        filename_map: dict,
    ) -> List[ZettelNote]:
        """Generate concept notes using filename-based links."""
        notes = []

        for concept in concepts:
            lines = []

            lines.append(concept.description)
            lines.append("")

            if concept.quotes:
                lines.append("## Key Quotes")
                lines.append("")
                for quote in concept.quotes:
                    lines.append(f"> {quote}")
                    lines.append("")

            lines.append("## Source")
            lines.append("")
            # Use filename for source link with path to sources
            source_filename = filename_map.get(source_title, source_title)
            lines.append(f"From: [[sources/{source_filename}|{source_title}]]")
            lines.append(f"URL: {source_url}")
            lines.append("")

            note_content = "\n".join(lines)

            # Links using filenames with paths and display names
            links = [f"sources/{source_filename}|{source_title}"]
            for related in concept.related_concepts:
                # Check if this concept has a file in our batch
                if related in filename_map:
                    # It exists - use full path with display name
                    related_filename = filename_map[related]
                    links.append(f"permanent-notes/{related_filename}|{related}")
                else:
                    # It doesn't exist - create a stub link (just the name)
                    links.append(related)

            note = ZettelNote(
                title=concept.name,
                content=note_content,
                tags=["concept", "permanent-note"],
                links=links,
                source_url=source_url,
                metadata={
                    "source_title": source_title,
                    "related_concepts": concept.related_concepts,
                },
                # Add merge tracking from concept
                merge_target=concept.merge_target,
                is_new=concept.is_new,
            )

            notes.append(note)

        return notes
