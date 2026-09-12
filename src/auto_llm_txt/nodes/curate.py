"""Curate — LLM prunes low-value pages.

When LLM is unavailable, falls back to quality-based heuristic (drop low).
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from auto_llm_txt.config import settings
from auto_llm_txt.constants import PageQuality
from auto_llm_txt.prompts import CURATE
from auto_llm_txt.state import CurateOutput, FetchError, PageSummary, SiteState


def _heuristic_curate(summaries: list[PageSummary]) -> tuple[list[PageSummary], list[str]]:
    """Fallback: keep medium/high, drop low. Returns (kept, warnings)."""
    kept: list[PageSummary] = []
    warnings: list[str] = []
    for s in summaries:
        # Support both PageSummary objects and dicts (from checkpoint)
        if isinstance(s, dict):
            quality = s.get("quality", PageQuality.medium)
            url = s.get("url", "")
            title = s.get("title", "")
            desc = s.get("description", "")
            # Normalize quality string
            if isinstance(quality, str):
                try:
                    quality = PageQuality(quality)
                except ValueError:
                    quality = PageQuality.medium
            obj = PageSummary(url=url, title=title, description=desc, quality=quality)
        else:
            obj = s
            quality = s.quality

        # Drop low quality; also drop obvious noise even if quality medium but title indicates noise
        lower_title = obj.title.lower()
        lower_desc = obj.description.lower()
        is_noise = any(
            kw in lower_title or kw in lower_desc
            for kw in ["404", "not found", "privacy policy", "terms of service", "cookie policy"]
        )
        if quality == PageQuality.low or is_noise:
            warnings.append(f"curate: dropped {obj.url} (heuristic, quality={quality})")
            continue
        kept.append(obj)

    # Be conservative: if heuristic would drop everything, keep all
    if not kept and summaries:
        warnings.append("curate: heuristic would drop all pages, keeping all instead")
        # Reconstruct kept as all summaries (normalized)
        kept = []
        for s in summaries:
            if isinstance(s, dict):
                kept.append(PageSummary(url=s.get("url",""), title=s.get("title",""), description=s.get("description",""), quality=PageQuality.medium))
            else:
                kept.append(s)
        warnings = [w for w in warnings if "dropped" not in w]

    return kept, warnings


async def curate(state: SiteState) -> dict:
    summaries: list[PageSummary] = state.get("summaries") or state.get("curated_summaries") or []  # type: ignore[assignment]
    if not summaries:
        return {"curated_summaries": [], "active_node": "curate"}

    # Normalize dicts to PageSummary for consistency (checkpoint deserialization may give dicts)
    normalized: list[PageSummary] = []
    for s in summaries:
        if isinstance(s, dict):
            # quality may be string
            q = s.get("quality", PageQuality.medium)
            if isinstance(q, str):
                try:
                    q = PageQuality(q)
                except ValueError:
                    q = PageQuality.medium
            normalized.append(PageSummary(url=s.get("url",""), title=s.get("title",""), description=s.get("description",""), quality=q))
        else:
            normalized.append(s)
    summaries = normalized

    # Fast path: no LLM key → heuristic
    if not settings.openrouter_api_key:
        kept, warnings = _heuristic_curate(summaries)
        result: dict = {"curated_summaries": kept, "active_node": "curate"}
        if warnings:
            result["warnings"] = warnings
        return result

    # LLM path
    try:
        from auto_llm_txt.nodes.utils import get_structured_llm

        llm = get_structured_llm(CurateOutput)

        # Build human message with page list
        lines: list[str] = []
        for i, s in enumerate(summaries, start=1):
            lines.append(f"{i}. [{s.title}]({s.url}): {s.description} (quality={s.quality})")

        page_list = "\n".join(lines)
        # Truncate if too long (100 pages * ~100 chars = 10k chars, still okay but cap)
        if len(page_list) > 12000:
            page_list = page_list[:12000] + "\n\n[... truncated]"

        messages = [
            SystemMessage(content=CURATE),
            HumanMessage(
                content=f"Pages to curate ({len(summaries)} total):\n{page_list}\n\nReturn keep_urls in original order. Keep the base/index page if present."
            ),
        ]

        output: CurateOutput = await llm.ainvoke(messages)  # type: ignore[assignment]

        # Validate keep_urls against input set
        input_urls = {s.url for s in summaries}
        # Preserve original order for kept, based on summaries order
        keep_set = set(output.keep_urls)
        # Filter to only URLs that were in input (ignore hallucinations)
        valid_keep_set = keep_set & input_urls

        # If LLM filtered too aggressively (e.g., kept 0), fallback to heuristic
        if not valid_keep_set and summaries:
            kept, warnings = _heuristic_curate(summaries)
            warnings.append("curate: LLM returned empty keep list, used heuristic instead")
            return {"curated_summaries": kept, "warnings": warnings, "active_node": "curate"}

        kept = [s for s in summaries if s.url in valid_keep_set]

        # Build warnings for dropped
        warnings: list[str] = []
        dropped_urls = input_urls - valid_keep_set
        if dropped_urls:
            # Map dropped reasons if LLM provided
            reason_map = {d.url: d.reason for d in output.dropped}
            for url in dropped_urls:
                reason = reason_map.get(url, "filtered by LLM")
                warnings.append(f"curate: dropped {url} — {reason}")

        # Also ensure we didn't lose base_url if it was dropped but we want to keep it
        # Be conservative: if kept < 2 and original had >2, keep at least 2
        # Not enforced; LLM is trusted

        return {"curated_summaries": kept, "warnings": warnings, "active_node": "curate"}

    except Exception as e:  # noqa: BLE001
        kept, warnings = _heuristic_curate(summaries)
        warnings.append(f"curate: LLM failed ({e}), used heuristic")
        return {
            "curated_summaries": kept,
            "warnings": warnings,
            "errors": [FetchError(url="", stage="curate", detail=str(e))],
            "active_node": "curate",
        }
