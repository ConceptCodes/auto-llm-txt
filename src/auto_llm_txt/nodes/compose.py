"""Compose — render llms.txt and llms-full.txt from sections + pages."""

from __future__ import annotations

from auto_llm_txt.state import SiteState
from auto_llm_txt.tools.renderer import render_llms_full_txt, render_llms_txt


async def compose(state: SiteState) -> dict:
    site_title: str = state.get("site_title") or "Untitled Site"
    site_description: str = state.get("site_description") or "Documentation for this site."
    sections = state.get("sections") or []
    pages = state.get("pages") or []

    # Optional full-dump URL: conventionally <base>/llms-full.txt — only include
    # if pages exist and include_full is enabled (default true).
    # For scaffold we always include the hint when pages exist.
    full_txt_url = None
    base_url = state.get("base_url") or ""
    if pages and base_url:
        base = base_url.rstrip("/")
        full_txt_url = f"{base}/llms-full.txt"

    llms_txt = render_llms_txt(site_title, site_description, sections, full_txt_url=full_txt_url)
    llms_full_txt = render_llms_full_txt(pages, site_title=site_title) if pages else ""

    return {"llms_txt": llms_txt, "llms_full_txt": llms_full_txt, "active_node": "compose"}
