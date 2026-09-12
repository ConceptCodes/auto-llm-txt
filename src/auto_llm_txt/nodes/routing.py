"""Routing — conditional edge functions.

fan_out_summaries implements the Send API map-reduce pattern:
`extract` → fan_out → parallel `summarize_page` branches → `curate`.
"""

from __future__ import annotations

from langgraph.types import Send

from auto_llm_txt.state import SiteState


def fan_out_summaries(state: SiteState) -> list[Send]:
    """Conditional edge after `extract`: one Send per page.

    Returns a list of Send("summarize_page", {"page": page}) so each page is
    summarized in its own parallel branch. Results merge via the
    `Annotated[list[PageSummary], operator.add]` reducer on `summaries`.

    If there are no pages, return a no-op (graph will still proceed via the
    normal edge to curate; we return an empty list to signal nothing to fan out).
    """
    pages: list = state.get("pages") or []
    if not pages:
        return []
    return [Send("summarize_page", {"page": page}) for page in pages]
