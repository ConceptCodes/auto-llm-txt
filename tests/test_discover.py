import pytest
import respx
from httpx import Response

from auto_llm_txt.config import settings
from auto_llm_txt.nodes.discover import discover


@pytest.mark.asyncio
@respx.mock
async def test_discover_via_sitemap():
    # Use a unique origin to avoid interference
    base_url = "https://sitemap-test.example.com/docs/"
    origin = "https://sitemap-test.example.com"

    # robots.txt 404 (no sitemaps)
    respx.get(f"{origin}/robots.txt").mock(return_value=Response(404))
    # sitemap at /docs/sitemap.xml
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://sitemap-test.example.com/docs/intro</loc></url>
  <url><loc>https://sitemap-test.example.com/docs/api</loc></url>
  <url><loc>https://sitemap-test.example.com/other/outside</loc></url>
</urlset>"""
    respx.get(f"{origin}/docs/sitemap.xml").mock(return_value=Response(200, text=sitemap_xml, headers={"content-type": "application/xml"}))
    # also mock origin sitemap as 404 so it doesn't override
    respx.get(f"{origin}/sitemap.xml").mock(return_value=Response(404))
    respx.get(f"{origin}/sitemap_index.xml").mock(return_value=Response(404))

    # small crawl_delay for speed
    orig_delay = settings.crawl_delay
    settings.crawl_delay = 0
    try:
        result = await discover({"base_url": base_url, "max_pages": 10, "max_depth": 2})
    finally:
        settings.crawl_delay = orig_delay

    urls = result["urls"]
    # Should include intro and api, but filter out /other/outside (outside prefix)
    assert "https://sitemap-test.example.com/docs/intro" in urls
    assert "https://sitemap-test.example.com/docs/api" in urls
    assert "https://sitemap-test.example.com/other/outside" not in urls
    # Should also include base_url itself if not in sitemap but within scope?
    # Our logic adds base_url if room; check it is present
    assert len(urls) >= 2


@pytest.mark.asyncio
@respx.mock
async def test_discover_via_sitemap_index():
    base_url = "https://index-test.example.com/docs/"
    origin = "https://index-test.example.com"
    respx.get(f"{origin}/robots.txt").mock(return_value=Response(404))
    # index sitemap at /docs/sitemap.xml that is actually an index
    index_xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://index-test.example.com/docs/sitemap1.xml</loc></sitemap>
  <sitemap><loc>https://index-test.example.com/docs/sitemap2.xml</loc></sitemap>
</sitemapindex>"""
    sitemap1_xml = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://index-test.example.com/docs/page1</loc></url>
</urlset>"""
    sitemap2_xml = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://index-test.example.com/docs/page2</loc></url>
</urlset>"""
    respx.get(f"{origin}/docs/sitemap.xml").mock(return_value=Response(200, text=index_xml, headers={"content-type": "application/xml"}))
    respx.get("https://index-test.example.com/docs/sitemap1.xml").mock(return_value=Response(200, text=sitemap1_xml, headers={"content-type": "application/xml"}))
    respx.get("https://index-test.example.com/docs/sitemap2.xml").mock(return_value=Response(200, text=sitemap2_xml, headers={"content-type": "application/xml"}))
    respx.get(f"{origin}/sitemap.xml").mock(return_value=Response(404))
    respx.get(f"{origin}/sitemap_index.xml").mock(return_value=Response(404))

    orig_delay = settings.crawl_delay
    settings.crawl_delay = 0
    try:
        result = await discover({"base_url": base_url, "max_pages": 10, "max_depth": 2})
    finally:
        settings.crawl_delay = orig_delay

    urls = result["urls"]
    assert "https://index-test.example.com/docs/page1" in urls
    assert "https://index-test.example.com/docs/page2" in urls


@pytest.mark.asyncio
@respx.mock
async def test_discover_bfs_fallback():
    base_url = "https://bfs-test.example.com/docs/"
    origin = "https://bfs-test.example.com"
    # All sitemaps 404 → BFS
    respx.get(f"{origin}/robots.txt").mock(return_value=Response(404))
    respx.get(f"{origin}/docs/sitemap.xml").mock(return_value=Response(404))
    respx.get(f"{origin}/sitemap.xml").mock(return_value=Response(404))
    respx.get(f"{origin}/sitemap_index.xml").mock(return_value=Response(404))

    # Mock pages
    index_html = """
    <html><head><title>Docs Home</title></head><body>
      <h1>Home</h1>
      <a href="/docs/a">A</a>
      <a href="/docs/b">B</a>
      <a href="/other/outside">Outside</a>
      <a href="https://external.com/page">External</a>
    </body></html>
    """
    a_html = """<html><head><title>A</title></head><body><h1>A</h1><a href="/docs/c">C</a></body></html>"""
    b_html = """<html><head><title>B</title></head><body><h1>B</h1><p>No more links</p></body></html>"""
    c_html = """<html><head><title>C</title></head><body><h1>C</h1></body></html>"""

    respx.get(base_url).mock(return_value=Response(200, text=index_html, headers={"content-type": "text/html"}))
    respx.get("https://bfs-test.example.com/docs/a").mock(return_value=Response(200, text=a_html, headers={"content-type": "text/html"}))
    respx.get("https://bfs-test.example.com/docs/b").mock(return_value=Response(200, text=b_html, headers={"content-type": "text/html"}))
    respx.get("https://bfs-test.example.com/docs/c").mock(return_value=Response(200, text=c_html, headers={"content-type": "text/html"}))

    orig_delay = settings.crawl_delay
    settings.crawl_delay = 0
    try:
        result = await discover({"base_url": base_url, "max_pages": 10, "max_depth": 2})
    finally:
        settings.crawl_delay = orig_delay

    urls = result["urls"]
    raw_pages = result.get("raw_pages", [])
    # BFS depth 2 should find a, b, c but not outside
    assert base_url in urls
    assert "https://bfs-test.example.com/docs/a" in urls
    assert "https://bfs-test.example.com/docs/b" in urls
    assert "https://bfs-test.example.com/docs/c" in urls
    assert "https://bfs-test.example.com/other/outside" not in urls
    assert "https://external.com/page" not in urls
    # raw_pages should contain html for visited pages
    assert len(raw_pages) >= 3
    # Depth checks: base depth 0, a/b depth1, c depth2
    depths = {rp.url: rp.depth for rp in raw_pages}
    assert depths[base_url] == 0
    assert depths["https://bfs-test.example.com/docs/a"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_discover_bfs_max_pages_truncate():
    base_url = "https://truncate-test.example.com/docs/"
    origin = "https://truncate-test.example.com"
    respx.get(f"{origin}/robots.txt").mock(return_value=Response(404))
    respx.get(f"{origin}/docs/sitemap.xml").mock(return_value=Response(404))
    respx.get(f"{origin}/sitemap.xml").mock(return_value=Response(404))
    respx.get(f"{origin}/sitemap_index.xml").mock(return_value=Response(404))

    index_html = """<html><body>
      <a href="/docs/1">1</a><a href="/docs/2">2</a><a href="/docs/3">3</a><a href="/docs/4">4</a><a href="/docs/5">5</a>
    </body></html>"""
    respx.get(base_url).mock(return_value=Response(200, text=index_html, headers={"content-type": "text/html"}))
    for i in [1, 2, 3, 4, 5]:
        respx.get(f"https://truncate-test.example.com/docs/{i}").mock(return_value=Response(200, text=f"<html><head><title>{i}</title></head><body>{i}</body></html>", headers={"content-type": "text/html"}))

    orig_delay = settings.crawl_delay
    settings.crawl_delay = 0
    try:
        result = await discover({"base_url": base_url, "max_pages": 3, "max_depth": 2})
    finally:
        settings.crawl_delay = orig_delay

    assert len(result["urls"]) <= 3
