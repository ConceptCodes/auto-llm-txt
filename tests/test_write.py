from __future__ import annotations

import asyncio

import pytest
from blockbuster import blockbuster_ctx

from auto_llm_txt.nodes.write import write


@pytest.mark.asyncio
async def test_write_moves_filesystem_work_off_event_loop(monkeypatch, tmp_path):
    calls = []
    real_to_thread = asyncio.to_thread

    async def tracked_to_thread(func, *args):
        calls.append((func, args))
        return await real_to_thread(func, *args)

    monkeypatch.setattr(asyncio, "to_thread", tracked_to_thread)

    with blockbuster_ctx():
        result = await write(
            {
                "output_dir": str(tmp_path),
                "llms_txt": "# Example\n",
                "llms_full_txt": "# Example (full)\n",
            }
        )

    assert result == {"active_node": "write"}
    assert len(calls) == 1
    assert (tmp_path / "llms.txt").read_text() == "# Example\n"
    assert (tmp_path / "llms-full.txt").read_text() == "# Example (full)\n"


@pytest.mark.asyncio
async def test_write_skips_filesystem_when_content_is_empty(monkeypatch):
    async def unexpected_to_thread(*args):
        pytest.fail("empty output should not schedule filesystem work")

    monkeypatch.setattr(asyncio, "to_thread", unexpected_to_thread)

    result = await write({"output_dir": "unused", "llms_txt": ""})

    assert result == {
        "warnings": ["write: nothing to write (llms_txt empty)"],
        "active_node": "write",
    }
