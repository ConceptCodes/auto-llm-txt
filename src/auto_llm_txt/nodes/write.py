"""Write — persist llms.txt / llms-full.txt to disk."""

from __future__ import annotations

from pathlib import Path

from auto_llm_txt.state import SiteState


async def write(state: SiteState) -> dict:
    output_dir = state.get("output_dir") or "./out"
    llms_txt: str = state.get("llms_txt") or ""
    llms_full_txt: str = state.get("llms_full_txt") or ""

    if not llms_txt.strip():
        return {"warnings": ["write: nothing to write (llms_txt empty)"], "active_node": "write"}

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    (out / "llms.txt").write_text(llms_txt, encoding="utf-8")
    if llms_full_txt.strip():
        (out / "llms-full.txt").write_text(llms_full_txt, encoding="utf-8")

    return {"active_node": "write"}
