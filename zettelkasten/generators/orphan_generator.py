"""Generate content for empty concept notes with AI-generated summaries."""

import re
from pathlib import Path
from zettelkasten.core.config import Config
from zettelkasten.processors.concept_extractor import ConceptExtractor


class OrphanNoteGenerator:
    """Generate summaries for empty concept notes using Claude."""

    def __init__(self, config: Config):
        """
        Initialize OrphanNoteGenerator.

        Args:
            config: Application configuration
        """
        self.config = config
        self.concept_extractor = ConceptExtractor(config)

    def fill_empty_note(self, filepath: Path) -> str:
        """
        Generate a summary for an empty note and return the updated content.

        Reads the existing note file, extracts the title from frontmatter,
        generates a summary using Claude, and returns the filled-out note content.

        Args:
            filepath: Path to the empty note file

        Returns:
            Updated markdown content with summary filled in
        """
        # Read the existing file
        content = filepath.read_text()

        # Extract frontmatter
        frontmatter_match = re.match(r"^(---\s*\n.*?\n---\s*\n)", content, re.DOTALL)
        if not frontmatter_match:
            raise ValueError(f"Note {filepath} does not have valid frontmatter")

        frontmatter = frontmatter_match.group(1)
        after_frontmatter = content[frontmatter_match.end():]

        # Extract title from frontmatter
        title_match = re.search(r"title:\s*(.+?)(?:\n|$)", frontmatter)
        if not title_match:
            raise ValueError(f"Could not extract title from {filepath}")

        title = title_match.group(1).strip().strip('"\'')

        # Extract title heading
        heading_match = re.search(r"^#\s+(.+?)$", after_frontmatter, re.MULTILINE)
        if not heading_match:
            raise ValueError(f"Could not find title heading in {filepath}")

        heading = heading_match.group(0)

        # Generate summary from Claude
        summary = self._generate_summary(title)

        # Build the updated content
        lines = []
        lines.append(frontmatter.rstrip())
        lines.append("")
        lines.append(heading)
        lines.append("")
        lines.append(summary)
        lines.append("")

        return "\n".join(lines)

    def _generate_summary(self, concept_name: str) -> str:
        """
        Generate a summary of a concept using Claude.

        Args:
            concept_name: Name of the concept to summarize

        Returns:
            Generated summary text
        """
        prompt = f"""Generate a clear, concise description of the concept "{concept_name}" suitable for a personal knowledge base.

The description should:
- Be 2-3 sentences
- Explain what the concept is and why it's important
- Be written in a way that helps build understanding
- Be actionable and practical where possible

Return only the description text, no JSON or formatting."""

        response = self.concept_extractor.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=512,
            temperature=0.5,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text.strip()
