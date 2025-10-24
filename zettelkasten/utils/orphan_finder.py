"""Find orphan concepts that are linked but don't have files yet."""

import re
from pathlib import Path
from typing import List, Dict, Set
from dataclasses import dataclass


@dataclass
class OrphanConcept:
    """Represents an orphan concept that is linked but doesn't have a file."""
    name: str
    backlinks: List[str]  # List of note titles that reference this orphan


class OrphanFinder:
    """Find orphan concepts in the vault that are referenced but don't exist."""

    def __init__(self, vault_path: Path):
        """
        Initialize OrphanFinder.

        Args:
            vault_path: Path to the vault root directory
        """
        self.vault_path = vault_path
        self.permanent_notes_path = vault_path / "permanent-notes"
        self.sources_path = vault_path / "sources"

    def find_all_orphans(self) -> List[OrphanConcept]:
        """
        Find all orphan concepts in the permanent notes.

        Returns:
            List of OrphanConcept objects
        """
        # Get all existing note titles
        existing_titles = self._get_existing_note_titles()

        # Find all linked concepts and their backlinks
        linked_concepts: Dict[str, List[str]] = {}

        # Scan permanent notes for links
        if self.permanent_notes_path.exists():
            for note_file in self.permanent_notes_path.glob("*.md"):
                if note_file.stem.upper() == "INDEX":
                    continue

                # Get the title of this note for backlinks
                note_title = self._get_note_title(note_file)
                if not note_title:
                    continue

                # Find all related notes links in this file
                content = note_file.read_text()
                linked_names = self._extract_related_concept_names(content)

                for name in linked_names:
                    if name not in linked_concepts:
                        linked_concepts[name] = []
                    # Add backlink if not already present
                    if note_title not in linked_concepts[name]:
                        linked_concepts[name].append(note_title)

        # Find orphans: concepts that are linked but don't exist
        orphans = []
        for concept_name, backlinks in linked_concepts.items():
            if concept_name not in existing_titles:
                orphans.append(OrphanConcept(name=concept_name, backlinks=backlinks))

        # Sort by name for consistent output
        orphans.sort(key=lambda x: x.name)
        return orphans

    def _get_existing_note_titles(self) -> Set[str]:
        """
        Get all existing note titles from the permanent notes directory.

        Returns:
            Set of note titles
        """
        titles = set()

        if self.permanent_notes_path.exists():
            for note_file in self.permanent_notes_path.glob("*.md"):
                if note_file.stem.upper() == "INDEX":
                    continue

                title = self._get_note_title(note_file)
                if title:
                    titles.add(title)

        return titles

    def _get_note_title(self, filepath: Path) -> str:
        """
        Extract the title from a note file.

        Looks in YAML frontmatter first, then falls back to first heading.

        Args:
            filepath: Path to the note file

        Returns:
            Note title, or empty string if not found
        """
        try:
            content = filepath.read_text()

            # Try YAML frontmatter first
            frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
            if frontmatter_match:
                frontmatter = frontmatter_match.group(1)
                for line in frontmatter.split("\n"):
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip()
                        # Remove quotes if present
                        title = title.strip('"\'')
                        return title

            # Fallback to first heading
            heading_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if heading_match:
                return heading_match.group(1).strip()

        except Exception:
            pass

        return ""

    def _extract_related_concept_names(self, content: str) -> List[str]:
        """
        Extract concept names from wikilinks in "Related Notes" section.

        Args:
            content: Note content to search

        Returns:
            List of concept names found in wikilinks
        """
        names = []

        # Find the "Related Notes" section
        related_section = re.search(
            r"##\s+Related Notes\s*\n(.*?)(?=##\s+|\Z)",
            content,
            re.DOTALL | re.IGNORECASE
        )

        if not related_section:
            return names

        section_text = related_section.group(1)

        # Extract all wikilink display names
        # Pattern: [[path|display]] or [[path]]
        wikilinks = re.findall(r"\[\[.*?\|(.+?)\]\]|\[\[(.+?)\]\]", section_text)

        for link in wikilinks:
            # wikilinks is a tuple of (display_name, fallback_name)
            # Take the first non-empty one
            name = link[0] if link[0] else link[1]
            if name.strip():
                names.append(name.strip())

        return names

    def find_orphans_with_context(self) -> List[Dict]:
        """
        Find orphans and include context about how they're referenced.

        Returns:
            List of dicts with orphan info and backlink details
        """
        orphans = self.find_all_orphans()

        result = []
        for orphan in orphans:
            result.append({
                "name": orphan.name,
                "backlinks": orphan.backlinks,
                "backlink_count": len(orphan.backlinks),
            })

        return result
