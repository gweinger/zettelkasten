"""RSS feed management for podcast episodes."""

import requests
from pathlib import Path
from datetime import datetime
from typing import Optional
import feedparser


class RSSManager:
    """Manages local RSS feed file for podcast episodes."""

    def __init__(self, config):
        """Initialize RSS manager with config.

        Args:
            config: Config object with rss_feed_file and podcast_rss_feed settings
        """
        self.config = config
        self.rss_feed_url = config.podcast_rss_feed
        self.rss_feed_file = config.rss_feed_file

    def download_feed(self, url: Optional[str] = None, overwrite: bool = True) -> tuple[Path, dict]:
        """
        Download RSS feed from URL and save to local file.

        Args:
            url: RSS feed URL (defaults to config.podcast_rss_feed if not provided)
            overwrite: Whether to overwrite existing file (default: True)

        Returns:
            Tuple of (Path to saved file, dict with download info)

        Raises:
            ValueError: If no URL provided and none configured
            requests.RequestException: If download fails
        """
        feed_url = url or self.rss_feed_url
        if not feed_url:
            raise ValueError(
                "No RSS feed URL provided. Either pass url parameter or set PODCAST_RSS_FEED in .env"
            )

        # Check if file exists and overwrite is False
        if self.rss_feed_file.exists() and not overwrite:
            raise ValueError(
                f"RSS feed file already exists at {self.rss_feed_file}. "
                "Use overwrite=True to replace it."
            )

        # Ensure parent directories exist
        self.rss_feed_file.parent.mkdir(parents=True, exist_ok=True)

        # Download the RSS feed
        response = requests.get(feed_url, timeout=30)
        response.raise_for_status()

        # Save to file
        self.rss_feed_file.write_text(response.text, encoding='utf-8')

        # Parse feed for info
        feed = feedparser.parse(response.text)
        podcast_title = feed.feed.get('title', 'Unknown Podcast')
        episode_count = len(feed.entries)

        return self.rss_feed_file, {
            'url': feed_url,
            'podcast_title': podcast_title,
            'episode_count': episode_count,
            'downloaded_at': datetime.now(),
            'file_size_kb': self.rss_feed_file.stat().st_size / 1024,
        }

    def get_feed_info(self) -> Optional[dict]:
        """
        Get information about the local RSS feed.

        Returns:
            Dictionary with podcast and episode information, or None if file doesn't exist
        """
        if not self.rss_feed_file.exists():
            return None

        try:
            feed_content = self.rss_feed_file.read_text(encoding='utf-8')
            feed = feedparser.parse(feed_content)

            return {
                'podcast_title': feed.feed.get('title', 'Unknown Podcast'),
                'podcast_description': feed.feed.get('description', ''),
                'podcast_link': feed.feed.get('link', ''),
                'episode_count': len(feed.entries),
                'file_path': str(self.rss_feed_file),
                'file_size_kb': self.rss_feed_file.stat().st_size / 1024,
                'last_modified': datetime.fromtimestamp(
                    self.rss_feed_file.stat().st_mtime
                ),
            }
        except Exception as e:
            raise ValueError(f"Failed to parse RSS feed: {e}")

    def list_episodes(self) -> list[dict]:
        """
        Parse RSS feed and return list of episodes.

        Returns:
            List of episode dictionaries with title, description, link, etc.
        """
        if not self.rss_feed_file.exists():
            raise ValueError(f"RSS feed file not found at {self.rss_feed_file}")

        try:
            feed_content = self.rss_feed_file.read_text(encoding='utf-8')
            feed = feedparser.parse(feed_content)

            episodes = []
            for idx, entry in enumerate(feed.entries, 1):
                # Extract episode number from various possible tags
                episode_number = None
                if 'itunes_episode' in entry:
                    try:
                        episode_number = int(entry.get('itunes_episode', ''))
                    except (ValueError, TypeError):
                        pass
                if not episode_number and hasattr(entry, 'episode'):
                    try:
                        episode_number = int(entry.episode)
                    except (ValueError, TypeError):
                        pass

                # Extract season number
                season_number = None
                if 'itunes_season' in entry:
                    try:
                        season_number = int(entry.get('itunes_season', ''))
                    except (ValueError, TypeError):
                        pass

                # Extract keywords from itunes:keywords tag
                keywords = None
                if 'itunes_keywords' in entry:
                    keywords_str = entry.get('itunes_keywords', '')
                    if keywords_str:
                        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]

                # Extract author
                author = entry.get('author', '')
                if not author and 'itunes_author' in entry:
                    author = entry.get('itunes_author', '')

                # Extract image
                image_url = None
                if 'itunes_image' in entry:
                    image_url = entry.get('itunes_image', '')
                elif 'image' in entry:
                    image_url = entry.get('image', '')

                # Extract explicit flag
                explicit = entry.get('itunes_explicit', '').lower() in ['true', 'yes', 'explicit']

                # Extract episode type
                episode_type = entry.get('itunes_episodeType', 'full')

                # Extract enclosure
                enclosure_url = ''
                enclosure_type = ''
                enclosure_length = ''
                if entry.get('enclosures'):
                    enc = entry.get('enclosures', [{}])[0]
                    enclosure_url = enc.get('href', '')
                    enclosure_type = enc.get('type', '')
                    enclosure_length = enc.get('length', '')

                episodes.append({
                    'title': entry.get('title', f'Episode {idx}'),
                    'summary': entry.get('summary', ''),
                    'description': entry.get('summary', ''),
                    'link': entry.get('link', ''),
                    'pub_date': entry.get('published', ''),
                    'author': author,
                    'duration': entry.get('itunes_duration', ''),
                    'episode_number': episode_number,
                    'season_number': season_number,
                    'episode_type': episode_type,
                    'explicit': explicit,
                    'keywords': keywords,
                    'image_url': image_url,
                    'enclosure_url': enclosure_url,
                    'enclosure_type': enclosure_type,
                    'enclosure_length': enclosure_length,
                    'guid': entry.get('id', ''),
                    'raw_entry': entry,
                })

            return episodes

        except Exception as e:
            raise ValueError(f"Failed to parse RSS feed: {e}")

    def get_episode_by_title(self, title: str) -> Optional[dict]:
        """
        Find an episode in the RSS feed by title.

        Args:
            title: Episode title to search for

        Returns:
            Episode dictionary if found, None otherwise
        """
        try:
            episodes = self.list_episodes()
            for episode in episodes:
                if episode['title'].lower() == title.lower():
                    return episode
            return None
        except Exception:
            return None

    def find_matching_episode(self, search_term: str) -> Optional[dict]:
        """
        Find an episode in the RSS feed using fuzzy matching.

        Searches title and description for partial matches.

        Args:
            search_term: Text to search for (guest name, topic, etc.)

        Returns:
            Episode dictionary if found, None otherwise
        """
        try:
            episodes = self.list_episodes()
            search_lower = search_term.lower()

            # First try exact title match
            for episode in episodes:
                if search_lower == episode['title'].lower():
                    return episode

            # Then try search in title
            for episode in episodes:
                if search_lower in episode['title'].lower():
                    return episode

            # Finally try search in description
            for episode in episodes:
                if search_lower in episode['description'].lower():
                    return episode

            return None
        except Exception:
            return None

    def create_episode_rss(self, episode_data: dict, output_path: Path) -> Path:
        """
        Create a single-episode RSS feed file.

        Args:
            episode_data: Episode data dictionary from RSS feed
            output_path: Path where to save the episode.rss file

        Returns:
            Path to created RSS file
        """
        import xml.etree.ElementTree as ET

        # Create RSS structure
        rss = ET.Element('rss', version='2.0', attrib={
            'xmlns:itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'
        })
        channel = ET.SubElement(rss, 'channel')

        # Add channel metadata
        feed_info = self.get_feed_info()
        if feed_info:
            ET.SubElement(channel, 'title').text = feed_info['podcast_title']
            ET.SubElement(channel, 'description').text = feed_info['podcast_description']
            ET.SubElement(channel, 'link').text = feed_info['podcast_link']

        # Add single episode as item
        item = ET.SubElement(channel, 'item')
        ET.SubElement(item, 'title').text = episode_data['title']
        ET.SubElement(item, 'description').text = episode_data['description']
        ET.SubElement(item, 'pubDate').text = episode_data['pub_date']

        if episode_data['duration']:
            duration_elem = ET.SubElement(item, 'itunes:duration')
            duration_elem.text = episode_data['duration']

        if episode_data['enclosure_url']:
            ET.SubElement(item, 'enclosure', url=episode_data['enclosure_url'])

        # Pretty print and save
        if hasattr(ET, 'indent'):  # Python 3.9+
            ET.indent(rss, space='  ')
        tree = ET.ElementTree(rss)
        tree.write(output_path, encoding='utf-8', xml_declaration=True)

        return output_path
