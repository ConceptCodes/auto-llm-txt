"""Summarize — per-page LLM summarization (Send API fan-out target).

Each invocation handles exactly ONE page (private state via Send).
Returns a single PageSummary with an add-reducer so parallel branches merge.
Uses LLM when OPENROUTER_API_KEY is set; otherwise heuristic fallback.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from auto_llm_txt.config import settings
from auto_llm_txt.constants import PageQuality
from auto_llm_txt.prompts import SUMMARIZE_PAGE
from auto_llm_txt.state import FetchError, PageSummary, SummarizeOutput, SummarizePageState


def _heuristic_description(title: str, markdown: str) -> tuple[str, PageQuality]:
    """Fallback when LLM unavailable: first meaningful line + medium quality."""
    text = markdown.strip()
    if not text:
        return "No meaningful page content could be extracted", PageQuality.low

    content_lines = {line.strip().casefold() for line in text.splitlines() if line.strip()}
    listing_shell_labels = {"name", "type", "size", "documents", "search"}
    if content_lines and content_lines <= listing_shell_labels:
        return "Document listing with no extractable item details", PageQuality.low

    if text:
        first = text.split("\n")[0].strip().lstrip("# ").strip()
        # Also handle markdown headings: "# Title" -> use next line if first is just title
        if first.lower() == title.strip().lower() and "\n" in text:
            # Try second line
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            for line in lines[1:]:
                clean = line.lstrip("#").strip()
                if clean and len(clean) > 5:
                    first = clean
                    break
        if len(first) > 120:
            first = first[:117].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."
        if first:
            # Simple quality heuristic: very short or boilerplate → low
            lower = first.lower()
            if any(kw in lower for kw in ["404", "not found", "privacy", "terms of service", "cookie"]):
                return first, PageQuality.low
            return first, PageQuality.medium
    return "No meaningful page content could be extracted", PageQuality.low


async def summarize_page(state: SummarizePageState, config: RunnableConfig = None) -> dict:
    """Summarize a single page.

    Input `state` is the typed worker payload: SummarizePageState(page=Page).
    LangGraph gives each Send branch its own private state.
    """
    page = state.get("page")
    if page is None:
        return {"errors": [FetchError(url="", stage="summarize", detail="missing page in Send payload")]}

    # Support both Page model and plain dict (from Send)
    if isinstance(page, dict):
        url = page.get("url", "")
        title = page.get("title", "Untitled")
        markdown = page.get("markdown", "")
    else:
        url = getattr(page, "url", "")
        title = getattr(page, "title", "Untitled")
        markdown = getattr(page, "markdown", "")

    # Fast path: no LLM key → heuristic
    if not settings.openrouter_api_key:
        description, quality = _heuristic_description(title, markdown)
        summary = PageSummary(url=url, title=title, description=description, quality=quality)
        return {"summaries": [summary]}

    # LLM path
    try:
        from auto_llm_txt.utils import get_structured_llm

        llm = get_structured_llm(SummarizeOutput)
        # Truncate markdown to keep prompt bounded (~3000 chars ≈ 750 tokens)
        excerpt = markdown.strip()[:3000]
        if len(markdown) > 3000:
            excerpt += "\n\n[... truncated]"
        # Fallback for empty markdown
        if not excerpt:
            excerpt = "(no content extracted)"

        messages = [
            SystemMessage(content=SUMMARIZE_PAGE),
            HumanMessage(
                content=f"Title: {title}\nURL: {url}\n\nMarkdown excerpt:\n{excerpt}"
            ),
        ]
        if config is not None:
            result: SummarizeOutput = await llm.ainvoke(messages, config=config)  # type: ignore[assignment]
        else:
            result: SummarizeOutput = await llm.ainvoke(messages)  # type: ignore[assignment]

        # Coerce quality to enum if LLM returned string
        quality = result.quality
        if isinstance(quality, str):
            try:
                quality = PageQuality(quality.lower())
            except ValueError:
                quality = PageQuality.medium

        description = result.description.strip().replace("\n", " ")
        # Enforce one sentence / 120 char cap? Keep as LLM gave but truncate a bit
        if len(description) > 200:
            description = description[:197].rstrip() + "..."

        if not description:
            description, quality = _heuristic_description(title, markdown)

        summary = PageSummary(url=url, title=title, description=description, quality=quality)
        return {"summaries": [summary]}

    except Exception as e:  # noqa: BLE001
        # LLM failed → heuristic fallback, but also surface as warning via error
        description, quality = _heuristic_description(title, markdown)
        summary = PageSummary(url=url, title=title, description=description, quality=quality)
        return {
            "summaries": [summary],
            "errors": [FetchError(url=url, stage="summarize", detail=f"LLM fallback: {e}")],
        }
