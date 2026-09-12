"""Extractor — HTML to clean markdown + title."""

from __future__ import annotations

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
    if HAS_TRAFILATURA:
        # trafilatura returns markdown-ish text; include formatting
        md = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            include_formatting=True,
            output_format="markdown",
            url=url or None,
        )
        if md and md.strip():
            return _clean_markdown(md)

    # Fallback: very simple heading/paragraph extraction
    soup = BeautifulSoup(html, "lxml")
    # Remove script/style/nav/footer
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

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


def _clean_markdown(md: str) -> str:
    # Collapse excessive blank lines
    md = re.sub(r"\n{3,}", "\n\n", md)
    # Collapse excessive spaces
    md = re.sub(r"[ \t]{2,}", " ", md)
    return md.strip()
