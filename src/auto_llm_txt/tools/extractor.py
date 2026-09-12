"""Extractor — HTML to clean markdown + title."""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

try:
    import trafilatura

    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False


def extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        if t:
            return t
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    return "Untitled"


def extract_markdown(html: str, url: str = "") -> str:
    """Convert HTML to markdown.

    Tries trafilatura first (best for article/docs), falls back to a simple
    BeautifulSoup text extraction so tests never depend on network/magic.
    """
    content_html = _prune_page_chrome(html)

    if HAS_TRAFILATURA:
        # trafilatura returns markdown-ish text; include formatting
        md = trafilatura.extract(
            content_html,
            include_comments=False,
            include_tables=True,
            include_formatting=True,
            output_format="markdown",
            deduplicate=True,
            url=url or None,
        )
        if md and md.strip():
            cleaned = _clean_markdown(md)
            if cleaned:
                return cleaned

        embedded_html = _extract_embedded_html(html)
        if embedded_html:
            md = trafilatura.extract(
                embedded_html,
                include_comments=False,
                include_tables=True,
                include_formatting=True,
                output_format="markdown",
                deduplicate=True,
                url=url or None,
            )
            if md and md.strip():
                cleaned = _clean_markdown(md)
                if cleaned:
                    return cleaned
            content_html = embedded_html

    # Fallback: very simple heading/paragraph extraction
    soup = BeautifulSoup(content_html, "lxml")

    lines: list[str] = []
    for elem in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "code"]):
        text = elem.get_text(" ", strip=True)
        if not text:
            continue
        if elem.name == "h1":
            lines.append(f"# {text}")
        elif elem.name == "h2":
            lines.append(f"## {text}")
        elif elem.name == "h3":
            lines.append(f"### {text}")
        elif elem.name == "li":
            lines.append(f"- {text}")
        elif elem.name in ("pre", "code"):
            lines.append(f"```\n{text}\n```")
        else:
            lines.append(text)

    if not lines:
        # Last resort: body text
        body = soup.get_text(" ", strip=True)
        if body:
            lines.append(body)

    return _clean_markdown("\n\n".join(lines))


def _prune_page_chrome(html: str) -> str:
    """Remove semantic site chrome before article extraction."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
        tag.decompose()
    for tag in soup.find_all(attrs={"role": ["navigation", "banner", "contentinfo"]}):
        tag.decompose()
    return str(soup)


def _extract_embedded_html(html: str) -> str:
    """Recover HTML fragments from JSON.parse hydration payloads."""
    soup = BeautifulSoup(html, "lxml")
    argument_pattern = re.compile(r'JSON\.parse\(("(?:\\.|[^"\\])*")\)')
    fragments: list[str] = []
    seen_fragments: set[str] = set()
    total_chars = 0

    for script in soup.find_all("script"):
        source = script.string or script.get_text()
        if "JSON.parse(" not in source:
            continue
        for match in argument_pattern.finditer(source):
            try:
                decoded = json.loads(match.group(1))
                payload = json.loads(decoded)
            except (json.JSONDecodeError, TypeError):
                continue

            stack = [payload]
            visited = 0
            while stack and visited < 50_000 and total_chars < 2_000_000:
                value = stack.pop()
                visited += 1
                if isinstance(value, dict):
                    nested: list[dict | list] = []
                    for key, child in value.items():
                        if key == "html" and isinstance(child, str) and "<" in child:
                            fragment = child[: 2_000_000 - total_chars]
                            if fragment not in seen_fragments:
                                seen_fragments.add(fragment)
                                fragments.append(fragment)
                                total_chars += len(fragment)
                        elif isinstance(child, (dict, list)):
                            nested.append(child)
                    stack.extend(reversed(nested))
                elif isinstance(value, list):
                    nested = [child for child in value if isinstance(child, (dict, list))]
                    stack.extend(reversed(nested))

    return "\n".join(fragments)


def _clean_markdown(md: str) -> str:
    # Collapse excessive blank lines
    md = re.sub(r"\n{3,}", "\n\n", md)
    # Collapse excessive spaces
    md = re.sub(r"[ \t]{2,}", " ", md)
    # Remove immediately repeated non-empty lines, including duplicates separated
    # by blank lines, which are common in responsive navigation and live feeds.
    cleaned: list[str] = []
    previous_content = ""
    seen_short_lines: set[str] = set()
    chrome_labels = {"skip to content", "skip gallery", "end of gallery"}
    for line in md.splitlines():
        content = line.strip()
        if content.casefold() in chrome_labels:
            continue
        if content and content == previous_content:
            continue
        if (
            content
            and len(content) <= 80
            and not content.startswith(("#", "-", "```"))
            and content in seen_short_lines
        ):
            continue
        cleaned.append(line.rstrip())
        if content:
            previous_content = content
            seen_short_lines.add(content)
    return "\n".join(cleaned).strip()
