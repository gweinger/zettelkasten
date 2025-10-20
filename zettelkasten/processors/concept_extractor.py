"""Concept extraction using Claude for Zettelkasten generation."""

import json
from typing import List
from anthropic import Anthropic
from zettelkasten.core.models import Concept
from zettelkasten.core.config import Config


class ConceptExtractor:
    """Extract concepts and generate Zettelkasten-style notes using Claude."""

    def __init__(self, config: Config):
        self.config = config
        self.client = Anthropic(api_key=config.anthropic_api_key)

    def extract_concepts(
        self,
        text: str,
        title: str,
        source_url: str,
        max_concepts: int = 10,
    ) -> List[Concept]:
        """
        Extract key concepts from text using Claude.

        Args:
            text: The text to analyze
            title: Title of the source content
            source_url: URL of the source
            max_concepts: Maximum number of concepts to extract

        Returns:
            List of Concept objects
        """
        prompt = f"""You are an expert at analyzing content and extracting key concepts for a Zettelkasten knowledge management system.

Your task is to:
1. Identify the main concepts, ideas, and themes in the content
2. For each concept, provide a clear description
3. Identify relationships between concepts - BOTH within this content AND to broader topics/concepts
4. Extract relevant quotes that support each concept

Focus on:
- Actionable insights
- Core ideas and principles
- Frameworks and mental models
- Practical applications
- Unique perspectives

IMPORTANT for related_concepts:
- For each concept, suggest 3-6 related concepts
- Include BOTH concepts from this content AND broader related topics
- Think about what other concepts would be useful to link to (even if not explicitly in this text)
- Examples: if discussing "change," also mention "Growth Mindset," "Resistance," "Habits," etc.
- These connections help build a rich knowledge graph

Analyze this content and extract key concepts for a Zettelkasten:

Title: {title}
Source: {source_url}

Content:
{text[:15000]}

Extract up to {max_concepts} concepts. Focus on the most important and actionable ideas.

Return your analysis as a JSON object with this structure:
{{
  "concepts": [
    {{
      "name": "Concept Name",
      "description": "Clear, concise description of the concept",
      "related_concepts": ["Related Concept 1", "Related Concept 2", "Broader Topic 1", "Broader Topic 2"],
      "quotes": ["Relevant quote from the text"]
    }}
  ]
}}

IMPORTANT: Return ONLY valid JSON. Do NOT use smart quotes or curly quotes. Escape any quotes inside strings properly with backslashes."""

        response = self.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=4096,
            temperature=0.7,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        # Parse response - Claude returns text content
        content_text = response.content[0].text

        # Extract JSON from the response (Claude might wrap it in markdown)
        if "```json" in content_text:
            # Extract JSON from markdown code block
            json_start = content_text.find("```json") + 7
            json_end = content_text.find("```", json_start)
            content_text = content_text[json_start:json_end].strip()
        elif "```" in content_text:
            # Extract from generic code block
            json_start = content_text.find("```") + 3
            json_end = content_text.find("```", json_start)
            content_text = content_text[json_start:json_end].strip()

        # Fix smart quotes (curly quotes) that break JSON parsing
        content_text = content_text.replace('"', '"').replace('"', '"')
        content_text = content_text.replace("'", "'").replace("'", "'")

        try:
            data = json.loads(content_text)
        except json.JSONDecodeError as e:
            # Try to fix common JSON issues
            import re

            # Remove trailing commas before closing brackets/braces
            fixed_text = re.sub(r',(\s*[}\]])', r'\1', content_text)

            # Try to manually fix unescaped quotes by using a simple heuristic:
            # Replace quotes inside string values (between ": " and ",)
            # This is imperfect but handles the most common case
            lines = fixed_text.split('\n')
            fixed_lines = []
            for line in lines:
                # If line contains both ": " and ends with "," it's likely a JSON value
                if '": "' in line and (line.rstrip().endswith('",') or line.rstrip().endswith('"')):
                    # Find the value part after ": "
                    parts = line.split('": "', 1)
                    if len(parts) == 2:
                        key_part = parts[0] + '": "'
                        value_part = parts[1]
                        # Escape quotes in the value part (but not the closing quote)
                        if value_part.rstrip().endswith('",'):
                            value_content = value_part[:-2]  # Remove trailing ",
                            value_fixed = value_content.replace('"', '\\"')
                            line = key_part + value_fixed + '",'
                        elif value_part.rstrip().endswith('"'):
                            value_content = value_part[:-1]  # Remove trailing "
                            value_fixed = value_content.replace('"', '\\"')
                            line = key_part + value_fixed + '"'
                fixed_lines.append(line)
            fixed_text = '\n'.join(fixed_lines)

            try:
                data = json.loads(fixed_text)
            except json.JSONDecodeError as e2:
                # If still fails, save the raw response for debugging and return empty concepts
                print(f"Warning: Failed to parse concept extraction response: {e}")
                print(f"First 500 chars of response: {content_text[:500]}")

                # Try to save the problematic response to a debug file
                try:
                    import tempfile
                    from pathlib import Path
                    debug_file = Path(tempfile.gettempdir()) / "zk_concept_extraction_error.json"
                    debug_file.write_text(content_text)
                    print(f"Full response saved to: {debug_file}")
                except Exception:
                    pass

                return []

        # Convert to Concept objects
        concepts = []
        for concept_data in data.get("concepts", [])[:max_concepts]:
            concepts.append(
                Concept(
                    name=concept_data.get("name", "Untitled Concept"),
                    description=concept_data.get("description", ""),
                    related_concepts=concept_data.get("related_concepts", []),
                    quotes=concept_data.get("quotes", []),
                )
            )

        return concepts

    def generate_summary(self, text: str, title: str) -> str:
        """
        Generate a concise summary of the content.

        Args:
            text: The text to summarize
            title: Title of the content

        Returns:
            Summary text
        """
        prompt = f"""You are an expert at creating concise, insightful summaries for a Zettelkasten knowledge base.

Create a summary that:
- Captures the main ideas and key points
- Is written in clear, accessible language
- Highlights actionable insights
- Is 2-4 paragraphs long

Summarize this content:

Title: {title}

Content:
{text[:10000]}"""

        response = self.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1024,
            temperature=0.7,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        return response.content[0].text

    def find_related_concepts(
        self, note_content: str, note_title: str, existing_concepts: List[str]
    ) -> List[str]:
        """
        Analyze a note and find which existing concepts in the KB are related.

        Args:
            note_content: The text content of the note to analyze
            note_title: Title of the note
            existing_concepts: List of existing concept titles in the vault

        Returns:
            List of related concept titles from the existing KB
        """
        # If there are no existing concepts, return empty list
        if not existing_concepts:
            return []

        # Format the existing concepts for the prompt
        concepts_list = "\n".join([f"- {concept}" for concept in existing_concepts])

        prompt = f"""You are an expert at analyzing notes and finding conceptual relationships in a Zettelkasten knowledge base.

Your task: Analyze this note and identify which existing concepts from the knowledge base are related to it.

Note Title: {note_title}

Note Content:
{note_content[:10000]}

Existing Concepts in Knowledge Base:
{concepts_list}

Instructions:
1. Read the note carefully and understand its main ideas
2. Review the list of existing concepts
3. Select concepts that are:
   - Directly related to topics discussed in the note
   - Share similar themes or principles
   - Would provide valuable context or connections
   - Help create a rich knowledge graph
4. Return 3-10 related concepts (or fewer if there aren't many good matches)
5. Only select concepts that genuinely relate to this note's content

Return your analysis as a JSON object:
{{
  "related_concepts": ["Concept Name 1", "Concept Name 2", "Concept Name 3"]
}}

IMPORTANT: Only include concept names that appear in the "Existing Concepts in Knowledge Base" list above."""

        response = self.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1024,
            temperature=0.5,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse response
        content_text = response.content[0].text

        # Extract JSON from the response
        if "```json" in content_text:
            json_start = content_text.find("```json") + 7
            json_end = content_text.find("```", json_start)
            content_text = content_text[json_start:json_end].strip()
        elif "```" in content_text:
            json_start = content_text.find("```") + 3
            json_end = content_text.find("```", json_start)
            content_text = content_text[json_start:json_end].strip()

        try:
            data = json.loads(content_text)
            related = data.get("related_concepts", [])

            # Filter to only include concepts that actually exist
            filtered_related = [c for c in related if c in existing_concepts]

            return filtered_related
        except json.JSONDecodeError:
            # If parsing fails, return empty list
            return []

    def classify_note(self, note_content: str, note_title: str) -> str:
        """
        Classify a note as either a 'concept' or a 'source'.

        Args:
            note_content: The text content of the note
            note_title: Title of the note

        Returns:
            Either "concept" or "source"
        """
        prompt = f"""You are an expert at analyzing notes in a Zettelkasten knowledge management system.

Your task: Determine if this note is a CONCEPT or a SOURCE.

Definitions:
- CONCEPT: A standalone idea, framework, principle, or mental model. These are atomic ideas that can be linked and built upon. Examples: "Growth Mindset", "Cognitive Dissonance", "The 4 Ps Framework"
- SOURCE: Notes about external content - summaries or highlights from articles, books, videos, podcasts, or other references. These document what you learned from a specific source.

Note Title: {note_title}

Note Content:
{note_content[:5000]}

Analyze this note and determine its type based on:
1. Does it reference an external source (article, book, video)?
2. Is it a summary or notes FROM something else?
3. Does it contain a URL or citation?
4. Or is it a standalone explanation of an idea/concept?

Return your classification as a JSON object:
{{
  "type": "concept",
  "reasoning": "Brief explanation of why"
}}

The type must be either "concept" or "source"."""

        response = self.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=512,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse response
        content_text = response.content[0].text

        # Extract JSON
        if "```json" in content_text:
            json_start = content_text.find("```json") + 7
            json_end = content_text.find("```", json_start)
            content_text = content_text[json_start:json_end].strip()
        elif "```" in content_text:
            json_start = content_text.find("```") + 3
            json_end = content_text.find("```", json_start)
            content_text = content_text[json_start:json_end].strip()

        try:
            data = json.loads(content_text)
            note_type = data.get("type", "concept")
            # Ensure valid type
            if note_type not in ["concept", "source"]:
                note_type = "concept"
            return note_type
        except json.JSONDecodeError:
            # Default to concept if parsing fails
            return "concept"
