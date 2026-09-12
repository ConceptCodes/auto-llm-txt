"""Extract — HTML → clean markdown + title.

Uses tools/extractor.py (trafilatura with BeautifulSoup fallback).
"""

from __future__ import annotations

from auto_llm_txt.state import Page, SiteState
from auto_llm_txt.tools.extractor import extract_markdown, extract_title


async def extract(state: SiteState) -> dict:
    raw_pages = state.get("raw_pages") or []
    base_url = state.get("base_url") or ""

    if not raw_pages:
        # No html fetched — check if we have legacy pages (for scaffold tests that inject pages directly)
        pages = state.get("pages") or []
        if pages:
            # Already have pages (e.g., tests injecting pages directly) — keep them
            return {"pages": pages, "active_node": "extract"}
        # Never manufacture content after a crawl failure. Downstream nodes can
        # produce a minimal diagnostic result without presenting invented pages.
        return {
            "pages": [],
            "warnings": [f"extract: no HTML was available for {base_url or 'the requested site'}"],
            "active_node": "extract",
        }

    pages: list[Page] = []
    warnings: list[str] = []
    for rp in raw_pages:
        # Support both RawPage model and plain dict (from checkpoint)
        if isinstance(rp, dict):
            url = rp.get("url", "")
            html = rp.get("html", "")
            depth = int(rp.get("depth", 0))
        else:
            url = getattr(rp, "url", "")
            html = getattr(rp, "html", "")
            depth = int(getattr(rp, "depth", 0))

        if not html or not html.strip():
            warnings.append(f"extract: empty html for {url}, skipping")
            continue

        try:
            title = extract_title(html)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"extract: title extraction failed for {url}: {e}")
            title = "Untitled"

        try:
            markdown = extract_markdown(html, url=url)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"extract: markdown extraction failed for {url}: {e}")
            markdown = ""

        if not markdown.strip():
            warnings.append(f"extract: empty markdown for {url} (title={title})")
            # Keep page anyway with empty markdown so it can still be listed, but warn

        pages.append(Page(url=url, title=title, markdown=markdown, depth=depth))

    if not pages:
        warnings.append("extract: no pages extracted, pipeline will produce empty llms.txt")

    result: dict = {"pages": pages, "active_node": "extract"}
    if warnings:
        result["warnings"] = warnings
    return result
