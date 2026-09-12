"""Discover — resolve the crawl frontier.

Strategy (sitemap-first, BFS fallback):
1. Try <base_url>/sitemap.xml and sitemap index (recursive, capped).
2. If that yields >= 2 URLs, use it (filtered to same-path-prefix).
3. Otherwise BFS from base_url following same-prefix links up to max_pages/max_depth.

Network I/O is async; helpers in tools/crawler.py stay pure/sync for testability.
"""

from __future__ import annotations

import asyncio
from collections import deque
from urllib.parse import urlparse

from auto_llm_txt.config import settings
from auto_llm_txt.state import FetchError, RawPage, SiteState
from auto_llm_txt.tools.crawler import (
    extract_links,
    filter_and_dedupe,
    get_sitemap_candidates,
    is_same_prefix,
    is_sitemap_index,
    parse_robots_for_sitemaps,
    parse_sitemap,
)
from auto_llm_txt.tools.fetcher import build_client, fetch_text


async def discover(state: SiteState) -> dict:
    """Populate state['urls'] with the crawl frontier."""
    # Test injection bypass — if caller already supplied a frontier, respect it
    if state.get("urls") is not None:
        urls = state.get("urls") or []
        if isinstance(urls, list) and len(urls) > 0:
            # Respect pre-populated frontier (used by tests to avoid network)
            raw_pages = state.get("raw_pages") or []
            pages = state.get("pages") or []
            # If tests injected pages but no raw_pages, keep pages for extract fallback
            result: dict = {"urls": urls, "active_node": "discover"}
            if raw_pages:
                result["raw_pages"] = raw_pages
            if pages and not raw_pages:
                # Keep pages so extract can use fallback
                result["pages"] = pages
            return result

    base_url: str = state.get("base_url") or ""
    if not base_url:
        return {"warnings": ["discover: base_url is empty"], "urls": []}

    max_pages: int = int(state.get("max_pages") or settings.max_pages)
    max_depth: int = int(state.get("max_depth") or settings.max_depth)
    timeout: int = int(settings.request_timeout)
    crawl_delay: float = float(settings.crawl_delay)

    # Try sitemap first
    try:
        sitemap_urls = await _discover_via_sitemap(base_url, max_pages, timeout, crawl_delay)
    except Exception as e:  # noqa: BLE001
        sitemap_urls = []
        # Return as warning rather than failing
        return await _bfs_fallback(base_url, max_pages, max_depth, timeout, crawl_delay, sitemap_error=str(e))

    if sitemap_urls:
        filtered = filter_and_dedupe(sitemap_urls, base_url)
        # If sitemap gave usable urls, use it (even if single page, still valid)
        # But require at least 1 and not just the seed alone when BFS would be better?
        # Policy: if sitemap returns >=1 urls, prefer it; BFS is fallback only when sitemap empty/failed.
        if filtered:
            capped = filtered[:max_pages]
            # Ensure base_url is included if it's within scope and not already present
            # This helps when sitemap omits the index page
            if base_url not in capped and is_same_prefix(base_url, base_url):
                # Only add if we have room and base is not already covered
                # Check normalized versions
                from auto_llm_txt.tools.crawler import normalize_url

                norm_base = normalize_url(base_url, base_url)
                if norm_base and norm_base not in capped and len(capped) < max_pages:
                    capped = [norm_base] + capped
            return {"urls": capped, "raw_pages": [], "active_node": "discover"}

    # Sitemap empty or gave no usable urls → BFS fallback
    return await _bfs_fallback(base_url, max_pages, max_depth, timeout, crawl_delay)


async def _discover_via_sitemap(base_url: str, max_pages: int, timeout: int, crawl_delay: float) -> list[str]:
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    candidates: list[str] = []

    all_urls: list[str] = []
    async with build_client(timeout=timeout) as client:
        # 0) Try robots.txt for explicit sitemap locations (highest priority)
        try:
            robots_text, _ = await fetch_text(client, f"{origin}/robots.txt")
            if robots_text:
                robot_sitemaps = parse_robots_for_sitemaps(robots_text)
                # Filter to same host or allow cross-host sitemaps? Keep only http(s)
                for sm in robot_sitemaps:
                    if sm.startswith("http"):
                        candidates.append(sm)
                await asyncio.sleep(crawl_delay)
        except Exception:
            pass

        # 1) Normal candidates
        candidates.extend(get_sitemap_candidates(base_url))

        # Dedupe candidates preserving order
        seen: set[str] = set()
        uniq_candidates: list[str] = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                uniq_candidates.append(c)

        for candidate in uniq_candidates:
            text, err = await fetch_text(client, candidate)
            await asyncio.sleep(crawl_delay)
            if err or not text:
                continue
            # Check if it's a sitemap index
            if is_sitemap_index(text):
                sub_sitemaps = parse_sitemap(text)
                # Limit sub-sitemaps to avoid explosion
                sub_sitemaps = sub_sitemaps[:10]
                for sub in sub_sitemaps:
                    if not sub.startswith("http"):
                        continue
                    sub_text, sub_err = await fetch_text(client, sub)
                    await asyncio.sleep(crawl_delay)
                    if sub_err or not sub_text:
                        continue
                    if is_sitemap_index(sub_text):
                        # Nested index — skip for v1 (avoid recursion depth)
                        continue
                    sub_urls = parse_sitemap(sub_text)
                    all_urls.extend(sub_urls)
                    if len(all_urls) >= max_pages:
                        break
                if all_urls:
                    return all_urls[: max_pages * 2]  # return generous, filtering happens later
            else:
                urls = parse_sitemap(text)
                if urls:
                    return urls[: max_pages * 2]
    return []


async def _bfs_fallback(
    base_url: str,
    max_pages: int,
    max_depth: int,
    timeout: int,
    crawl_delay: float,
    sitemap_error: str | None = None,
) -> dict:
    warnings: list[str] = []
    errors: list[FetchError] = []
    if sitemap_error:
        warnings.append(f"discover: sitemap error — {sitemap_error}, falling back to BFS")

    queue: deque[tuple[str, int]] = deque([(base_url, 0)])
    visited: set[str] = {base_url}
    urls: list[str] = [base_url]
    raw_pages: list[RawPage] = []

    client = build_client(timeout=timeout)
    async with client:
        while queue and len(urls) < max_pages:
            current_url, depth = queue.popleft()
            if depth > max_depth:
                continue

            html, err = await fetch_text(client, current_url)
            await asyncio.sleep(crawl_delay)

            if err or html is None:
                errors.append(FetchError(url=current_url, stage="discover", detail=err or "empty response"))
                # Keep the URL in frontier (so fetch node can retry), but don't expand links
                continue

            # Store HTML for reuse in fetch node (avoid double fetch)
            # Only store if not already stored
            if not any(rp.url == current_url for rp in raw_pages):
                raw_pages.append(RawPage(url=current_url, html=html, depth=depth))

            if depth >= max_depth:
                continue

            try:
                links = extract_links(html, current_url)
            except Exception as e:  # noqa: BLE001
                warnings.append(f"discover: failed to extract links from {current_url}: {e}")
                continue

            filtered = filter_and_dedupe(links, base_url)
            for link in filtered:
                if link in visited:
                    continue
                if len(urls) >= max_pages:
                    break
                visited.add(link)
                urls.append(link)
                queue.append((link, depth + 1))

            if len(urls) >= max_pages:
                warnings.append(f"discover: hit max_pages ({max_pages}) during BFS, truncated")
                break

    if not urls:
        warnings.append("discover: BFS found no urls")

    return {
        "urls": urls[:max_pages],
        "raw_pages": raw_pages,
        "warnings": warnings,
        "errors": errors,
        "active_node": "discover",
    }
