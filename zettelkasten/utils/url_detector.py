"""URL detection and classification utilities."""

from urllib.parse import urlparse
from typing import Tuple
from zettelkasten.core.models import ContentType


def detect_content_type(url: str) -> Tuple[ContentType, dict]:
    """
    Detect the type of content from a URL.

    Args:
        url: The URL to analyze

    Returns:
        Tuple of (ContentType, metadata dict)
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    metadata = {"original_url": url}

    # YouTube detection
    if "youtube.com" in domain or "youtu.be" in domain:
        # Extract video ID
        if "youtu.be" in domain:
            video_id = parsed.path.lstrip("/")
        elif "youtube.com" in domain:
            # Handle both /watch?v= and /embed/ formats
            if "/watch" in parsed.path:
                from urllib.parse import parse_qs
                query = parse_qs(parsed.query)
                video_id = query.get("v", [None])[0]
            elif "/embed/" in parsed.path:
                video_id = parsed.path.split("/embed/")[1]
            else:
                video_id = None

        if video_id:
            metadata["video_id"] = video_id

        return ContentType.YOUTUBE, metadata

    # Podcast platforms
    podcast_domains = [
        "podcasts.apple.com",
        "open.spotify.com",
        "podcasts.google.com",
        "overcast.fm",
        "pocketcasts.com",
        "castro.fm",
    ]

    if any(pd in domain for pd in podcast_domains):
        metadata["platform"] = domain
        return ContentType.PODCAST, metadata

    # Default to article for web pages
    return ContentType.ARTICLE, metadata


def is_valid_url(url: str) -> bool:
    """Check if a string is a valid URL."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False
