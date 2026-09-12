import pytest
import respx
from httpx import Response

from auto_llm_txt.config import settings
from auto_llm_txt.nodes.extract import extract
from auto_llm_txt.nodes.fetch import fetch
from auto_llm_txt.state import RawPage


@pytest.mark.asyncio
@respx.mock
async def test_fetch_concurrent_with_cache():
    # urls, with one already cached from discover BFS
    urls = [
        "https://fetch-test.example.com/docs/a",
        "https://fetch-test.example.com/docs/b",
        "https://fetch-test.example.com/docs/c",
    ]
    # One cached
    cached = RawPage(url=urls[0], html="<html><head><title>A</title></head><body>A</body></html>", depth=0)
    # Mock remaining two
    respx.get(urls[1]).mock(return_value=Response(200, text="<html><head><title>B</title></head><body>B</body></html>", headers={"content-type": "text/html"}))
    respx.get(urls[2]).mock(return_value=Response(200, text="<html><head><title>C</title></head><body>C</body></html>", headers={"content-type": "text/html"}))

    orig_delay = settings.crawl_delay
    settings.crawl_delay = 0
    orig_conc = settings.concurrency
    settings.concurrency = 2
    try:
        result = await fetch({"urls": urls, "raw_pages": [cached]})
    finally:
        settings.crawl_delay = orig_delay
        settings.concurrency = orig_conc

    raw_pages = result["raw_pages"]
    assert len(raw_pages) == 3
    assert {rp.url for rp in raw_pages} == set(urls)
    # Order should be same as urls
    assert [rp.url for rp in raw_pages] == urls
    # Cached one preserved depth 0 and html
    assert raw_pages[0].html == cached.html


@pytest.mark.asyncio
@respx.mock
async def test_fetch_handles_404():
    urls = [
        "https://fetch-test.example.com/docs/ok",
        "https://fetch-test.example.com/docs/missing",
    ]
    respx.get(urls[0]).mock(return_value=Response(200, text="<html><title>OK</title><body>hi</body></html>", headers={"content-type": "text/html"}))
    respx.get(urls[1]).mock(return_value=Response(404, text="not found"))

    orig_delay = settings.crawl_delay
    settings.crawl_delay = 0
    try:
        result = await fetch({"urls": urls, "raw_pages": []})
    finally:
        settings.crawl_delay = orig_delay

    raw_pages = result["raw_pages"]
    # Only ok should be present
    assert len(raw_pages) == 1
    assert raw_pages[0].url == urls[0]
    assert "errors" in result
    assert any("missing" in e.url for e in result["errors"])
    assert "warnings" in result


@pytest.mark.asyncio
async def test_extract_basic():
    raw_pages = [
        RawPage(url="https://ex.com/a", html="<html><head><title>Title A</title></head><body><h1>Heading</h1><p>Paragraph text.</p></body></html>", depth=0),
        RawPage(url="https://ex.com/b", html="<html><head><title>Title B</title></head><body><p>Just paragraph.</p></body></html>", depth=1),
    ]
    result = await extract({"raw_pages": raw_pages, "base_url": "https://ex.com/"})
    pages = result["pages"]
    assert len(pages) == 2
    assert pages[0].title == "Title A"
    assert "Heading" in pages[0].markdown
    assert "Paragraph text." in pages[0].markdown
    assert pages[1].title == "Title B"


@pytest.mark.asyncio
async def test_extract_fallback_to_pages():
    # When raw_pages empty but pages injected (scaffold tests)
    from auto_llm_txt.state import Page

    pages = [Page(url="https://ex.com/a", title="A", markdown="hi", depth=0)]
    result = await extract({"raw_pages": [], "pages": pages})
    assert result["pages"] == pages


@pytest.mark.asyncio
async def test_extract_empty_html():
    raw_pages = [RawPage(url="https://ex.com/empty", html="", depth=0)]
    result = await extract({"raw_pages": raw_pages})
    assert "warnings" in result
    # No pages extracted when html empty
    assert len(result["pages"]) == 0
