"""Generate index pages for concepts and sources."""

from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import re
from collections import defaultdict

from zettelkasten.core.config import Config
from zettelkasten.core.models import ContentType
from zettelkasten.processors.concept_extractor import ConceptExtractor


class NoteMetadata:
    """Simple container for parsed note metadata."""

    def __init__(
        self,
        filepath: Path,
        title: str,
        source_type: Optional[str] = None,
        source_url: Optional[str] = None,
        created: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ):
        self.filepath = filepath
        self.title = title
        self.source_type = source_type
        self.source_url = source_url
        self.created = created
        self.tags = tags or []


class IndexGenerator:
    """Generate index pages for browsing the Zettelkasten."""

    def __init__(self, config: Config):
        self.config = config
        self.config.ensure_directories()
        # Initialize concept extractor for generating summaries
        self.concept_extractor = ConceptExtractor(config)

    def rebuild_indices(self) -> Dict[str, Path]:
        """
        Rebuild all index files.

        Returns:
            Dict mapping index names to their file paths
        """
        indices = {}

        # Generate concept index
        concept_index_path = self.generate_concept_index()
        if concept_index_path:
            indices["concepts"] = concept_index_path

        # Generate person index
        person_index_path = self.generate_person_index()
        if person_index_path:
            indices["people"] = person_index_path

        # Generate source index
        source_index_path = self.generate_source_index()
        if source_index_path:
            indices["sources"] = source_index_path

        return indices

    def generate_concept_index(self) -> Optional[Path]:
        """
        Generate an alphabetical index of all concept notes.

        Returns:
            Path to the generated index file
        """
        permanent_notes_dir = self.config.get_permanent_notes_path()

        # Find all markdown files
        note_files = list(permanent_notes_dir.glob("*.md"))

        # Exclude all index files
        note_files = [f for f in note_files if f.stem.upper() not in ["INDEX", "PEOPLE-INDEX", "PERSON-INDEX"]]

        if not note_files:
            return None

        # Parse all notes
        notes = []
        for filepath in note_files:
            metadata = self._parse_note_metadata(filepath)
            if metadata:
                notes.append(metadata)

        # Sort alphabetically by title
        notes.sort(key=lambda n: n.title.lower())

        # Group by first letter
        grouped_notes: Dict[str, List[NoteMetadata]] = defaultdict(list)
        for note in notes:
            first_letter = note.title[0].upper()
            # Group numbers and special characters under '#'
            if not first_letter.isalpha():
                first_letter = "#"
            grouped_notes[first_letter].append(note)

        # Generate markdown content
        lines = []
        lines.append("---")
        lines.append("title: Concept Index")
        lines.append(f"created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("tags: [index, concepts]")
        lines.append("---")
        lines.append("")
        lines.append("# Concept Index")
        lines.append("")
        lines.append(f"*{len(notes)} concepts*")
        lines.append("")

        # Add alphabetical sections
        for letter in sorted(grouped_notes.keys()):
            lines.append(f"## {letter}")
            lines.append("")
            for note in grouped_notes[letter]:
                # Create relative link to the note with description
                relative_filename = note.filepath.stem

                # Try to extract a brief description from the note content
                description = self._extract_description(Path(note.filepath))
                if description:
                    lines.append(f"- **[[{relative_filename}|{note.title}]]**: {description}")
                else:
                    lines.append(f"- [[{relative_filename}|{note.title}]]")
            lines.append("")

        # Write index file
        index_path = permanent_notes_dir / "INDEX.md"
        index_path.write_text("\n".join(lines))

        return index_path

    def generate_person_index(self) -> Optional[Path]:
        """
        Generate an alphabetical index of all person/contact notes.

        Returns:
            Path to the generated index file
        """
        permanent_notes_dir = self.config.get_permanent_notes_path()

        # Find all markdown files
        note_files = list(permanent_notes_dir.glob("*.md"))

        # Exclude the index files themselves
        note_files = [f for f in note_files if f.stem.upper() not in ["INDEX", "PEOPLE-INDEX", "PERSON-INDEX"]]

        # Filter to only person notes (those with 'person' or 'contact' tag)
        person_notes = []
        for filepath in note_files:
            metadata = self._parse_note_metadata(filepath)
            if metadata and ("person" in metadata.tags or "contact" in metadata.tags):
                person_notes.append(metadata)

        if not person_notes:
            return None

        # Sort alphabetically by title
        person_notes.sort(key=lambda n: n.title.lower())

        # Generate markdown content
        lines = []
        lines.append("---")
        lines.append("title: People Index")
        lines.append(f"created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("tags: [index, people, contacts]")
        lines.append("---")
        lines.append("")
        lines.append("# People Index")
        lines.append("")
        lines.append(f"*{len(person_notes)} people*")
        lines.append("")
        lines.append("Directory of professionals, speakers, and contacts in your Zettelkasten.")
        lines.append("")

        # Group by first letter
        grouped_notes: Dict[str, List[NoteMetadata]] = defaultdict(list)
        for note in person_notes:
            first_letter = note.title[0].upper()
            # Group numbers and special characters under '#'
            if not first_letter.isalpha():
                first_letter = "#"
            grouped_notes[first_letter].append(note)

        # Add alphabetical sections
        for letter in sorted(grouped_notes.keys()):
            lines.append(f"## {letter}")
            lines.append("")
            for note in grouped_notes[letter]:
                # Create relative link to the note with description
                relative_filename = note.filepath.stem

                # Try to extract a brief description from the note content
                description = self._extract_description(Path(note.filepath))
                if description:
                    lines.append(f"- **[[{relative_filename}|{note.title}]]**: {description}")
                else:
                    lines.append(f"- [[{relative_filename}|{note.title}]]")
            lines.append("")

        # Write index file
        index_path = permanent_notes_dir / "PEOPLE-INDEX.md"
        index_path.write_text("\n".join(lines))

        return index_path

    def generate_source_index(self) -> Optional[Path]:
        """
        Generate an index of all source notes grouped by content type.

        Returns:
            Path to the generated index file
        """
        # Get summaries directory (where source notes are stored)
        summaries_dir = self.config.get_sources_path()

        # Find all markdown files in summaries
        note_files = list(summaries_dir.glob("*.md"))

        # Exclude the index file itself
        note_files = [f for f in note_files if f.stem.upper() != "INDEX"]

        if not note_files:
            return None

        # Parse all notes
        notes = []
        for filepath in note_files:
            metadata = self._parse_note_metadata(filepath)
            if metadata:
                notes.append(metadata)

        # Group by source type
        grouped_notes: Dict[str, List[NoteMetadata]] = defaultdict(list)
        for note in notes:
            source_type = note.source_type or "other"
            grouped_notes[source_type].append(note)

        # Sort notes within each group by title
        for group in grouped_notes.values():
            group.sort(key=lambda n: n.title.lower())

        # Generate markdown content
        lines = []
        lines.append("---")
        lines.append("title: Source Index")
        lines.append(f"created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("tags: [index, sources]")
        lines.append("---")
        lines.append("")
        lines.append("# Source Index")
        lines.append("")
        lines.append(f"*{len(notes)} sources*")
        lines.append("")

        # Define order and display names for content types
        type_order = [
            (ContentType.YOUTUBE.value, "YouTube Videos"),
            (ContentType.ARTICLE.value, "Articles"),
            (ContentType.PODCAST.value, "Podcasts"),
            ("other", "Other Sources"),
        ]

        # Add sections by content type
        for type_key, type_display in type_order:
            if type_key in grouped_notes:
                notes_in_group = grouped_notes[type_key]
                lines.append(f"## {type_display}")
                lines.append("")
                lines.append(f"*{len(notes_in_group)} {type_display.lower()}*")
                lines.append("")
                for note in notes_in_group:
                    # Create relative link to the note (in summaries/ subdirectory)
                    relative_filename = note.filepath.stem
                    link_text = f"[[summaries/{relative_filename}|{note.title}]]"
                    if note.source_url:
                        lines.append(f"- {link_text} - [source]({note.source_url})")
                    else:
                        lines.append(f"- {link_text}")
                lines.append("")

        # Write index file to sources root (not in summaries subdirectory)
        index_path = self.config.get_sources_base_path() / "INDEX.md"
        index_path.write_text("\n".join(lines))

        return index_path

    def _parse_note_metadata(self, filepath: Path) -> Optional[NoteMetadata]:
        """
        Parse metadata from a markdown file's YAML frontmatter.

        Args:
            filepath: Path to the markdown file

        Returns:
            NoteMetadata object or None if parsing fails
        """
        try:
            content = filepath.read_text()

            # Extract YAML frontmatter
            frontmatter = self._extract_frontmatter(content)
            if not frontmatter:
                return None

            # Parse key fields
            title = frontmatter.get("title", filepath.stem)
            source_type = frontmatter.get("source_type")
            source_url = frontmatter.get("source")
            created = frontmatter.get("created")
            tags_raw = frontmatter.get("tags", "")

            # Parse tags (handle both list and bracketed string formats)
            tags = []
            if isinstance(tags_raw, str):
                # Remove brackets and split by comma
                tags_clean = tags_raw.strip("[]")
                tags = [t.strip() for t in tags_clean.split(",") if t.strip()]
            elif isinstance(tags_raw, list):
                tags = tags_raw

            return NoteMetadata(
                filepath=filepath,
                title=title,
                source_type=source_type,
                source_url=source_url,
                created=created,
                tags=tags,
            )

        except Exception as e:
            print(f"Warning: Could not parse {filepath.name}: {e}")
            return None

    def _extract_frontmatter(self, content: str) -> Optional[Dict]:
        """
        Extract YAML frontmatter from markdown content.

        Args:
            content: Markdown file content

        Returns:
            Dict of frontmatter key-value pairs or None
        """
        # Match YAML frontmatter between --- delimiters
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not match:
            return None

        frontmatter_text = match.group(1)
        frontmatter = {}

        # Parse YAML - handle both simple key: value and list formats
        lines = frontmatter_text.split("\n")
        current_key = None
        current_list = []

        for line in lines:
            # Check if line is a key: value pair
            if ":" in line and not line.startswith(" "):
                # Save previous list if any
                if current_key and current_list:
                    frontmatter[current_key] = current_list
                    current_list = []

                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()

                if value:
                    # Regular key: value pair
                    frontmatter[key] = value
                    current_key = None
                else:
                    # Might be start of a list
                    current_key = key
                    current_list = []

            elif line.startswith("  - ") and current_key:
                # List item
                item = line.strip()[2:].strip()  # Remove "- " prefix
                current_list.append(item)

        # Save any remaining list
        if current_key and current_list:
            frontmatter[current_key] = current_list

        return frontmatter

    def _extract_description(self, filepath: Path) -> Optional[str]:
        """
        Generate a one-line summary of the note content using Claude.

        Args:
            filepath: Path to markdown file

        Returns:
            Brief one-line summary or None
        """
        try:
            content = filepath.read_text()

            # Skip frontmatter
            if content.startswith("---"):
                end_frontmatter = content.find("---", 3)
                if end_frontmatter != -1:
                    content = content[end_frontmatter + 3:].strip()

            # Get title
            title = None
            if content.startswith("# "):
                title = content.split("\n")[0].replace("# ", "").strip()

            # Use Claude to generate a concise one-line summary
            prompt = f"""Generate a single-line summary (max 150 characters) of this concept note.

Title: {title or filepath.stem}

Content:
{content[:2000]}

Return ONLY the summary text, no other commentary. Keep it under 150 characters."""

            response = self.concept_extractor.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=100,
                temperature=0.5,
                messages=[{"role": "user", "content": prompt}],
            )

            summary = response.content[0].text.strip()

            # Truncate if too long
            if len(summary) > 150:
                summary = summary[:147] + "..."

            return summary

        except Exception:
            return None
