"""Crawler — discovers URLs via sitemap.xml with BFS fallback.

Pure helpers here take raw XML/HTML strings so they are unit-testable without
network access. Async network code lives in nodes/discover.py which calls these.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def parse_sitemap(xml_text: str) -> list[str]:
    """Parse sitemap.xml / sitemap index text into a flat list of URLs."""
    urls: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    # Strip namespace if present: {http://www.sitemaps.org/schemas/sitemap/0.9}url
    def local(tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag

    for elem in root.iter():
        if local(elem.tag) == "loc" and elem.text:
            text = elem.text.strip()
            if text:
                urls.append(text)
    return urls


def is_sitemap_index(xml_text: str) -> bool:
    """Return True if xml_text is a <sitemapindex> rather than <urlset>."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return False

    def local(tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag

    return local(root.tag) == "sitemapindex"


def get_sitemap_candidates(base_url: str) -> list[str]:
    """Return ordered sitemap.xml candidates for a base URL."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    candidates: list[str] = []
    # 1) base_url's own sitemap.xml (e.g. https://example.com/docs/ → https://example.com/docs/sitemap.xml)
    base_clean = base_url.rstrip("/")
    candidates.append(f"{base_clean}/sitemap.xml")
    # 2) origin sitemap.xml (most common)
    candidates.append(f"{origin}/sitemap.xml")
    # 3) origin sitemap_index.xml variant
    candidates.append(f"{origin}/sitemap_index.xml")
    # 4) base without path? for deep bases also try origin + path prefix sitemap
    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def parse_robots_for_sitemaps(robots_text: str) -> list[str]:
    """Extract Sitemap: URLs from robots.txt."""
    sitemaps: list[str] = []
    for line in robots_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("sitemap:"):
            url = line.split(":", 1)[1].strip() if ":" in line else ""
            # Sitemap: directive may be "Sitemap: https://example.com/sitemap.xml"
            # split above is wrong because it splits on first colon -> "https"
            # So handle properly: split on first whitespace after colon
            # Better: find colon then take remainder
            m = re.match(r"(?i)sitemap:\s*(\S+)", line)
            if m:
                sitemaps.append(m.group(1).strip())
    return sitemaps


def extract_links(html: str, base_url: str) -> list[str]:
    """Extract href links from HTML, resolved against base_url."""
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        # Skip non-http schemes early
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        # Also skip pure fragment
        if href.startswith("#"):
            continue
        # Resolve relative URLs
        joined = urljoin(base_url, href)
        parsed = urlparse(joined)
        if parsed.scheme not in ("http", "https"):
            continue
        # Drop fragment, keep query
        canonical = parsed._replace(fragment="").geturl()
        links.append(canonical)
    return links


def is_same_prefix(url: str, base_url: str) -> bool:
    """True if url's path starts with base_url's path and same host."""
    base = urlparse(base_url)
    cand = urlparse(url)
    if cand.netloc and cand.netloc != base.netloc:
        return False
    # Same-path-prefix: /docs/ allows /docs, /docs/, /docs/a but not /doc or /other
    base_path = base.path or "/"
    cand_path = cand.path or "/"
    if base_path == "/" or base_path == "":
        return True
    base_norm = base_path.rstrip("/") or "/"
    cand_norm = cand_path.rstrip("/") or "/"
    if cand_norm == base_norm:
        return True
    # Candidate is under base prefix if it starts with base_norm + "/"
    return cand_path.startswith(base_norm + "/") or cand_norm.startswith(base_norm + "/")


def normalize_url(url: str, base_url: str) -> str | None:
    """Canonicalize url relative to base_url; return None if not http(s) or filtered."""
    joined = urljoin(base_url, url.strip())
    parsed = urlparse(joined)
    if parsed.scheme not in ("http", "https"):
        return None
    # Drop fragment, keep query
    canonical = parsed._replace(fragment="").geturl()
    # Normalise trailing slash for root only is fine
    return canonical


def filter_and_dedupe(urls: list[str], base_url: str) -> list[str]:
    """Filter to same-path-prefix, dedupe preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in urls:
        norm = normalize_url(raw, base_url)
        if norm is None:
            continue
        if not is_same_prefix(norm, base_url):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out
