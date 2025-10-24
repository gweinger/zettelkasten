"""Find empty concept notes (orphans) that need to be filled out."""

import re
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class EmptyNote:
    """Represents an empty/stub note that needs content."""
    title: str
    filepath: Path
    is_stub: bool  # True if only has frontmatter and title


class OrphanFinder:
    """Find empty concept notes in the vault that need content."""

    def __init__(self, vault_path: Path):
        """
        Initialize OrphanFinder.

        Args:
            vault_path: Path to the vault root directory
        """
        self.vault_path = vault_path
        self.permanent_notes_path = vault_path / "permanent-notes"

    def find_all_orphans(self) -> List[EmptyNote]:
        """
        Find all empty/stub notes in the permanent notes directory.

        Empty notes are those with only frontmatter and a title heading,
        no substantive content.

        Returns:
            List of EmptyNote objects
        """
        orphans = []

        if not self.permanent_notes_path.exists():
            return orphans

        for note_file in self.permanent_notes_path.glob("*.md"):
            if note_file.stem.upper() == "INDEX":
                continue

            if self._is_empty_note(note_file):
                title = self._get_note_title(note_file)
                if title:
                    orphans.append(EmptyNote(
                        title=title,
                        filepath=note_file,
                        is_stub=True
                    ))

        # Sort by name for consistent output
        orphans.sort(key=lambda x: x.title)
        return orphans

    def _is_empty_note(self, filepath: Path) -> bool:
        """
        Check if a note is essentially empty.

        A note is considered empty if it:
        - Is completely empty (0 bytes)
        - Only contains YAML frontmatter
        - Only contains frontmatter + title heading
        - Only contains frontmatter + title + whitespace/comments

        Args:
            filepath: Path to the note file

        Returns:
            True if note is empty, False otherwise
        """
        try:
            content = filepath.read_text()

            # Completely empty file
            if not content or not content.strip():
                return True

            # Skip frontmatter
            frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
            if frontmatter_match:
                content = content[frontmatter_match.end():]
            else:
                # No frontmatter found - if file starts with non-frontmatter content,
                # it's not empty in the way we're looking for
                return False

            # Remove title heading and surrounding whitespace
            content = re.sub(r"^#\s+.+?\n\n", "", content, flags=re.MULTILINE)
            content = content.strip()

            # If nothing left, it's empty
            if not content:
                return True

            # If only whitespace or HTML comments remain, it's empty
            content_cleaned = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
            content_cleaned = content_cleaned.strip()

            return len(content_cleaned) == 0

        except Exception:
            return False

    def _get_note_title(self, filepath: Path) -> str:
        """
        Extract the title from a note file.

        For completely empty files, use the filename as the title.
        Otherwise, looks in YAML frontmatter first, then falls back to first heading.

        Args:
            filepath: Path to the note file

        Returns:
            Note title, or empty string if not found
        """
        try:
            content = filepath.read_text()

            # Completely empty file - use filename as title
            if not content or not content.strip():
                # Extract title from filename (remove timestamp prefix and .md)
                filename = filepath.stem
                # Remove timestamp prefix (format: 20251024145426-title)
                parts = filename.split("-", 1)
                if len(parts) > 1:
                    title = parts[1].replace("-", " ").title()
                    return title
                return filename

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

    def find_orphans_with_context(self) -> List[Dict]:
        """
        Find orphans and return info about them.

        Returns:
            List of dicts with orphan info
        """
        orphans = self.find_all_orphans()

        result = []
        for orphan in orphans:
            result.append({
                "title": orphan.title,
                "filepath": str(orphan.filepath),
                "relative_path": str(orphan.filepath.relative_to(self.vault_path)),
            })

        return result
