"""Validate — lint llms.txt format."""

from __future__ import annotations

from auto_llm_txt.state import SiteState
from auto_llm_txt.tools.renderer import validate_llms_txt


async def validate(state: SiteState) -> dict:
    llms_txt: str = state.get("llms_txt") or ""
    if not llms_txt.strip():
        return {"warnings": ["validate: llms_txt is empty"], "active_node": "validate"}

    warnings = validate_llms_txt(llms_txt)
    if warnings:
        # Prefix so they're distinguishable in the final error list
        warnings = [f"validate: {w}" for w in warnings]
        return {"warnings": warnings, "active_node": "validate"}

    return {"active_node": "validate"}
