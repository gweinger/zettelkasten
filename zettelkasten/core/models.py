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


class Episode(BaseModel):
    """A podcast episode with all associated content and metadata."""

    # Core metadata
    title: str
    guest_name: Optional[str] = None
    episode_number: Optional[int] = None
    recording_date: Optional[datetime] = None
    publish_date: Optional[datetime] = None
    duration_minutes: Optional[int] = None

    # Status tracking
    status: str = "planning"  # planning, recorded, editing, published

    # Content descriptions
    summary: Optional[str] = None  # Brief episode summary
    topics: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    # File tracking (relative to episode directory)
    prep_transcript: Optional[str] = "prep conversation transcript.txt"
    interview_questions: Optional[str] = "interview questions.md"
    podcast_video: Optional[str] = None  # e.g., "podcast video.mp4"
    podcast_audio: Optional[str] = None  # e.g., "podcast audio.wav"
    podcast_transcript: Optional[str] = None  # e.g., "podcast transcript.txt"
    minisode_audio: Optional[str] = None  # e.g., "podcast minisode.wav"
    rss_description: Optional[str] = "RSS description.md"
    youtube_description: Optional[str] = "YouTube description.md"
    substack_description: Optional[str] = "Substack description.md"

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def to_yaml_frontmatter(self) -> str:
        """Convert to YAML frontmatter for index.md."""
        lines = ["---"]

        # Basic info
        lines.append(f"title: \"{self.title}\"")
        if self.guest_name:
            lines.append(f"guest: \"{self.guest_name}\"")
        if self.episode_number:
            lines.append(f"episode_number: {self.episode_number}")

        # Dates
        lines.append(f"created: {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"updated: {self.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if self.recording_date:
            lines.append(f"recording_date: {self.recording_date.strftime('%Y-%m-%d')}")
        if self.publish_date:
            lines.append(f"publish_date: {self.publish_date.strftime('%Y-%m-%d')}")

        # Status and metadata
        lines.append(f"status: {self.status}")
        if self.duration_minutes:
            lines.append(f"duration_minutes: {self.duration_minutes}")

        # Lists
        if self.topics:
            lines.append(f"topics: [{', '.join(self.topics)}]")
        if self.tags:
            lines.append(f"tags: [{', '.join(self.tags)}]")

        # File references
        if self.prep_transcript:
            lines.append(f"prep_transcript: \"{self.prep_transcript}\"")
        if self.interview_questions:
            lines.append(f"interview_questions: \"{self.interview_questions}\"")
        if self.podcast_video:
            lines.append(f"podcast_video: \"{self.podcast_video}\"")
        if self.podcast_audio:
            lines.append(f"podcast_audio: \"{self.podcast_audio}\"")
        if self.podcast_transcript:
            lines.append(f"podcast_transcript: \"{self.podcast_transcript}\"")
        if self.minisode_audio:
            lines.append(f"minisode_audio: \"{self.minisode_audio}\"")
        if self.rss_description:
            lines.append(f"rss_description: \"{self.rss_description}\"")
        if self.youtube_description:
            lines.append(f"youtube_description: \"{self.youtube_description}\"")
        if self.substack_description:
            lines.append(f"substack_description: \"{self.substack_description}\"")

        lines.append("---")
        return "\n".join(lines)

    def to_index_markdown(self) -> str:
        """Generate complete index.md content for the episode."""
        lines = []

        # Add YAML frontmatter
        lines.append(self.to_yaml_frontmatter())
        lines.append("")

        # Title
        lines.append(f"# {self.title}")
        lines.append("")

        # Summary
        if self.summary:
            lines.append("## Summary")
            lines.append("")
            lines.append(self.summary)
            lines.append("")

        # Topics
        if self.topics:
            lines.append("## Topics")
            lines.append("")
            for topic in self.topics:
                lines.append(f"- {topic}")
            lines.append("")

        # Files
        lines.append("## Episode Files")
        lines.append("")
        lines.append("### Preparation")
        if self.prep_transcript:
            lines.append(f"- [{self.prep_transcript}]({self.prep_transcript})")
        if self.interview_questions:
            lines.append(f"- [{self.interview_questions}]({self.interview_questions})")
        lines.append("")

        lines.append("### Production")
        if self.podcast_video:
            lines.append(f"- [{self.podcast_video}]({self.podcast_video})")
        if self.podcast_audio:
            lines.append(f"- [{self.podcast_audio}]({self.podcast_audio})")
        if self.podcast_transcript:
            lines.append(f"- [{self.podcast_transcript}]({self.podcast_transcript})")
        if self.minisode_audio:
            lines.append(f"- [{self.minisode_audio}]({self.minisode_audio})")
        lines.append("")

        lines.append("### Publishing")
        if self.rss_description:
            lines.append(f"- [{self.rss_description}]({self.rss_description})")
        if self.youtube_description:
            lines.append(f"- [{self.youtube_description}]({self.youtube_description})")
        if self.substack_description:
            lines.append(f"- [{self.substack_description}]({self.substack_description})")
        lines.append("")

        lines.append("### Promos")
        lines.append("- [promos/](promos/)")
        lines.append("")

        return "\n".join(lines)

    def get_directory_name(self) -> str:
        """Generate directory name for this episode."""
        if self.guest_name:
            # Use guest name as directory name (slugified)
            slug = self.guest_name.lower()
            slug = slug.replace(" ", "-")
            slug = "".join(c for c in slug if c.isalnum() or c == "-")
            return slug
        else:
            # Fallback to title-based slug
            slug = self.title.lower()
            slug = slug.replace(" ", "-")
            slug = "".join(c for c in slug if c.isalnum() or c == "-")
            return slug


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
