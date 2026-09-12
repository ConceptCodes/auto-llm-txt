"""Compose — render llms.txt and llms-full.txt from sections + pages."""

from __future__ import annotations

from auto_llm_txt.state import SiteState
from auto_llm_txt.tools.renderer import render_llms_full_txt, render_llms_txt


async def compose(state: SiteState) -> dict:
    site_title: str = state.get("site_title") or "Untitled Site"
    site_description: str = state.get("site_description") or "Documentation for this site."
    sections = state.get("sections") or []
    pages = state.get("pages") or []
    if "curated_summaries" in state:
        curated_urls = {
            summary.get("url", "") if isinstance(summary, dict) else summary.url
            for summary in state.get("curated_summaries") or []
        }
        pages = [
            page
            for page in pages
            if (page.get("url", "") if isinstance(page, dict) else page.url) in curated_urls
        ]

    # Optional full-dump URL: conventionally <base>/llms-full.txt.
    full_txt_url = None
    base_url = state.get("base_url") or ""
    include_full = state.get("include_full", True)
    if include_full and pages and base_url:
        base = base_url.rstrip("/")
        full_txt_url = f"{base}/llms-full.txt"

    llms_txt = render_llms_txt(site_title, site_description, sections, full_txt_url=full_txt_url)
    llms_full_txt = (
        render_llms_full_txt(pages, site_title=site_title) if include_full and pages else ""
    )

    return {"llms_txt": llms_txt, "llms_full_txt": llms_full_txt, "active_node": "compose"}
