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
                # Extract text from paragraphs
                paragraphs = element.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"])
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

    def save_full_text(self, source_filename: str, content: 'ProcessedContent') -> Path:
        """
        Save article full text to a file for future reference.

        Uses the source note filename (minus .md) with -article.txt suffix for consistency.

        Args:
            source_filename: Base filename of the source note (without .md extension)
            content: ProcessedContent with article data

        Returns:
            Path to the saved file
        """
        # Use source filename with -article.txt suffix
        filename = f"{source_filename}-article.txt"

        # Save to articles directory
        article_file = self.config.articles_path / filename

        # Build file content with metadata header
        lines = []
        lines.append("=" * 80)
        lines.append(f"TITLE: {content.title}")
        lines.append(f"URL: {content.url}")
        lines.append(f"SAVED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if content.metadata.get("author"):
            lines.append(f"AUTHOR: {content.metadata['author']}")
        if content.metadata.get("published_date"):
            lines.append(f"PUBLISHED: {content.metadata['published_date']}")
        if content.metadata.get("site_name"):
            lines.append(f"SITE: {content.metadata['site_name']}")
        lines.append("=" * 80)
        lines.append("")
        lines.append(content.text_content)

        # Write to file
        article_file.write_text("\n".join(lines))

        return article_file
