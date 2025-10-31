"""Configuration management for Zettelkasten CLI."""

from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional, Union
import os
from dotenv import load_dotenv

from zettelkasten.utils.project_root import find_project_root


class Config(BaseModel):
    """Application configuration."""

    # API Keys
    anthropic_api_key: str = Field(..., description="Anthropic API key for Claude (concept extraction)")

    # Whisper Configuration
    whisper_model_size: str = Field(
        default="base",
        description="Local Whisper model size (tiny, base, small, medium, large)",
    )

    # Podcast Configuration
    podcast_rss_feed: str = Field(
        default="",
        description="RSS feed URL for the podcast",
    )

    # Vault Configuration
    vault_name: str = Field(
        default="Your Zettelkasten",
        description="Display name for your vault (shown in web UI)",
    )

    # Paths
    vault_path: Path = Field(
        default=Path("./vault"),
        description="Path to Obsidian vault",
    )
    # Note: sources/ contains source materials (articles, audio, video, transcripts)
    # and summaries/ contains source reference notes (summaries of sources)
    summaries_path: Path = Field(
        default=Path("./vault/sources/summaries"),
        description="Path for source summary/reference notes",
    )
    audio_path: Path = Field(
        default=Path("./vault/sources/audio"),
        description="Path for downloaded audio files",
    )
    video_path: Path = Field(
        default=Path("./vault/sources/video"),
        description="Path for downloaded video files",
    )
    transcripts_path: Path = Field(
        default=Path("./vault/sources/transcripts"),
        description="Path for transcript files",
    )
    articles_path: Path = Field(
        default=Path("./vault/sources/articles"),
        description="Path for saved article full text",
    )
    episodes_path: Path = Field(
        default=Path("./vault/sources/episodes"),
        description="Path for podcast episodes",
    )
    additional_episode_dirs: list[Path] = Field(
        default_factory=list,
        description="Additional directories to search for episodes",
    )
    rss_feed_file: Path = Field(
        default=Path("./vault/sources/podcast.rss"),
        description="Path to store local RSS feed file",
    )

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables.

        Automatically detects the project root and changes to that directory
        before loading configuration, allowing the tool to be run from anywhere.
        """
        # Find project root
        project_root = find_project_root()
        if project_root is None:
            raise ValueError(
                "Could not find Zettelkasten project root. "
                "Make sure you're running this command within a Zettelkasten project "
                "or initialize a new project first."
            )

        # Change to project root directory
        os.chdir(project_root)

        # Load .env from project root
        load_dotenv(project_root / ".env")

        # Get vault path first
        vault_path = Path(os.getenv("VAULT_PATH", "./vault"))

        # Get base sources path (sources/ contains summaries and materials)
        sources_base = vault_path / "sources"

        # Parse additional episode directories
        additional_dirs = []
        additional_dirs_str = os.getenv("ADDITIONAL_EPISODE_DIRS", "")
        if additional_dirs_str:
            for dir_str in additional_dirs_str.split(","):
                dir_str = dir_str.strip()
                if dir_str:
                    additional_dirs.append(Path(dir_str).expanduser())

        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            whisper_model_size=os.getenv("WHISPER_MODEL_SIZE", "base"),
            podcast_rss_feed=os.getenv("PODCAST_RSS_FEED", ""),
            vault_name=os.getenv("VAULT_NAME", "Your Zettelkasten"),
            vault_path=vault_path,
            summaries_path=Path(os.getenv("SUMMARIES_PATH", str(sources_base / "summaries"))),
            audio_path=Path(os.getenv("AUDIO_PATH", str(sources_base / "audio"))),
            video_path=Path(os.getenv("VIDEO_PATH", str(sources_base / "video"))),
            transcripts_path=Path(os.getenv("TRANSCRIPTS_PATH", str(sources_base / "transcripts"))),
            articles_path=Path(os.getenv("ARTICLES_PATH", str(sources_base / "articles"))),
            episodes_path=Path(os.getenv("EPISODES_PATH", str(sources_base / "episodes"))),
            additional_episode_dirs=additional_dirs,
            rss_feed_file=Path(os.getenv("RSS_FEED_FILE", str(sources_base / "podcast.rss"))),
        )

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.vault_path.mkdir(parents=True, exist_ok=True)

        # Create Zettelkasten subdirectories
        (self.vault_path / "permanent-notes").mkdir(parents=True, exist_ok=True)
        (self.vault_path / "sources").mkdir(parents=True, exist_ok=True)
        (self.vault_path / "fleeting-notes").mkdir(parents=True, exist_ok=True)
        (self.vault_path / "inbox").mkdir(parents=True, exist_ok=True)
        (self.vault_path / "staging").mkdir(parents=True, exist_ok=True)

        # Create sources subdirectories (summaries and materials)
        self.summaries_path.mkdir(parents=True, exist_ok=True)
        self.audio_path.mkdir(parents=True, exist_ok=True)
        self.video_path.mkdir(parents=True, exist_ok=True)
        self.transcripts_path.mkdir(parents=True, exist_ok=True)
        self.articles_path.mkdir(parents=True, exist_ok=True)
        self.episodes_path.mkdir(parents=True, exist_ok=True)

        # Create inbox subdirectories for classification
        (self.vault_path / "inbox" / "concepts").mkdir(parents=True, exist_ok=True)
        (self.vault_path / "inbox" / "sources").mkdir(parents=True, exist_ok=True)

        # Create staging subdirectories to organize staged notes
        (self.vault_path / "staging" / "concepts").mkdir(parents=True, exist_ok=True)
        (self.vault_path / "staging" / "sources").mkdir(parents=True, exist_ok=True)

    def get_permanent_notes_path(self) -> Path:
        """Get path to permanent notes directory."""
        return self.vault_path / "permanent-notes"

    def get_sources_path(self) -> Path:
        """Get path to source summaries directory (where source notes are saved)."""
        return self.summaries_path

    def get_sources_base_path(self) -> Path:
        """Get path to sources base directory (contains summaries and materials)."""
        return self.vault_path / "sources"

    def get_fleeting_notes_path(self) -> Path:
        """Get path to fleeting notes directory."""
        return self.vault_path / "fleeting-notes"

    def get_inbox_path(self) -> Path:
        """Get path to inbox directory."""
        return self.vault_path / "inbox"

    def get_staging_path(self) -> Path:
        """Get path to staging directory."""
        return self.vault_path / "staging"

    def get_episodes_path(self) -> Path:
        """Get path to episodes directory."""
        return self.episodes_path

    def get_episode_dir(self, episode_name: str) -> Path:
        """Get path to a specific episode directory."""
        return self.episodes_path / episode_name

    def get_all_episode_dirs(self) -> list[Path]:
        """Get all directories where episodes can be found (main + additional)."""
        dirs = [self.episodes_path]
        dirs.extend(self.additional_episode_dirs)
        return dirs

    def find_episode_path(self, episode_name: str) -> Optional[Path]:
        """
        Find the path to an episode directory by searching all episode directories.

        Args:
            episode_name: Name of the episode directory to find

        Returns:
            Path to the episode directory if found, None otherwise
        """
        for base_dir in self.get_all_episode_dirs():
            if not base_dir.exists():
                continue
            episode_path = base_dir / episode_name
            if episode_path.exists() and episode_path.is_dir():
                return episode_path
        return None
