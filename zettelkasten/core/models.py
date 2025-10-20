"""Data models for Zettelkasten content."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field


class ContentType(str, Enum):
    """Type of content being processed."""

    YOUTUBE = "youtube"
    PODCAST = "podcast"
    ARTICLE = "article"
    UNKNOWN = "unknown"


class ProcessedContent(BaseModel):
    """Content after initial processing (download/extraction)."""

    url: str
    content_type: ContentType
    title: str
    text_content: Optional[str] = None  # For articles
    audio_file: Optional[Path] = None  # For audio/video
    metadata: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class Transcript(BaseModel):
    """Transcription result from Whisper."""

    text: str
    source_file: Path
    language: Optional[str] = None
    duration: Optional[float] = None


class Concept(BaseModel):
    """A single concept extracted from content."""

    name: str
    description: str
    related_concepts: List[str] = Field(default_factory=list)
    quotes: List[str] = Field(default_factory=list)
    # Merge tracking
    merge_target: Optional[str] = None  # Filename of existing note to merge into
    is_new: bool = True  # False if merging into existing concept


class ZettelNote(BaseModel):
    """A single Zettelkasten note."""

    title: str
    content: str
    tags: List[str] = Field(default_factory=list)
    links: List[str] = Field(default_factory=list)
    source_url: Optional[str] = None
    source_type: Optional[ContentType] = None
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)
    # Merge tracking
    merge_target: Optional[str] = None  # Filename of existing note to merge into
    is_new: bool = True  # False if merging into existing concept

    def to_markdown(self) -> str:
        """Convert to Obsidian-compatible markdown."""
        lines = []

        # YAML frontmatter
        lines.append("---")
        lines.append(f"title: {self.title}")
        lines.append(f"created: {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if self.tags:
            lines.append(f"tags: [{', '.join(self.tags)}]")
        if self.source_url:
            lines.append(f"source: {self.source_url}")
        if self.source_type:
            lines.append(f"source_type: {self.source_type.value}")
        # Add merge metadata
        if self.merge_target:
            lines.append(f"merge_into: {self.merge_target}")
            lines.append(f"is_new: {str(self.is_new).lower()}")
        lines.append("---")
        lines.append("")

        # Add merge status banner if merging
        if not self.is_new and self.merge_target:
            lines.append("> **⚠️ MERGE**: This content will be merged into existing note: [[{merge_target}]]".replace("{merge_target}", self.merge_target.replace('.md', '')))
            lines.append("> Review and approve to add this content to the existing concept.")
            lines.append("")

        # Title
        lines.append(f"# {self.title}")
        lines.append("")

        # Content
        lines.append(self.content)
        lines.append("")

        # Links section if any
        if self.links:
            lines.append("## Related Notes")
            lines.append("")
            for link in self.links:
                lines.append(f"- [[{link}]]")
            lines.append("")

        return "\n".join(lines)

    def get_filename(self) -> str:
        """Generate a filename for this note."""
        # Slugify the title
        slug = self.title.lower()
        slug = slug.replace(" ", "-")
        # Remove special characters
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        # Add timestamp to ensure uniqueness
        timestamp = self.created_at.strftime("%Y%m%d%H%M%S")
        return f"{timestamp}-{slug}.md"
