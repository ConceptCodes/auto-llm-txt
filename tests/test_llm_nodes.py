import pytest

from auto_llm_txt.config import settings
from auto_llm_txt.constants import PageQuality
from auto_llm_txt.state import Page, PageSummary, RawPage
from auto_llm_txt.state import CurateOutput, CategorizeOutput, CategorizeSectionOutput, SummarizeOutput, DropEntry


class FakeLLM:
    def __init__(self, output):
        self._output = output

    async def ainvoke(self, messages):
        return self._output


@pytest.mark.asyncio
async def test_summarize_with_llm(monkeypatch):
    from auto_llm_txt.nodes.summarize import summarize_page

    # Set dummy key to trigger LLM path
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    fake_output = SummarizeOutput(description="Sets up the project quickly", quality=PageQuality.high)

    def fake_get_structured(schema, llm=None):
        assert schema == SummarizeOutput
        return FakeLLM(fake_output)

    monkeypatch.setattr("auto_llm_txt.nodes.utils.get_structured_llm", fake_get_structured)

    page = Page(url="https://ex.com/setup", title="Setup", markdown="# Setup\nDo this...", depth=0)
    result = await summarize_page({"page": page})
    assert len(result["summaries"]) == 1
    s = result["summaries"][0]
    assert s.url == page.url
    assert s.title == page.title
    assert s.description == "Sets up the project quickly"
    assert s.quality == PageQuality.high
    assert "errors" not in result or not result.get("errors")


@pytest.mark.asyncio
async def test_summarize_llm_truncates_long_description(monkeypatch):
    from auto_llm_txt.nodes.summarize import summarize_page

    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    long_desc = "A" * 500
    fake_output = SummarizeOutput(description=long_desc, quality=PageQuality.medium)

    def fake_get_structured(schema, llm=None):
        return FakeLLM(fake_output)

    monkeypatch.setattr("auto_llm_txt.nodes.utils.get_structured_llm", fake_get_structured)
    page = Page(url="https://ex.com/a", title="A", markdown="hi", depth=0)
    result = await summarize_page({"page": page})
    desc = result["summaries"][0].description
    # Should be truncated to ~200 chars
    assert len(desc) <= 210


@pytest.mark.asyncio
async def test_summarize_fallback_on_llm_error(monkeypatch):
    from auto_llm_txt.nodes.summarize import summarize_page

    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    class FailingLLM:
        async def ainvoke(self, messages):
            raise RuntimeError("LLM down")

    def fake_get_structured(schema, llm=None):
        return FailingLLM()

    monkeypatch.setattr("auto_llm_txt.nodes.utils.get_structured_llm", fake_get_structured)
    page = Page(url="https://ex.com/a", title="Hello", markdown="Some content here", depth=0)
    result = await summarize_page({"page": page})
    # Should fallback to heuristic, still produce summary
    assert len(result["summaries"]) == 1
    assert result["summaries"][0].title == "Hello"
    # Should have error entry with fallback info
    assert any("LLM fallback" in e.detail for e in result.get("errors", []))


@pytest.mark.asyncio
async def test_summarize_heuristic_when_no_key(monkeypatch):
    from auto_llm_txt.nodes.summarize import summarize_page

    monkeypatch.setattr(settings, "openrouter_api_key", "")
    page = Page(url="https://ex.com/a", title="My Page", markdown="This is the first line\nSecond line", depth=0)
    result = await summarize_page({"page": page})
    assert result["summaries"][0].description == "This is the first line"
    assert result["summaries"][0].quality == PageQuality.medium


@pytest.mark.asyncio
async def test_curate_with_llm(monkeypatch):
    from auto_llm_txt.nodes.curate import curate

    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    summaries = [
        PageSummary(url="https://ex.com/a", title="A", description="Keep A", quality=PageQuality.high),
        PageSummary(url="https://ex.com/b", title="Privacy Policy", description="legal", quality=PageQuality.low),
        PageSummary(url="https://ex.com/c", title="C", description="Keep C", quality=PageQuality.medium),
    ]

    fake_output = CurateOutput(
        keep_urls=["https://ex.com/a", "https://ex.com/c"],
        dropped=[DropEntry(url="https://ex.com/b", reason="legal boilerplate")],
    )

    def fake_get_structured(schema, llm=None):
        assert schema == CurateOutput
        return FakeLLM(fake_output)

    monkeypatch.setattr("auto_llm_txt.nodes.utils.get_structured_llm", fake_get_structured)

    result = await curate({"summaries": summaries})
    kept = result["curated_summaries"]
    assert len(kept) == 2
    assert {p.url for p in kept} == {"https://ex.com/a", "https://ex.com/c"}
    assert any("dropped" in w for w in result.get("warnings", []))


@pytest.mark.asyncio
async def test_curate_heuristic_drops_low(monkeypatch):
    from auto_llm_txt.nodes.curate import curate

    monkeypatch.setattr(settings, "openrouter_api_key", "")
    summaries = [
        PageSummary(url="https://ex.com/a", title="A", description="Good", quality=PageQuality.high),
        PageSummary(url="https://ex.com/b", title="B", description="Bad", quality=PageQuality.low),
    ]
    result = await curate({"summaries": summaries})
    kept = result["curated_summaries"]
    assert len(kept) == 1
    assert kept[0].url == "https://ex.com/a"


@pytest.mark.asyncio
async def test_curate_llm_empty_keep_fallback(monkeypatch):
    from auto_llm_txt.nodes.curate import curate

    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    summaries = [
        PageSummary(url="https://ex.com/a", title="A", description="A", quality=PageQuality.high),
    ]
    # LLM returns empty keep list → should fallback to heuristic keeping all
    fake_output = CurateOutput(keep_urls=[], dropped=[])

    def fake_get_structured(schema, llm=None):
        return FakeLLM(fake_output)

    monkeypatch.setattr("auto_llm_txt.nodes.utils.get_structured_llm", fake_get_structured)

    result = await curate({"summaries": summaries})
    assert len(result["curated_summaries"]) == 1


@pytest.mark.asyncio
async def test_categorize_with_llm(monkeypatch):
    from auto_llm_txt.nodes.categorize import categorize

    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(settings, "site_title", "")

    curated = [
        PageSummary(url="https://ex.com/docs/intro", title="Intro", description="Intro", quality=PageQuality.high),
        PageSummary(url="https://ex.com/docs/api/users", title="Users API", description="Users", quality=PageQuality.high),
        PageSummary(url="https://ex.com/docs/api/posts", title="Posts API", description="Posts", quality=PageQuality.high),
    ]

    fake_output = CategorizeOutput(
        site_title="Example Docs",
        site_description="Docs for Example product.",
        sections=[
            CategorizeSectionOutput(name="Getting Started", description="Start here", page_urls=["https://ex.com/docs/intro"]),
            CategorizeSectionOutput(name="API Reference", description="API docs", page_urls=["https://ex.com/docs/api/users", "https://ex.com/docs/api/posts"]),
        ],
    )

    def fake_get_structured(schema, llm=None):
        assert schema == CategorizeOutput
        return FakeLLM(fake_output)

    monkeypatch.setattr("auto_llm_txt.nodes.utils.get_structured_llm", fake_get_structured)

    result = await categorize({"curated_summaries": curated, "base_url": "https://ex.com/docs/"})
    assert result["site_title"] == "Example Docs"
    assert "Docs for Example" in result["site_description"]
    assert len(result["sections"]) == 2
    assert result["sections"][0].name == "Getting Started"
    assert len(result["sections"][1].pages) == 2
    # Ensure all pages assigned
    all_urls = {p.url for sec in result["sections"] for p in sec.pages}
    assert all_urls == {p.url for p in curated}


@pytest.mark.asyncio
async def test_categorize_llm_handles_missing_urls(monkeypatch):
    from auto_llm_txt.nodes.categorize import categorize

    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    curated = [
        PageSummary(url="https://ex.com/a", title="A", description="A", quality=PageQuality.high),
        PageSummary(url="https://ex.com/b", title="B", description="B", quality=PageQuality.high),
        PageSummary(url="https://ex.com/c", title="C", description="C", quality=PageQuality.high),
    ]

    # LLM only assigns 1 url, misses b and c → should go to Other
    fake_output = CategorizeOutput(
        site_title="Test",
        site_description="Desc",
        sections=[
            CategorizeSectionOutput(name="Docs", description="", page_urls=["https://ex.com/a"]),
        ],
    )

    def fake_get_structured(schema, llm=None):
        return FakeLLM(fake_output)

    monkeypatch.setattr("auto_llm_txt.nodes.utils.get_structured_llm", fake_get_structured)

    result = await categorize({"curated_summaries": curated, "base_url": "https://ex.com/"})
    assert len(result["sections"]) == 2  # Docs + Other
    other = next(s for s in result["sections"] if s.name == "Other")
    assert len(other.pages) == 2
    assert any("not assigned" in w for w in result.get("warnings", []))


@pytest.mark.asyncio
async def test_categorize_heuristic(monkeypatch):
    from auto_llm_txt.nodes.categorize import categorize

    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "site_title", "")

    curated = [
        PageSummary(url="https://ex.com/docs/api/a", title="A", description="A", quality=PageQuality.high),
        PageSummary(url="https://ex.com/docs/api/b", title="B", description="B", quality=PageQuality.high),
        PageSummary(url="https://ex.com/docs/guide/c", title="C", description="C", quality=PageQuality.high),
        PageSummary(url="https://ex.com/docs/guide/d", title="D", description="D", quality=PageQuality.high),
        PageSummary(url="https://ex.com/docs/guide/e", title="E", description="E", quality=PageQuality.high),
        PageSummary(url="https://ex.com/docs/other/f", title="F", description="F", quality=PageQuality.high),
    ]
    # More than 5 pages should trigger grouping heuristic
    result = await categorize({"curated_summaries": curated, "base_url": "https://ex.com/docs/"})
    # Heuristic should group by first segment: api, guide, other
    assert len(result["sections"]) >= 2
    assert result["site_title"] == "ex.com"


@pytest.mark.asyncio
async def test_categorize_heuristic_small_site_single_section(monkeypatch):
    from auto_llm_txt.nodes.categorize import categorize

    monkeypatch.setattr(settings, "openrouter_api_key", "")
    curated = [
        PageSummary(url="https://ex.com/a", title="A", description="A", quality=PageQuality.high),
        PageSummary(url="https://ex.com/b", title="B", description="B", quality=PageQuality.high),
    ]
    result = await categorize({"curated_summaries": curated, "base_url": "https://ex.com/"})
    assert len(result["sections"]) == 1
    assert result["sections"][0].name == "Documentation"


@pytest.mark.asyncio
async def test_end_to_end_with_mocked_llm(monkeypatch):
    """Full graph with mocked LLM for all three stages."""
    from auto_llm_txt.agent import graph
    from auto_llm_txt.state import RawPage

    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(settings, "crawl_delay", 0)

    # Prepare raw pages (bypass discover/fetch)
    raw_pages = [
        RawPage(url="https://ex.com/docs/intro", html="<html><head><title>Intro</title></head><body><h1>Intro</h1><p>Welcome</p></body></html>", depth=0),
        RawPage(url="https://ex.com/docs/api", html="<html><head><title>API</title></head><body><h1>API</h1><p>API details</p></body></html>", depth=0),
        RawPage(url="https://ex.com/privacy", html="<html><head><title>Privacy</title></head><body><h1>Privacy</h1><p>legal stuff</p></body></html>", depth=0),
    ]
    urls = [rp.url for rp in raw_pages]

    # Mock summarize to return different qualities
    async def fake_summarize(state):
        page = state.get("page")
        url = page.url if hasattr(page, "url") else page.get("url")
        title = page.title if hasattr(page, "title") else page.get("title")
        # privacy should be low
        if "privacy" in url:
            return {"summaries": [PageSummary(url=url, title=title, description="Privacy policy", quality=PageQuality.low)]}
        return {"summaries": [PageSummary(url=url, title=title, description=f"Desc for {title}", quality=PageQuality.high)]}

    # For curate and categorize we still want LLM path, so mock get_structured_llm
    def fake_get_structured(schema, llm=None):
        if schema.__name__ == "CurateOutput":
            # Keep only non-privacy (high quality)
            return FakeLLM(CurateOutput(keep_urls=["https://ex.com/docs/intro", "https://ex.com/docs/api"], dropped=[DropEntry(url="https://ex.com/privacy", reason="legal")] ))
        if schema.__name__ == "CategorizeOutput":
            return FakeLLM(CategorizeOutput(
                site_title="Test Product",
                site_description="Test product docs.",
                sections=[
                    CategorizeSectionOutput(name="Getting Started", description="Intro", page_urls=["https://ex.com/docs/intro"]),
                    CategorizeSectionOutput(name="API Reference", description="API", page_urls=["https://ex.com/docs/api"]),
                ]
            ))
        # summarize should not use this when we patch summarize_page directly
        return FakeLLM(SummarizeOutput(description="fallback", quality=PageQuality.medium))

    monkeypatch.setattr("auto_llm_txt.nodes.summarize.get_structured_llm", fake_get_structured, raising=False)
    monkeypatch.setattr("auto_llm_txt.nodes.curate.get_structured_llm", fake_get_structured, raising=False)
    monkeypatch.setattr("auto_llm_txt.nodes.categorize.get_structured_llm", fake_get_structured, raising=False)
    # Actually summarize uses utils.get_structured_llm, so patch that too for the other path
    monkeypatch.setattr("auto_llm_txt.nodes.utils.get_structured_llm", fake_get_structured)

    # Patch summarize_page to use our fake_summarize logic (to avoid needing LLM for each page)
    monkeypatch.setattr("auto_llm_txt.nodes.summarize.summarize_page", fake_summarize)
    # Need to also patch the graph's reference: agent imports summarize_page at build time, so we need to rebuild graph
    # Simplest: call graph.ainvoke will still use the original compiled graph which captured old summarize_page.
    # So we need to rebuild a new graph for this test, or patch via monkeypatch on the module that graph uses.
    # The compiled graph's node function is the original; patching the source module won't affect already compiled graph.
    # Workaround: directly invoke nodes manually instead of full graph, or rebuild graph.
    from auto_llm_txt.agent import build_graph
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    # Build test graph with patched summarize
    import auto_llm_txt.nodes as nodes_module
    # monkeypatch already changed nodes.summarize.summarize_page, but build_graph imports from nodes/__init__
    # Reimport to get patched version
    import importlib
    import auto_llm_txt.nodes.summarize as sum_mod
    # Ensure build_graph picks up patched version by re-patching the nodes package
    monkeypatch.setattr(nodes_module, "summarize_page", fake_summarize)

    test_graph = build_graph()
    serde = JsonPlusSerializer(allowed_msgpack_modules=[
        ("auto_llm_txt.state", "RawPage"),
        ("auto_llm_txt.state", "Page"),
        ("auto_llm_txt.state", "PageSummary"),
        ("auto_llm_txt.state", "Section"),
        ("auto_llm_txt.state", "FetchError"),
        ("auto_llm_txt.constants", "PageQuality"),
    ])
    test_graph_compiled = test_graph.compile(checkpointer=InMemorySaver(serde=serde))

    result = await test_graph_compiled.ainvoke(
        {"base_url": "https://ex.com/", "urls": urls, "raw_pages": raw_pages, "max_pages": 10, "max_depth": 2},
        {"configurable": {"thread_id": "test-e2e-mocked-llm"}},
    )

    # Should have pruned privacy via curate LLM
    assert len(result["curated_summaries"]) == 2
    assert all("privacy" not in p.url for p in result["curated_summaries"])
    assert len(result["sections"]) == 2
    assert result["site_title"] == "Test Product"
    assert "Test product docs" in result["site_description"]
    # llms.txt should contain both kept pages, not privacy
    assert "privacy" not in result["llms_txt"].lower()
    assert "Intro" in result["llms_txt"]
