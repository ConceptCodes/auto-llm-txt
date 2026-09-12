from auto_llm_txt.tools.crawler import filter_and_dedupe, is_same_prefix, parse_sitemap


def test_parse_sitemap_basic():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a</loc></url>
  <url><loc>https://example.com/b</loc></url>
</urlset>"""
    assert parse_sitemap(xml) == ["https://example.com/a", "https://example.com/b"]


def test_parse_sitemap_index():
    xml = """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap2.xml</loc></sitemap>
</sitemapindex>"""
    urls = parse_sitemap(xml)
    assert "https://example.com/sitemap1.xml" in urls


def test_is_same_prefix():
    base = "https://example.com/docs/"
    assert is_same_prefix("https://example.com/docs/a", base) is True
    assert is_same_prefix("https://example.com/docs", base) is True  # /docs == /docs
    assert is_same_prefix("https://example.com/other", base) is False
    assert is_same_prefix("https://other.com/docs/a", base) is False
    # root prefix matches everything on same host
    assert is_same_prefix("https://example.com/anything", "https://example.com/") is True


def test_filter_and_dedupe():
    base = "https://example.com/docs/"
    urls = [
        "https://example.com/docs/a",
        "https://example.com/docs/a",  # dupe
        "https://example.com/other",
        "/docs/b",
        "mailto:foo@example.com",
    ]
    filtered = filter_and_dedupe(urls, base)
    assert "https://example.com/docs/a" in filtered
    assert "https://example.com/docs/b" in filtered
    assert "https://example.com/other" not in filtered
    assert len([u for u in filtered if u == "https://example.com/docs/a"]) == 1
