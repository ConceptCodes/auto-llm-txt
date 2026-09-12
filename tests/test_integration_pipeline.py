"""End-to-end pipeline via respx — discover → fetch → extract → summarize → compose."""

import pytest
import respx
from httpx import Response

from auto_llm_txt.agent import graph
from auto_llm_txt.config import settings


@pytest.mark.asyncio
@respx.mock
async def test_full_pipeline_bfs():
    base_url = "https://pipeline-test.example.com/docs/"
    origin = "https://pipeline-test.example.com"

    # Sitemap 404 → BFS
    respx.get(f"{origin}/robots.txt").mock(return_value=Response(404))
    respx.get(f"{origin}/docs/sitemap.xml").mock(return_value=Response(404))
    respx.get(f"{origin}/sitemap.xml").mock(return_value=Response(404))
    respx.get(f"{origin}/sitemap_index.xml").mock(return_value=Response(404))

    index_html = """<html><head><title>Docs Home</title></head><body>
      <h1>Home</h1>
      <a href="/docs/intro">Intro</a>
      <a href="/docs/setup">Setup</a>
    </body></html>"""
    intro_html = """<html><head><title>Introduction</title></head><body><h1>Introduction</h1><p>Welcome to the docs for our product.</p></body></html>"""
    setup_html = """<html><head><title>Setup</title></head><body><h1>Setup Guide</h1><p>How to set things up.</p></body></html>"""

    # Need mocks for discover BFS (fetch during discover) and then fetch node re-fetch?
    # But discover BFS already caches html for base, intro, setup; fetch will reuse cache
    # So we need to allow both phases: discover will fetch base_url then intro/setup during BFS.
    # However fetch will skip those because cached. So we only need one set of mocks.
    # But httpx respx expects each URL to be mocked once; with cache, each URL fetched once during discover.
    respx.get(base_url).mock(return_value=Response(200, text=index_html, headers={"content-type": "text/html"}))
    respx.get("https://pipeline-test.example.com/docs/intro").mock(return_value=Response(200, text=intro_html, headers={"content-type": "text/html"}))
    respx.get("https://pipeline-test.example.com/docs/setup").mock(return_value=Response(200, text=setup_html, headers={"content-type": "text/html"}))

    orig_delay = settings.crawl_delay
    settings.crawl_delay = 0
    try:
        result = await graph.ainvoke(
            {"base_url": base_url, "output_dir": "./out", "max_pages": 10, "max_depth": 2},
            {"configurable": {"thread_id": "test-pipeline-bfs"}},
        )
    finally:
        settings.crawl_delay = orig_delay

    # Verify pages extracted
    pages = result["pages"]
    assert len(pages) >= 3
    assert any(p.title == "Docs Home" or "Home" in p.title for p in pages)
    # Summaries via scaffold heuristic (no LLM key)
    assert len(result["summaries"]) == len(pages)
    # llms.txt valid
    llms_txt = result["llms_txt"]
    assert llms_txt.startswith("# ")
    assert "> " in llms_txt
    assert "## " in llms_txt
    # llms-full should contain each page's markdown or title
    full = result["llms_full_txt"]
    assert "Source: https://pipeline-test.example.com/docs/intro" in full
    assert "Introduction" in full


@pytest.mark.asyncio
@respx.mock
async def test_full_pipeline_sitemap():
    base_url = "https://pipeline-sitemap.example.com/docs/"
    origin = "https://pipeline-sitemap.example.com"

    respx.get(f"{origin}/robots.txt").mock(return_value=Response(404))
    sitemap_xml = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://pipeline-sitemap.example.com/docs/a</loc></url>
      <url><loc>https://pipeline-sitemap.example.com/docs/b</loc></url>
    </urlset>"""
    respx.get(f"{origin}/docs/sitemap.xml").mock(return_value=Response(200, text=sitemap_xml, headers={"content-type": "application/xml"}))
    respx.get(f"{origin}/sitemap.xml").mock(return_value=Response(404))
    respx.get(f"{origin}/sitemap_index.xml").mock(return_value=Response(404))

    # Pages for fetch phase (discover sitemap doesn't fetch html)
    a_html = """<html><head><title>A Page</title></head><body><h1>A Page</h1><p>Content A.</p></body></html>"""
    b_html = """<html><head><title>B Page</title></head><body><h1>B Page</h1><p>Content B.</p></body></html>"""
    # sitemap includes a and b, but discover will also add base_url if room; base_url fetch will happen in discover? No, sitemap path doesn't fetch base html during discover, so base_url not in raw cache. That's fine.
    # For fetch we need mocks for a and b (and maybe base_url if it was added)
    respx.get("https://pipeline-sitemap.example.com/docs/a").mock(return_value=Response(200, text=a_html, headers={"content-type": "text/html"}))
    respx.get("https://pipeline-sitemap.example.com/docs/b").mock(return_value=Response(200, text=b_html, headers={"content-type": "text/html"}))
    # Mock base_url as well in case discover added it
    respx.get(base_url).mock(return_value=Response(200, text="<html><head><title>Base</title></head><body>Base</body></html>", headers={"content-type": "text/html"}))

    orig_delay = settings.crawl_delay
    settings.crawl_delay = 0
    try:
        result = await graph.ainvoke(
            {"base_url": base_url, "output_dir": "./out", "max_pages": 10, "max_depth": 2},
            {"configurable": {"thread_id": "test-pipeline-sitemap"}},
        )
    finally:
        settings.crawl_delay = orig_delay

    pages = result["pages"]
    # Should have at least a and b; base may or may not be included depending on sitemap handling
    urls = {p.url for p in pages}
    assert "https://pipeline-sitemap.example.com/docs/a" in urls
    assert "https://pipeline-sitemap.example.com/docs/b" in urls
    assert result["llms_txt"].startswith("#")
