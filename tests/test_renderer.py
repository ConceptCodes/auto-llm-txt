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
    assert "All docs" not in txt  # H2 sections are machine-parseable file lists only
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
    assert validate_llms_txt(txt) == []  # H2 sections are optional in the v2 proposal


def test_validate_missing_h1():
    assert any("H1" in w for w in validate_llms_txt("no h1\n> desc\n## Sec"))


def test_validate_rejects_prose_inside_file_list_section():
    text = "# Site\n\n## Docs\n\nIntro prose\n\n- [Page](https://example.com/page)\n"

    assert any("only Markdown file-list links" in warning for warning in validate_llms_txt(text))


def test_render_collapses_structural_text_and_escapes_link_urls():
    section = Section(
        name="Docs\n## Injected",
        pages=[
            PageSummary(
                url="https://example.com/a_(test)",
                title="Page\n# Injected",
                description="First line\nSecond line",
            )
        ],
    )

    text = render_llms_txt("Site\n# Injected", "Summary", [section])

    assert text.startswith("# Site # Injected\n")
    assert "## Docs ## Injected" in text
    assert "[Page # Injected](https://example.com/a_%28test%29): First line Second line" in text
    assert validate_llms_txt(text) == []


def test_render_full_txt():
    pages = [
        Page(url="https://example.com/a", title="Page A", markdown="Hello **world**", depth=0),
        Page(url="https://example.com/b", title="Page B", markdown="Second", depth=1),
    ]
    full = render_llms_full_txt(pages, site_title="Example")
    assert "Source: https://example.com/a" in full
    assert "Hello **world**" in full
    assert full.count("---") == 2
