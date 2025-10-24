"""Generate concept notes for orphan concepts with AI-generated summaries."""

from datetime import datetime
from typing import List
from pathlib import Path
from zettelkasten.core.models import ZettelNote
from zettelkasten.core.config import Config
from zettelkasten.processors.concept_extractor import ConceptExtractor


class OrphanNoteGenerator:
    """Generate concept notes for orphan concepts with Claude summaries."""

    def __init__(self, config: Config):
        """
        Initialize OrphanNoteGenerator.

        Args:
            config: Application configuration
        """
        self.config = config
        self.concept_extractor = ConceptExtractor(config)

    def generate_orphan_note(
        self,
        orphan_name: str,
        backlinks: List[str],
        context_notes: List[str] = None,
    ) -> ZettelNote:
        """
        Generate a templated note for an orphan concept.

        Uses Claude to generate a summary of the concept based on context from
        the notes that reference it.

        Args:
            orphan_name: Name of the orphan concept
            backlinks: List of note titles that reference this orphan
            context_notes: Optional list of full note contents for better context

        Returns:
            ZettelNote object ready to save
        """
        # Generate summary from Claude using backlink context
        summary = self._generate_summary_from_context(
            orphan_name, backlinks, context_notes
        )

        # Build the note content
        created_at = datetime.now()
        lines = []

        # Add the summary
        lines.append(summary)
        lines.append("")

        note_content = "\n".join(lines)

        # Build links for the backlinks
        links = []
        for backlink in backlinks:
            # Create safe filename slug
            slug = backlink.lower().replace(" ", "-")
            slug = "".join(c for c in slug if c.isalnum() or c == "-")
            # Use the relative path pattern - ZettelNote.to_markdown() will wrap this in [[...]]
            links.append(f"permanent-notes/{slug}|{backlink}")

        # Create the note object
        return ZettelNote(
            title=orphan_name,
            content=note_content,
            tags=["concept", "permanent-note", "orphan-stub"],
            links=links,
            created_at=created_at,
            metadata={
                "related_concepts": backlinks,
                "is_orphan_stub": True,
            },
        )

    def _generate_summary_from_context(
        self,
        orphan_name: str,
        backlinks: List[str],
        context_notes: List[str] = None,
    ) -> str:
        """
        Generate a summary of the orphan concept using Claude.

        Uses context from the notes that reference the concept.

        Args:
            orphan_name: Name of the concept
            backlinks: Titles of notes that reference this concept
            context_notes: Optional full contents of backlinked notes

        Returns:
            Generated summary text
        """
        # Build context from backlinks
        backlink_text = "\n".join([f"- {link}" for link in backlinks])

        context_info = ""
        if context_notes:
            # Include snippets from context notes
            context_info = "\n\nContext from referencing notes:\n"
            for note_content in context_notes[:3]:  # Limit to first 3 for token usage
                # Extract first paragraph
                first_para = note_content.split("\n\n")[0]
                if first_para:
                    context_info += f"\n{first_para[:500]}..."

        prompt = f"""Based on the following information, generate a concise description of the concept "{orphan_name}".

This concept is referenced in these notes:
{backlink_text}
{context_info}

Generate a clear, actionable description (2-3 sentences) of what this concept is, suitable for a personal knowledge base.
Focus on how it relates to the topics in the referencing notes.

Return only the description text, no JSON or formatting."""

        response = self.concept_extractor.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=512,
            temperature=0.5,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text.strip()
