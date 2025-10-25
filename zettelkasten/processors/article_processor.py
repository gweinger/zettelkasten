"""Article/web page content processor."""

import requests
from bs4 import BeautifulSoup
from typing import Optional
from pathlib import Path
from datetime import datetime
import hashlib
from zettelkasten.core.models import ProcessedContent, ContentType
from zettelkasten.core.config import Config


class ArticleProcessor:
    """Process web articles - extract text content and metadata."""

    def __init__(self, config: Config):
        """Initialize with configuration."""
        self.config = config

    def process(self, url: str) -> ProcessedContent:
        """
        Fetch and extract content from a web article.

        Args:
            url: Article URL

        Returns:
            ProcessedContent with extracted text and metadata
        """
        # Fetch the page
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(response.content, "html.parser")

        # Extract title
        title = self._extract_title(soup)

        # Extract main content
        text_content = self._extract_content(soup)

        # Extract metadata
        metadata = {
            "title": title,
            "url": url,
            "author": self._extract_meta(soup, "author"),
            "description": self._extract_meta(soup, "description"),
            "published_date": self._extract_meta(soup, "article:published_time"),
            "site_name": self._extract_meta(soup, "og:site_name"),
        }

        return ProcessedContent(
            url=url,
            content_type=ContentType.ARTICLE,
            title=title,
            text_content=text_content,
            metadata=metadata,
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract article title from various sources."""
        # Try different title sources in order of preference
        title_sources = [
            soup.find("meta", property="og:title"),
            soup.find("meta", attrs={"name": "twitter:title"}),
            soup.find("h1"),
            soup.find("title"),
        ]

        for source in title_sources:
            if source:
                title = source.get("content") if source.get("content") else source.get_text()
                if title:
                    return title.strip()

        return "Untitled Article"

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main article content."""
        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()

        # Try to find article content
        content_elements = [
            soup.find("article"),
            soup.find("main"),
            soup.find("div", class_=lambda x: x and "content" in x.lower()),
            soup.find("div", class_=lambda x: x and "article" in x.lower()),
            soup.find("body"),
        ]

        for element in content_elements:
            if element:
                # Extract text from paragraphs and headings
                # Note: Don't include 'li' tags as they're nested in other elements
                # and would cause duplicate text extraction
                paragraphs = element.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"])
                text = "\n\n".join(p.get_text().strip() for p in paragraphs if p.get_text().strip())
                if text:
                    return text

        return soup.get_text(separator="\n\n", strip=True)

    def _extract_meta(self, soup: BeautifulSoup, property_name: str) -> Optional[str]:
        """Extract metadata from meta tags."""
        # Try property attribute
        meta = soup.find("meta", property=property_name)
        if meta and meta.get("content"):
            return meta.get("content")

        # Try name attribute
        meta = soup.find("meta", attrs={"name": property_name})
        if meta and meta.get("content"):
            return meta.get("content")

        return None

    def save_full_text(self, source_filename: str, content: 'ProcessedContent', force: bool = False) -> Path:
        """
        Save article full text to a file for future reference.

        Uses the source note filename (minus .md) with -article.txt suffix for consistency.
        Checks for duplicate content and prompts user if a duplicate is found.

        Args:
            source_filename: Base filename of the source note (without .md extension)
            content: ProcessedContent with article data
            force: If True, overwrite without prompting

        Returns:
            Path to the saved file

        Raises:
            FileExistsError: If duplicate content found and user declines overwrite
        """
        # Use source filename with -article.txt suffix
        filename = f"{source_filename}-article.txt"

        # Save to articles directory
        article_file = self.config.articles_path / filename

        # Build file content with metadata header
        new_content_lines = []
        new_content_lines.append("=" * 80)
        new_content_lines.append(f"TITLE: {content.title}")
        new_content_lines.append(f"URL: {content.url}")
        new_content_lines.append(f"SAVED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if content.metadata.get("author"):
            new_content_lines.append(f"AUTHOR: {content.metadata['author']}")
        if content.metadata.get("published_date"):
            new_content_lines.append(f"PUBLISHED: {content.metadata['published_date']}")
        if content.metadata.get("site_name"):
            new_content_lines.append(f"SITE: {content.metadata['site_name']}")
        new_content_lines.append("=" * 80)
        new_content_lines.append("")
        new_content_lines.append(content.text_content)

        new_content = "\n".join(new_content_lines)

        # Check for duplicates - look for same text content
        if article_file.exists() and not force:
            existing_content = article_file.read_text()

            # Compare the actual article text (after headers)
            # Extract text content from both
            existing_text = self._extract_text_from_saved(existing_content)

            # Simple duplicate check: if text content is identical or very similar
            if existing_text and self._content_matches(existing_text, content.text_content):
                # Content is a duplicate
                raise FileExistsError(
                    f"Duplicate content detected. Article with same text already exists at:\n"
                    f"  {article_file}\n"
                    f"Use --force to overwrite."
                )

        # Write to file
        article_file.write_text(new_content)

        return article_file

    def _extract_text_from_saved(self, saved_content: str) -> str:
        """
        Extract the actual text content from a saved article file.

        Args:
            saved_content: Full saved file content with headers

        Returns:
            Just the text portion (after headers)
        """
        # Find the end of the header (second row of ===)
        lines = saved_content.split("\n")
        header_end = 0

        for i, line in enumerate(lines):
            if line.startswith("=" * 20):  # Look for separator line
                header_end = i + 1
                break

        # Return everything after the header
        if header_end > 0:
            return "\n".join(lines[header_end:]).strip()

        return saved_content

    def _content_matches(self, existing_text: str, new_text: str, threshold: float = 0.95) -> bool:
        """
        Check if two texts are similar enough to be considered duplicates.

        Uses simple string similarity check.

        Args:
            existing_text: Previously saved text
            new_text: New text to compare
            threshold: Similarity threshold (0-1)

        Returns:
            True if texts are similar enough to be duplicates
        """
        # Normalize both texts
        existing_normalized = " ".join(existing_text.lower().split())
        new_normalized = " ".join(new_text.lower().split())

        # If they're identical
        if existing_normalized == new_normalized:
            return True

        # If very similar length and content (at least 95% match)
        if len(existing_normalized) > 100 and len(new_normalized) > 100:
            # Check if one is mostly contained in the other
            if existing_normalized in new_normalized or new_normalized in existing_normalized:
                return True

            # Simple character-level similarity
            matching_chars = sum(1 for a, b in zip(existing_normalized, new_normalized) if a == b)
            similarity = matching_chars / max(len(existing_normalized), len(new_normalized))

            if similarity >= threshold:
                return True

        return False
