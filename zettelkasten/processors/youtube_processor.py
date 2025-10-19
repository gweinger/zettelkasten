"""YouTube video content processor."""

import yt_dlp
from pathlib import Path
from typing import Optional
from zettelkasten.core.models import ProcessedContent, ContentType
from zettelkasten.core.config import Config


class YouTubeProcessor:
    """Process YouTube videos - download audio and extract metadata."""

    def __init__(self, config: Config):
        self.config = config
        self.config.ensure_directories()

    def process(self, url: str, video_id: Optional[str] = None) -> ProcessedContent:
        """
        Download YouTube video audio and extract metadata.

        Args:
            url: YouTube URL
            video_id: Optional video ID (extracted from URL if not provided)

        Returns:
            ProcessedContent with audio file and metadata
        """
        # Configure yt-dlp options
        output_path = self.config.downloads_path / f"youtube_{video_id or 'video'}.%(ext)s"

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(output_path),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "quiet": False,
            "no_warnings": False,
        }

        # Download and extract info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            # Get the actual downloaded file path
            audio_file = self.config.downloads_path / f"youtube_{video_id or info['id']}.mp3"

            metadata = {
                "video_id": info.get("id"),
                "title": info.get("title"),
                "description": info.get("description"),
                "uploader": info.get("uploader"),
                "upload_date": info.get("upload_date"),
                "duration": info.get("duration"),
                "view_count": info.get("view_count"),
                "like_count": info.get("like_count"),
                "channel": info.get("channel"),
                "channel_url": info.get("channel_url"),
                "tags": info.get("tags", []),
            }

            return ProcessedContent(
                url=url,
                content_type=ContentType.YOUTUBE,
                title=info.get("title", "Untitled YouTube Video"),
                audio_file=audio_file,
                metadata=metadata,
            )

    def cleanup(self, audio_file: Path) -> None:
        """Delete downloaded audio file after processing."""
        if audio_file and audio_file.exists():
            audio_file.unlink()
