"""Utilities for scanning and analyzing vault contents."""

from pathlib import Path
from typing import List, Dict, Optional
import re

from zettelkasten.core.config import Config


def get_existing_concepts(config: Config) -> List[Dict[str, str]]:
    """
    Get a list of all existing concept notes in the vault.

    Args:
        config: Application configuration

    Returns:
        List of dicts with 'title' and 'filepath' keys
    """
    permanent_notes_dir = config.get_permanent_notes_path()
    concepts = []

    # Find all markdown files except INDEX
    note_files = [f for f in permanent_notes_dir.glob("*.md") if f.stem.upper() != "INDEX"]

    for filepath in note_files:
        # Parse the note to get its title
        title = _extract_title(filepath)
        if title:
            concepts.append({"title": title, "filepath": str(filepath)})

    return concepts


def get_existing_concept_titles(config: Config) -> List[str]:
    """
    Get a simple list of all existing concept titles.

    Args:
        config: Application configuration

    Returns:
        List of concept titles
    """
    concepts = get_existing_concepts(config)
    return [c["title"] for c in concepts]


def find_matching_concept(concept_name: str, config: Config) -> Optional[Dict[str, str]]:
    """
    Find an existing concept that matches the given name.

    Uses fuzzy matching to handle slight variations in naming.

    Args:
        concept_name: Name of the concept to find
        config: Application configuration

    Returns:
        Dict with 'title' and 'filepath' if found, None otherwise
    """
    existing_concepts = get_existing_concepts(config)

    # Normalize the search name for comparison
    search_name = concept_name.lower().strip()

    for concept in existing_concepts:
        existing_name = concept["title"].lower().strip()

        # Exact match
        if search_name == existing_name:
            return concept

        # Very close match (handle plurals, minor differences)
        # Remove common suffixes and check again
        search_base = search_name.rstrip('s')
        existing_base = existing_name.rstrip('s')
        if search_base == existing_base:
            return concept

        # Check if one is contained in the other (with some length threshold)
        if len(search_name) > 10 and len(existing_name) > 10:
            if search_name in existing_name or existing_name in search_name:
                return concept

    return None


def _extract_title(filepath: Path) -> Optional[str]:
    """
    Extract title from a markdown file's frontmatter or first heading.

    Args:
        filepath: Path to markdown file

    Returns:
        Title string or None
    """
    try:
        content = filepath.read_text()

        # Try to extract from YAML frontmatter
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if frontmatter_match:
            frontmatter_text = frontmatter_match.group(1)
            for line in frontmatter_text.split("\n"):
                if line.startswith("title:"):
                    return line.split(":", 1)[1].strip()

        # Fallback: extract from first # heading
        heading_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if heading_match:
            return heading_match.group(1).strip()

        # Last resort: use filename
        return filepath.stem

    except Exception:
        return None


def parse_markdown_note(filepath: Path) -> Dict[str, str]:
    """
    Parse a markdown note, extracting title, content, and any existing frontmatter.

    Args:
        filepath: Path to markdown file

    Returns:
        Dict with 'title', 'content', 'raw_content', and optional frontmatter fields
    """
    content = filepath.read_text()

    result = {
        "raw_content": content,
        "title": "",
        "content": "",
        "has_frontmatter": False,
    }

    # Check for YAML frontmatter
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)

    if frontmatter_match:
        frontmatter_text = frontmatter_match.group(1)
        body = frontmatter_match.group(2)
        result["has_frontmatter"] = True

        # Parse frontmatter fields
        for line in frontmatter_text.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                result[key.strip()] = value.strip()

        # Get title from frontmatter or first heading
        if "title" in result and result["title"]:
            # Title from frontmatter - remove first heading from body if it matches
            body = _remove_first_heading_if_matches(body, result["title"])
        else:
            # Try to get from first heading
            heading_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            if heading_match:
                result["title"] = heading_match.group(1).strip()
                # Remove the first heading from the body
                body = re.sub(r"^#\s+.+$\n?", "", body, count=1, flags=re.MULTILINE)

        result["content"] = body.strip()
    else:
        # No frontmatter - extract title from first heading
        heading_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if heading_match:
            result["title"] = heading_match.group(1).strip()
            # Remove the first heading from content
            body = re.sub(r"^#\s+.+$\n?", "", content, count=1, flags=re.MULTILINE)
            result["content"] = body.strip()
        else:
            result["title"] = filepath.stem
            result["content"] = content.strip()

    # If we still don't have a title, use filename
    if not result["title"]:
        result["title"] = filepath.stem

    return result


def _remove_first_heading_if_matches(content: str, title: str) -> str:
    """
    Remove the first heading from content if it matches the given title.

    Args:
        content: Markdown content
        title: Title to match against

    Returns:
        Content with first heading removed if it matches
    """
    heading_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if heading_match and heading_match.group(1).strip() == title:
        # Remove the first heading
        return re.sub(r"^#\s+.+$\n?", "", content, count=1, flags=re.MULTILINE).strip()
    return content


def get_inbox_files(config: Config) -> List[Path]:
    """
    Get all markdown files in the inbox directory, excluding README files.

    Args:
        config: Application configuration

    Returns:
        List of paths to markdown files in inbox
    """
    inbox_path = config.get_inbox_path()

    # Recursively find all markdown files in inbox and subdirectories
    markdown_files = list(inbox_path.rglob("*.md"))

    # Filter out README files and archive directory
    markdown_files = [
        f for f in markdown_files
        if f.name.upper() != "README.MD" and "archive" not in f.parts
    ]

    return markdown_files
