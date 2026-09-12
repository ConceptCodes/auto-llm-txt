import pytest

from auto_llm_txt.agent import graph
from auto_llm_txt.config import settings
from auto_llm_txt.state import Page, RawPage


@pytest.mark.asyncio
async def test_graph_scaffold_single_page(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    config = {"configurable": {"thread_id": "test-scaffold-single"}}
    result = await graph.ainvoke(
        {"base_url": "https://example.com/", "output_dir": "./out", "max_pages": 5}, config
    )
    assert result["llms_txt"].startswith("# ")
    assert "> " in result["llms_txt"]
    assert "## " in result["llms_txt"]
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_graph_parallel_send(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    config = {"configurable": {"thread_id": "test-parallel"}}
    pages = [
        Page(url="https://example.com/a", title="A", markdown="Cats.", depth=0),
        Page(url="https://example.com/b", title="B", markdown="Dogs.", depth=1),
        Page(url="https://example.com/c", title="C", markdown="Birds.", depth=1),
    ]
    result = await graph.ainvoke(
        {
            "base_url": "https://example.com/",
            "output_dir": "./out",
            "max_pages": 5,
            "urls": [p.url for p in pages],
            "pages": pages,
        },
        config,
    )
    # Send API should produce 3 summaries in parallel
    assert len(result["summaries"]) == 3
    assert len(result["curated_summaries"]) == 3
    assert len(result["sections"]) == 1
    assert "Page A" in result["llms_txt"] or "A" in result["llms_txt"]


@pytest.mark.asyncio
async def test_graph_empty_pages_routes_to_curate(monkeypatch):
    """Verify Command(goto='curate') prevents dead-end when extract yields 0 pages."""
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    config = {"configurable": {"thread_id": "test-empty-pages"}}
    raw_pages = [RawPage(url="https://example.com/empty", html="", depth=0)]
    result = await graph.ainvoke(
        {
            "base_url": "https://example.com/",
            "output_dir": "./out",
            "urls": ["https://example.com/empty"],
            "raw_pages": raw_pages,
            "max_pages": 5,
        },
        config,
    )
    # Graph should complete all the way to write node
    assert result.get("active_node") == "write"
    assert result.get("sections") == []
