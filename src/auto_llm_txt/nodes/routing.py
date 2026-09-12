"""Routing — conditional edge functions.

fan_out_summaries implements the Send API map-reduce pattern:
`extract` → fan_out → parallel `summarize_page` branches → `curate`.
"""

from __future__ import annotations

from typing import Literal

from langgraph.types import Command, Send

from auto_llm_txt.state import SiteState, SummarizePageState


def fan_out_summaries(state: SiteState) -> Command[Literal["curate", "summarize_page"]]:
    """Route pages using the Command API.

    Returns a Command routing to parallel `summarize_page` workers via Send,
    or directly jumps to `curate` if no pages are available.
    """
    pages: list = state.get("pages") or []
    if not pages:
        return Command(goto="curate")
    return Command(goto=[Send("summarize_page", SummarizePageState(page=page)) for page in pages])
