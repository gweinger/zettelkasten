"""Manage podcast episode directories and files."""

from pathlib import Path
from typing import Optional
from zettelkasten.core.config import Config
from zettelkasten.core.models import Episode


class EpisodeManager:
    """Create and manage podcast episode directories and files."""

    def __init__(self, config: Config):
        """
        Initialize EpisodeManager.

        Args:
            config: Application configuration
        """
        self.config = config

    def create_episode_directory(self, episode: Episode) -> Path:
        """
        Create a new episode directory with all subdirectories and template files.

        Args:
            episode: Episode model with metadata

        Returns:
            Path to the created episode directory

        Raises:
            ValueError: If episode directory already exists
        """
        # Get episode directory path
        episode_dir_name = episode.get_directory_name()
        episode_dir = self.config.get_episode_dir(episode_dir_name)

        # Check if directory already exists
        if episode_dir.exists():
            raise ValueError(
                f"Episode directory already exists: {episode_dir}\n"
                f"Use a different guest name or title."
            )

        # Create main episode directory
        episode_dir.mkdir(parents=True, exist_ok=False)

        # Create promos subdirectory
        (episode_dir / "promos").mkdir(exist_ok=True)

        # Create index.md with episode metadata
        index_path = episode_dir / "index.md"
        index_content = episode.to_index_markdown()
        index_path.write_text(index_content)

        # Create template files
        self._create_template_files(episode_dir, episode)

        return episode_dir

    def _create_template_files(self, episode_dir: Path, episode: Episode) -> None:
        """
        Create template files for the episode.

        Args:
            episode_dir: Path to episode directory
            episode: Episode model with metadata
        """
        # Create prep conversation transcript template
        if episode.prep_transcript:
            prep_file = episode_dir / episode.prep_transcript
            prep_file.write_text(
                "# Prep Conversation Transcript\n\n"
                f"Episode: {episode.title}\n\n"
                "<!-- Add prep conversation transcript here -->\n"
            )

        # Create interview questions template
        if episode.interview_questions:
            questions_file = episode_dir / episode.interview_questions
            questions_content = [
                f"# Interview Questions - {episode.title}",
                "",
            ]
            if episode.guest_name:
                questions_content.append(f"**Guest:** {episode.guest_name}")
                questions_content.append("")

            questions_content.extend([
                "## Opening Questions",
                "",
                "1. <!-- Add question here -->",
                "",
                "## Main Discussion",
                "",
                "1. <!-- Add question here -->",
                "",
                "## Closing Questions",
                "",
                "1. <!-- Add question here -->",
                "",
            ])
            questions_file.write_text("\n".join(questions_content))

        # Create RSS description template
        if episode.rss_description:
            rss_file = episode_dir / episode.rss_description
            rss_content = [
                f"# RSS Description - {episode.title}",
                "",
            ]
            if episode.summary:
                rss_content.append(episode.summary)
                rss_content.append("")
            else:
                rss_content.append("<!-- Add RSS podcast description here -->")
                rss_content.append("")

            if episode.guest_name:
                rss_content.append(f"Guest: {episode.guest_name}")
                rss_content.append("")

            rss_content.extend([
                "## Show Notes",
                "",
                "<!-- Add show notes here -->",
                "",
            ])
            rss_file.write_text("\n".join(rss_content))

        # Create YouTube description template
        if episode.youtube_description:
            youtube_file = episode_dir / episode.youtube_description
            youtube_content = [
                f"# YouTube Description - {episode.title}",
                "",
            ]
            if episode.summary:
                youtube_content.append(episode.summary)
                youtube_content.append("")
            else:
                youtube_content.append("<!-- Add YouTube description here -->")
                youtube_content.append("")

            youtube_content.extend([
                "## Timestamps",
                "",
                "0:00 - Intro",
                "<!-- Add timestamps here -->",
                "",
                "## Links",
                "",
                "<!-- Add relevant links here -->",
                "",
            ])
            youtube_file.write_text("\n".join(youtube_content))

        # Create Substack description template
        if episode.substack_description:
            substack_file = episode_dir / episode.substack_description
            substack_content = [
                f"# Substack Description - {episode.title}",
                "",
            ]
            if episode.summary:
                substack_content.append(episode.summary)
                substack_content.append("")
            else:
                substack_content.append("<!-- Add Substack post content here -->")
                substack_content.append("")

            substack_content.extend([
                "## About This Episode",
                "",
                "<!-- Add episode details here -->",
                "",
            ])
            substack_file.write_text("\n".join(substack_content))

    def list_episodes(self) -> list[str]:
        """
        List all episode directories from all configured episode locations.

        Returns:
            List of episode directory names (deduplicated)
        """
        episode_names = set()

        # Search in all episode directories
        for episodes_path in self.config.get_all_episode_dirs():
            if not episodes_path.exists():
                continue

            for d in episodes_path.iterdir():
                if d.is_dir() and (d / "index.md").exists():
                    episode_names.add(d.name)

        return sorted(list(episode_names))

    def import_existing_episode(self, episode_dir_name: str, episode_number: Optional[int] = None) -> tuple[Path, Episode, dict]:
        """
        Import an existing episode directory that doesn't have an index.md.

        Intelligently detects files and creates the episode structure:
        - Largest .mp4 file -> podcast video
        - Largest .mp3/.wav file -> podcast audio
        - Files with "-ts.txt" pattern -> podcast transcript
        - .png files -> moved to promos/ folder
        - Automatically links to RSS feed data if available

        Args:
            episode_dir_name: Name of the existing episode directory
            episode_number: Optional episode number to assign (defaults to 999 if not found)

        Returns:
            Tuple of (episode_dir, Episode model, file_mapping dict)

        Raises:
            ValueError: If directory doesn't exist or already has index.md
        """
        # Search for the episode directory in all configured locations
        episode_dir = None
        for base_dir in self.config.get_all_episode_dirs():
            potential_path = base_dir / episode_dir_name
            if potential_path.exists():
                episode_dir = potential_path
                break

        if episode_dir is None:
            # If not found, default to main episodes path (for creating new)
            episode_dir = self.config.get_episode_dir(episode_dir_name)
            if not episode_dir.exists():
                raise ValueError(f"Episode directory does not exist: {episode_dir_name}")

        if (episode_dir / "index.md").exists():
            raise ValueError(f"Episode already indexed: {episode_dir}")

        # Scan for files
        all_files = list(episode_dir.iterdir())

        # Detect video files (mp4)
        video_files = [(f, f.stat().st_size) for f in all_files if f.suffix.lower() == '.mp4']
        video_files.sort(key=lambda x: x[1], reverse=True)  # Sort by size, largest first

        # Detect audio files (mp3, wav)
        audio_files = [(f, f.stat().st_size) for f in all_files
                       if f.suffix.lower() in ['.mp3', '.wav']]
        audio_files.sort(key=lambda x: x[1], reverse=True)  # Sort by size, largest first

        # Detect transcript files (*-ts.txt)
        transcript_files = [f for f in all_files
                           if f.suffix.lower() == '.txt' and '-ts.txt' in f.name.lower()]

        # Detect promo images (png files)
        promo_files = [f for f in all_files if f.suffix.lower() == '.png']

        # Create file mapping
        file_mapping = {
            'video': video_files[0][0] if video_files else None,
            'audio': audio_files[0][0] if audio_files else None,
            'transcript': transcript_files[0] if transcript_files else None,
            'promos': promo_files,
        }

        # Extract episode number from filenames if possible (unless provided)
        detected_episode_number = None
        if episode_number is None:
            for f in all_files:
                # Look for patterns like "Episode 30" or "Ep 30"
                import re
                match = re.search(r'[Ee]pisode?\s*(\d+)', f.name)
                if match:
                    detected_episode_number = int(match.group(1))
                    break

            # If no episode number detected and none provided, default to 999
            if detected_episode_number is None:
                detected_episode_number = 999
        else:
            detected_episode_number = episode_number

        # Create Episode model
        episode = Episode(
            title=episode_dir_name,
            guest_name=episode_dir_name,
            episode_number=detected_episode_number,
            podcast_video=file_mapping['video'].name if file_mapping['video'] else None,
            podcast_audio=file_mapping['audio'].name if file_mapping['audio'] else None,
            podcast_transcript=file_mapping['transcript'].name if file_mapping['transcript'] else None,
        )

        # Create promos directory if needed
        if promo_files:
            promos_dir = episode_dir / "promos"
            promos_dir.mkdir(exist_ok=True)

            # Move promo files
            for promo in promo_files:
                dest = promos_dir / promo.name
                if not dest.exists():
                    promo.rename(dest)

        # Create index.md
        index_path = episode_dir / "index.md"
        index_content = episode.to_index_markdown()
        index_path.write_text(index_content)

        # Create template files that don't exist
        self._create_template_files(episode_dir, episode)

        # Try to link to RSS feed if available
        self._link_rss_data_to_episode(episode_dir, episode_dir_name)

        return episode_dir, episode, file_mapping

    def _link_rss_data_to_episode(self, episode_dir: Path, episode_dir_name: str) -> bool:
        """
        Try to link RSS feed data to an imported episode.

        Updates the episode's index.md with RSS metadata if a matching
        episode is found in the RSS feed.

        Args:
            episode_dir: Path to the episode directory
            episode_dir_name: Name of the episode directory

        Returns:
            True if RSS data was found and linked, False otherwise
        """
        try:
            from zettelkasten.utils.rss_manager import RSSManager

            # Only proceed if RSS feed exists
            rss_manager = RSSManager(self.config)
            if not rss_manager.rss_feed_file.exists():
                return False

            # Try to find matching episode in RSS
            rss_episode = rss_manager.find_matching_episode(episode_dir_name)
            if not rss_episode:
                return False

            # Update index.md with RSS data
            index_file = episode_dir / "index.md"
            if not index_file.exists():
                return False

            import yaml
            content = index_file.read_text(encoding='utf-8')
            parts = content.split('---')

            if len(parts) < 3:
                return False

            frontmatter_str = parts[1]
            body = '---'.join(parts[2:])
            frontmatter = yaml.safe_load(frontmatter_str) or {}

            # Add comprehensive RSS metadata to frontmatter
            # Basic metadata
            frontmatter['rss_title'] = str(rss_episode['title']) if rss_episode.get('title') else ''
            frontmatter['rss_description'] = str(rss_episode['description'][:500]) if rss_episode.get('description') else ''
            frontmatter['rss_date'] = str(rss_episode['pub_date']) if rss_episode.get('pub_date') else ''

            # Episode/Season information
            if rss_episode.get('episode_number'):
                frontmatter['episode_number'] = int(rss_episode['episode_number'])
            if rss_episode.get('season_number'):
                frontmatter['season_number'] = int(rss_episode['season_number'])

            # Content metadata
            if rss_episode.get('author'):
                frontmatter['rss_author'] = str(rss_episode['author'])
            if rss_episode.get('duration'):
                frontmatter['duration'] = str(rss_episode['duration'])
            if rss_episode.get('episode_type'):
                frontmatter['episode_type'] = str(rss_episode['episode_type'])

            # Media information
            if rss_episode.get('image_url'):
                frontmatter['image_url'] = str(rss_episode['image_url'])
            if rss_episode.get('explicit'):
                frontmatter['explicit'] = bool(rss_episode['explicit'])

            # Enclosure information (audio/video file details)
            if rss_episode.get('enclosure_url'):
                frontmatter['enclosure_url'] = str(rss_episode['enclosure_url'])
            if rss_episode.get('enclosure_type'):
                frontmatter['enclosure_type'] = str(rss_episode['enclosure_type'])
            if rss_episode.get('enclosure_length'):
                frontmatter['enclosure_length'] = str(rss_episode['enclosure_length'])

            # Keywords - ensure it's a list of strings
            if rss_episode.get('keywords'):
                keywords = rss_episode['keywords']
                if isinstance(keywords, list):
                    frontmatter['keywords'] = [str(k) for k in keywords]
                else:
                    frontmatter['keywords'] = [str(keywords)]

            # Link back to episode on web
            if rss_episode.get('link'):
                frontmatter['rss_link'] = str(rss_episode['link'])

            # GUID for reference
            if rss_episode.get('guid'):
                frontmatter['rss_guid'] = str(rss_episode['guid'])

            # Write back updated frontmatter with safe YAML dumper
            # Use default_flow_style=False and allow_unicode=True for clean output
            new_frontmatter = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True)
            updated_content = f"---\n{new_frontmatter}---{body}"
            index_file.write_text(updated_content, encoding='utf-8')

            return True

        except Exception:
            # Silently fail if RSS linking doesn't work
            return False
