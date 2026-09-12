from __future__ import annotations

import pytest

from auto_llm_txt.nodes.compose import compose
from auto_llm_txt.state import Page


@pytest.mark.asyncio
async def test_compose_can_omit_full_document():
    result = await compose(
        {
            "base_url": "https://docs.example.com/",
            "site_title": "Example",
            "pages": [
                Page(
                    url="https://docs.example.com/start",
                    title="Start",
                    markdown="Get started.",
                )
            ],
            "include_full": False,
        }
    )

    assert result["llms_full_txt"] == ""
    assert "llms-full.txt" not in result["llms_txt"]


@pytest.mark.asyncio
async def test_full_document_contains_only_curated_pages():
    kept = Page(url="https://example.com/keep", title="Keep", markdown="Useful")
    dropped = Page(url="https://example.com/drop", title="Drop", markdown="Noise")

    result = await compose(
        {
            "base_url": "https://example.com/",
            "site_title": "Example",
            "pages": [kept, dropped],
            "curated_summaries": [
                {"url": kept.url, "title": kept.title, "description": "Useful page"}
            ],
            "include_full": True,
        }
    )

    assert kept.url in result["llms_full_txt"]
    assert dropped.url not in result["llms_full_txt"]
