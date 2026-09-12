from auto_llm_txt.state import Page, PageSummary, Section
from auto_llm_txt.tools.renderer import render_llms_full_txt, render_llms_txt, validate_llms_txt


def test_render_llms_txt_single_section():
    sec = Section(
        name="Docs",
        description="All docs",
        pages=[
            PageSummary(url="https://example.com/a", title="A", description="Desc A"),
            PageSummary(url="https://example.com/b", title="B", description="Desc B"),
        ],
    )
    txt = render_llms_txt("Example", "An example site.", [sec])
    assert txt.startswith("# Example\n")
    assert "> An example site." in txt
    assert "## Docs" in txt
    assert "- [A](https://example.com/a): Desc A" in txt
    assert validate_llms_txt(txt) == []


def test_render_with_full_url():
    sec = Section(name="Guides", pages=[PageSummary(url="https://example.com/g", title="G", description="Guide")])
    txt = render_llms_txt("T", "D", [sec], full_txt_url="https://example.com/llms-full.txt")
    assert "## Optional" in txt
    assert "llms-full.txt" in txt


def test_render_empty_sections():
    txt = render_llms_txt("T", "D", [])
    assert "# T" in txt
    assert validate_llms_txt(txt) != []  # warns about no H2


def test_validate_missing_h1():
    assert any("H1" in w for w in validate_llms_txt("no h1\n> desc\n## Sec"))


def test_render_full_txt():
    pages = [
        Page(url="https://example.com/a", title="Page A", markdown="Hello **world**", depth=0),
        Page(url="https://example.com/b", title="Page B", markdown="Second", depth=1),
    ]
    full = render_llms_full_txt(pages, site_title="Example")
    assert "Source: https://example.com/a" in full
    assert "Hello **world**" in full
    assert full.count("---") == 2
