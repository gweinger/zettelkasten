"""Generate interview questions using Claude API."""

from pathlib import Path
from typing import Optional
import anthropic


class InterviewQuestionGenerator:
    """Generate interview questions for podcast episodes using Claude."""

    def __init__(self, config):
        """
        Initialize the interview question generator.

        Args:
            config: Application configuration with API key
        """
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        # Look for podcast_context in the vault/workflows directory
        self.context_dir = config.vault_path / "workflows" / "podcast_context"

    def load_prompt(self) -> str:
        """Load the interview prompt template."""
        prompt_file = self.context_dir / "interview_prompt.md"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Interview prompt not found: {prompt_file}")
        return prompt_file.read_text(encoding='utf-8')

    def load_podcast_context(self) -> str:
        """Load podcast context information."""
        context_file = self.context_dir / "podcast_context.txt"
        if not context_file.exists():
            raise FileNotFoundError(f"Podcast context not found: {context_file}")
        return context_file.read_text(encoding='utf-8')

    def load_seo_keywords(self) -> str:
        """Load SEO keywords."""
        keywords_file = self.context_dir / "seo_keywords.txt"
        if not keywords_file.exists():
            raise FileNotFoundError(f"SEO keywords file not found: {keywords_file}")
        keywords = keywords_file.read_text(encoding='utf-8').strip().split('\n')
        return ', '.join(keywords)

    def extract_from_transcript(self, transcript_path: Path) -> dict:
        """
        Extract key information from prep transcript using Claude.

        Args:
            transcript_path: Path to the prep conversation transcript

        Args:
            dict: Extracted information (background, key_topics)
        """
        if not transcript_path.exists():
            return {"background": "", "key_topics": ""}

        transcript_text = transcript_path.read_text(encoding='utf-8')

        if not transcript_text.strip() or "Add prep conversation transcript here" in transcript_text:
            return {"background": "", "key_topics": ""}

        # Use Claude to extract key information from the transcript
        message = self.client.messages.create(
            model="claude-opus-4-1-20250805",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"""Please analyze this prep conversation transcript and extract:
1. Brief background about the guest (2-3 sentences)
2. Key topics they discuss (5-7 bullet points)

Format your response as:
BACKGROUND:
[background text]

KEY_TOPICS:
[bullet points]

Transcript:
{transcript_text}"""
                }
            ]
        )

        response_text = message.content[0].text
        parts = response_text.split('KEY_TOPICS:')

        background = parts[0].replace('BACKGROUND:', '').strip() if parts else ""
        key_topics = parts[1].strip() if len(parts) > 1 else ""

        return {
            "background": background,
            "key_topics": key_topics
        }

    def generate_questions(
        self,
        guest_name: str,
        transcript_path: Optional[Path] = None,
        background: Optional[str] = None,
        key_topics: Optional[str] = None,
    ) -> str:
        """
        Generate interview questions for a guest.

        Args:
            guest_name: Name of the guest
            transcript_path: Path to prep conversation transcript (optional)
            background: Guest background information (optional, can be extracted from transcript)
            key_topics: Key topics to discuss (optional, can be extracted from transcript)

        Returns:
            str: Generated interview questions in markdown format
        """
        # Extract from transcript if not provided
        if not background or not key_topics:
            if transcript_path:
                extracted = self.extract_from_transcript(transcript_path)
                background = background or extracted["background"]
                key_topics = key_topics or extracted["key_topics"]

        # Use defaults if still missing
        if not background:
            background = "Information will be extracted from the conversation."
        if not key_topics:
            key_topics = "To be determined from the interview."

        # Load templates and context
        prompt_template = self.load_prompt()
        podcast_context = self.load_podcast_context()
        seo_keywords = self.load_seo_keywords()

        # Fill in the template
        system_prompt = prompt_template.format(
            GUEST_NAME=guest_name,
            GUEST_BACKGROUND=background,
            KEY_TOPICS=key_topics,
            SEO_KEYWORDS=seo_keywords,
            PODCAST_CONTEXT=podcast_context,
        )

        # Generate questions using Claude
        message = self.client.messages.create(
            model="claude-opus-4-1-20250805",
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": system_prompt
                }
            ]
        )

        return message.content[0].text

    def save_questions(self, questions: str, output_path: Path) -> None:
        """
        Save generated questions to a file.

        Args:
            questions: Generated questions markdown
            output_path: Path where to save the file
        """
        output_path.write_text(questions, encoding='utf-8')

    def ensure_episode_index(self, guest_name: str, episode_path: Path) -> None:
        """
        Ensure an index.md file exists and is populated with all episode files.
        Uses EpisodeManager to properly generate the index with file links.

        Args:
            guest_name: Name of the guest
            episode_path: Path to the episode directory
        """
        index_file = episode_path / "index.md"

        # Use EpisodeManager to import/refresh the episode and regenerate index with all files
        try:
            from zettelkasten.utils.episode_manager import EpisodeManager
            manager = EpisodeManager(self.config)

            # Import the episode which will regenerate the index.md with all files listed
            manager.import_existing_episode(episode_path.name)
        except Exception:
            # Fallback: if import fails, create a basic index
            if index_file.exists():
                return

            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')

            index_content = f"""---
title: "{guest_name}"
date: {today}
type: episode
guest: "{guest_name}"
---

# {guest_name}

Episode with {guest_name}.
"""
            index_file.write_text(index_content, encoding='utf-8')

    def ensure_person_note(self, guest_name: str, transcript_path: Optional[Path] = None, background: Optional[str] = None) -> None:
        """
        Ensure a person note exists in the permanent-notes directory for the guest.
        Creates one if it doesn't exist, enriched with background information.

        Args:
            guest_name: Name of the guest
            transcript_path: Optional path to prep transcript for extracting background
            background: Optional background information about the guest
        """
        permanent_notes_dir = self.config.get_permanent_notes_path()

        # Create a safe filename from the guest name
        safe_filename = guest_name.lower().replace(" ", "-") + ".md"
        person_file = permanent_notes_dir / safe_filename

        # If file already exists, don't overwrite it
        if person_file.exists():
            return

        # Extract background if not provided
        if not background and transcript_path and transcript_path.exists():
            extracted = self.extract_from_transcript(transcript_path)
            background = extracted.get("background", "")

        # Create person note with enriched content
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')

        # Build the note content
        person_content = f"""---
title: "{guest_name}"
date: {today}
tags: [person, guest]
---

# {guest_name}

"""
        if background:
            person_content += f"{background}\n"
        else:
            person_content += "Podcast guest.\n"

        person_file.write_text(person_content, encoding='utf-8')
