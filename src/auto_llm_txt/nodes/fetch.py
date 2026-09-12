"""Fetch — download HTML for each URL in the frontier.

Bounded concurrency, respects request_timeout + crawl_delay.
Reuses html already fetched during discover BFS (raw_pages cache) to avoid double fetch.
"""

from __future__ import annotations

import asyncio

from auto_llm_txt.config import settings
from auto_llm_txt.state import FetchError, RawPage, SiteState
from auto_llm_txt.tools.fetcher import build_client, fetch_text


async def fetch(state: SiteState) -> dict:
    urls: list[str] = state.get("urls") or []
    if not urls:
        return {"warnings": ["fetch: no urls to fetch"], "active_node": "fetch"}

    # Test injection bypass: if pages already supplied (scaffold tests), keep them
    if state.get("pages"):
        pages = state.get("pages") or []
        if isinstance(pages, list) and len(pages) > 0 and not state.get("raw_pages"):
            # No raw_pages to fetch; downstream extract will use injected pages
            return {"raw_pages": [], "active_node": "fetch"}

    # Existing cache from discover BFS
    existing_raw: list[RawPage] = list(state.get("raw_pages") or [])
    # Handle both RawPage objects and plain dicts (from checkpoint deserialization)
    def _get_url(rp) -> str:
        if isinstance(rp, dict):
            return rp.get("url", "")
        return getattr(rp, "url", "")

    cached_urls: set[str] = {_get_url(rp) for rp in existing_raw}

    to_fetch: list[str] = [u for u in urls if u not in cached_urls]
    if not to_fetch:
        # Everything already cached — nothing to do
        return {"raw_pages": existing_raw, "active_node": "fetch"}

    timeout: int = int(settings.request_timeout)
    concurrency: int = int(settings.concurrency)
    crawl_delay: float = float(settings.crawl_delay)

    sem = asyncio.Semaphore(concurrency)
    errors: list[FetchError] = []
    fetched: list[RawPage] = []

    client = build_client(timeout=timeout)

    async def fetch_one(url: str) -> None:
        async with sem:
            try:
                html, err = await fetch_text(client, url)
                if crawl_delay:
                    await asyncio.sleep(crawl_delay)
                if err or html is None:
                    errors.append(FetchError(url=url, stage="fetch", detail=err or "empty response"))
                    return
                # Depth is not known here separately; use 0 as placeholder.
                # Discover's BFS already set depths for those urls; for sitemap case depth is 0.
                fetched.append(RawPage(url=url, html=html, depth=0))
            except Exception as e:  # noqa: BLE001
                errors.append(FetchError(url=url, stage="fetch", detail=str(e)))

    async with client:
        await asyncio.gather(*(fetch_one(u) for u in to_fetch))

    # Merge existing + newly fetched, preserving order of urls
    # Build lookup for new fetches
    new_by_url: dict[str, RawPage] = {(_get_url(rp) if isinstance(rp, dict) else rp.url): rp for rp in fetched}
    merged: list[RawPage] = []
    for url in urls:
        if url in cached_urls:
            # Find existing
            for rp in existing_raw:
                if _get_url(rp) == url:
                    merged.append(rp)
                    break
        elif url in new_by_url:
            merged.append(new_by_url[url])
        else:
            # Fetch failed — no html, will be missing from raw_pages; extract will skip
            pass

    # Also include any existing_raw that may not be in urls? Should not happen, but keep
    # (e.g., discover fetched extra pages beyond frontier? Not needed)

    warnings: list[str] = []
    if len(merged) < len(urls):
        warnings.append(f"fetch: {len(urls) - len(merged)} urls failed to fetch and will be skipped")

    # Combine cached urls that were successful with new ones: merged already is ordered
    # But we lost fetched pages that are not in urls order? merged is already ordered.
    # Ensure we return merged as raw_pages. If some urls failed, merged shorter.

    result: dict = {"raw_pages": merged, "active_node": "fetch"}
    if errors:
        result["errors"] = errors
    if warnings:
        result["warnings"] = warnings
    return result
