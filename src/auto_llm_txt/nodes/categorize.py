"""Categorize — LLM groups pages into H2 sections + writes site summary.

Falls back to single-section heuristic when LLM unavailable or fails.
"""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from auto_llm_txt.config import settings
from auto_llm_txt.prompts import CATEGORIZE
from auto_llm_txt.state import (
    CategorizeOutput,
    FetchError,
    PageSummary,
    Section,
    SiteState,
)

# ---------------------------------------------------------------------------
# Heuristic fallback: group by URL path prefix
# ---------------------------------------------------------------------------


def _heuristic_sections(pages: list[PageSummary], base_url: str) -> tuple[list[Section], str, str]:
    """Group pages by URL path prefix for fallback."""
    # Site title from base_url host
    site_title = ""
    if base_url:
        try:
            parsed = urlparse(base_url)
            site_title = parsed.netloc or base_url
        except Exception:  # noqa: BLE001
            site_title = base_url
    site_title = site_title or "Untitled Site"
    site_description = f"Documentation for {site_title} — {len(pages)} pages indexed."

    if not pages:
        return [], site_title, site_description

    if len(pages) <= 5:
        # Small site → single section is fine
        return [Section(name="Documentation", description="", pages=list(pages))], site_title, site_description

    # Group by first path segment after stripping base prefix
    try:
        base_parsed = urlparse(base_url)
        base_path = base_parsed.path.rstrip("/") or ""
    except Exception:  # noqa: BLE001
        base_path = ""

    groups: dict[str, list[PageSummary]] = defaultdict(list)
    for p in pages:
        try:
            path = urlparse(p.url).path
            # Remove base prefix
            if base_path and path.startswith(base_path):
                path = path[len(base_path) :] or "/"
            # Split into segments
            segments = [s for s in path.split("/") if s]
            if not segments:
                key = "General"
            elif len(segments) == 1:
                # Single file like /intro → group by its name? use "General" or file name
                # Use first segment capitalized as group? But many distinct files would create many groups,
                # so we bucket them into "Documentation" and rely on LLM for smarter grouping.
                # For heuristic fallback, just use first segment or "Documentation"
                key = segments[0].replace("-", " ").replace("_", " ").title()
                # If key is like "Intro" for single page, that would create per-page sections which is too many.
                # Instead treat single-segment pages as "Documentation" unless there are multiple with same prefix?
                # Simplify: if group would have only 1 page, later we merge small groups
            else:
                # Use first segment as group, e.g., api, guides, docs
                key = segments[0].replace("-", " ").replace("_", " ").title()
        except Exception:  # noqa: BLE001
            key = "Documentation"
        groups[key].append(p)

    # Merge tiny groups (<2 pages) into "Other" or "Documentation"
    merged: dict[str, list[PageSummary]] = {}
    other: list[PageSummary] = []
    for name, grp in groups.items():
        if len(grp) < 2:
            other.extend(grp)
        else:
            merged[name] = grp
    if other:
        # If we already have a Documentation group, add there; else create "Other"
        if "Documentation" in merged:
            merged["Documentation"].extend(other)
        elif len(merged) == 0:
            merged["Documentation"] = other
        else:
            merged["Other"] = other

    # If still only one group, return single Documentation
    if len(merged) == 1 and "Documentation" in merged:
        return [Section(name="Documentation", description="", pages=merged["Documentation"])], site_title, site_description

    # Prefer sorted order for determinism
    sections: list[Section] = []
    for name in sorted(merged.keys()):
        pages_in_group = sorted(merged[name], key=lambda p: p.url)
        sections.append(Section(name=name, description="", pages=pages_in_group))

    # Cap to 8 sections
    if len(sections) > 8:
        # Merge smallest extra sections into "Other"
        sections = sorted(sections, key=lambda s: len(s.pages), reverse=True)
        keep = sections[:7]
        rest_pages: list[PageSummary] = []
        for s in sections[7:]:
            rest_pages.extend(s.pages)
        keep.append(Section(name="Other", description="", pages=sorted(rest_pages, key=lambda p: p.url)))
        sections = keep

    return sections, site_title, site_description


def _normalize_pages(pages: list) -> list[PageSummary]:
    """Normalize dicts or PageSummary objects to list[PageSummary]."""
    out: list[PageSummary] = []
    for p in pages:
        if isinstance(p, dict):
            from auto_llm_txt.constants import PageQuality

            q = p.get("quality", PageQuality.medium)
            if isinstance(q, str):
                try:
                    q = PageQuality(q)
                except ValueError:
                    q = PageQuality.medium
            out.append(PageSummary(url=p.get("url", ""), title=p.get("title", ""), description=p.get("description", ""), quality=q))
        else:
            out.append(p)
    return out


async def categorize(state: SiteState, config: RunnableConfig = None) -> dict:
    curated_raw = state.get("curated_summaries") or state.get("summaries") or []
    base_url = state.get("base_url") or ""

    # Derive site title override from settings if set
    settings_title = (settings.site_title or "").strip()
    state_title = (state.get("site_title") or "").strip()
    # We'll let LLM override, but keep settings/state as fallback
    fallback_title = settings_title or state_title

    curated = _normalize_pages(curated_raw)  # type: ignore[arg-type]

    if not curated:
        site_title = fallback_title or (urlparse(base_url).netloc if base_url else "Untitled Site")
        site_title = site_title or "Untitled Site"
        site_desc = state.get("site_description") or "Documentation for this site."
        return {
            "sections": [],
            "site_title": site_title,
            "site_description": site_desc,
            "active_node": "categorize",
        }

    # If no LLM key, heuristic
    if not settings.openrouter_api_key:
        sections, heur_title, heur_desc = _heuristic_sections(curated, base_url)
        # Respect explicit title if provided
        site_title = fallback_title or heur_title
        # If state already has site_description, keep it else heuristic
        site_description = state.get("site_description") or heur_desc
        return {
            "sections": sections,
            "site_title": site_title,
            "site_description": site_description,
            "active_node": "categorize",
        }

    # LLM path
    try:
        from auto_llm_txt.utils import get_structured_llm

        llm = get_structured_llm(CategorizeOutput)

        lines: list[str] = []
        for p in curated:
            lines.append(f"- [{p.title}]({p.url}): {p.description}")

        page_list = "\n".join(lines)
        if len(page_list) > 15000:
            page_list = page_list[:15000] + "\n\n[... truncated]"

        base_hint = f"Base URL: {base_url}\n" if base_url else ""
        existing_title_hint = f"Current site title (host-derived): {fallback_title}\n" if fallback_title else ""

        messages = [
            SystemMessage(content=CATEGORIZE),
            HumanMessage(
                content=(
                    f"{base_hint}{existing_title_hint}"
                    f"Pages ({len(curated)} total):\n{page_list}\n\n"
                    "Organize them into sections. Each page must appear exactly once. "
                    "Prefer URL path clues for grouping."
                )
            ),
        ]

        if config is not None:
            output: CategorizeOutput = await llm.ainvoke(messages, config=config)  # type: ignore[assignment]
        else:
            output: CategorizeOutput = await llm.ainvoke(messages)  # type: ignore[assignment]

        # Validate and map
        input_urls = {p.url for p in curated}
        url_to_summary = {p.url: p for p in curated}
        seen: set[str] = set()
        sections: list[Section] = []
        warnings: list[str] = []

        for sec_out in output.sections:
            # Normalize name
            name = (sec_out.name or "").strip() or "Documentation"
            desc = (sec_out.description or "").strip()
            # Filter page_urls to valid, deduped, preserve order
            valid_urls: list[str] = []
            for u in sec_out.page_urls:
                u = u.strip()
                if not u:
                    continue
                if u not in input_urls:
                    # Try to match by normalized URL (strip trailing slash)
                    # e.g., LLM may omit https or trailing slash
                    # Do fuzzy match: find first input url that ends with same path
                    matched = None
                    for cand in input_urls:
                        if (
                            cand.rstrip("/") == u.rstrip("/") or cand.endswith(u) or u.endswith(cand)
                        ) and (cand not in seen and cand not in valid_urls):
                            matched = cand
                            break
                    if matched:
                        valid_urls.append(matched)
                    else:
                        warnings.append(f"categorize: LLM section '{name}' references unknown URL {u}, dropped")
                elif u in seen:
                    warnings.append(f"categorize: duplicate URL {u} in section '{name}', deduped")
                else:
                    valid_urls.append(u)

            # Also dedupe within section
            deduped: list[str] = []
            for u in valid_urls:
                if u not in deduped:
                    deduped.append(u)

            if not deduped:
                warnings.append(f"categorize: section '{name}' has no valid pages, skipped")
                continue

            for u in deduped:
                seen.add(u)

            pages_in_sec = [url_to_summary[u] for u in deduped if u in url_to_summary]
            sections.append(Section(name=name, description=desc, pages=pages_in_sec))

        # Handle missing URLs (not assigned to any section)
        missing = input_urls - seen
        if missing:
            warnings.append(f"categorize: {len(missing)} pages not assigned by LLM, putting in 'Other'")
            other_pages = [url_to_summary[u.url] for u in curated if u.url in missing]
            # Try to find existing Other section or create
            other_sec = next((s for s in sections if s.name.lower() == "other"), None)
            if other_sec:
                other_sec.pages.extend(other_pages)
            else:
                sections.append(Section(name="Other", description="", pages=sorted(other_pages, key=lambda p: p.url)))

        # If LLM gave no sections or all invalid, fallback
        if not sections:
            warnings.append("categorize: LLM returned no valid sections, using heuristic")
            sections, heur_title, heur_desc = _heuristic_sections(curated, base_url)
            site_title = (output.site_title or "").strip() or fallback_title or heur_title
            site_description = (output.site_description or "").strip() or heur_desc
            return {
                "sections": sections,
                "site_title": site_title or heur_title,
                "site_description": site_description or heur_desc,
                "warnings": warnings,
                "active_node": "categorize",
            }

        # Cap sections to 8
        if len(sections) > 8:
            warnings.append(f"categorize: LLM returned {len(sections)} sections, capping to 8")
            # Keep largest 7 + other
            sections = sorted(sections, key=lambda s: len(s.pages), reverse=True)
            keep = sections[:7]
            rest_pages: list[PageSummary] = []
            for s in sections[7:]:
                rest_pages.extend(s.pages)
            keep.append(Section(name="Other", description="", pages=rest_pages))
            sections = keep

        site_title = (output.site_title or "").strip() or fallback_title or (urlparse(base_url).netloc if base_url else "Untitled Site")
        site_description = (output.site_description or "").strip() or f"Documentation for {site_title} — {len(curated)} pages indexed."

        result: dict = {
            "sections": sections,
            "site_title": site_title,
            "site_description": site_description,
            "active_node": "categorize",
        }
        if warnings:
            result["warnings"] = warnings
        return result

    except Exception as e:  # noqa: BLE001
        sections, heur_title, heur_desc = _heuristic_sections(curated, base_url)
        site_title = fallback_title or heur_title
        site_description = state.get("site_description") or heur_desc
        warnings = [f"categorize: LLM failed ({e}), used heuristic"]
        return {
            "sections": sections,
            "site_title": site_title,
            "site_description": site_description,
            "warnings": warnings,
            "errors": [FetchError(url=base_url, stage="categorize", detail=str(e))],
            "active_node": "categorize",
        }
