"""Renderer — pure functions that format llms.txt / llms-full.txt per spec.

Spec: https://llmstxt.org

llms.txt format:
  H1 title
  > blockquote summary (may span multiple lines)
  optional extra prose
  ## Section Name
  - [Title](url): description
  ## Optional
  - [Full content](url/full): Complete markdown dump (if include_full)

All functions are pure and heavily unit-tested via golden files.
"""

from auto_llm_txt.state import Page, Section


def render_llms_txt(
    site_title: str,
    site_description: str,
    sections: list[Section],
    *,
    full_txt_url: str | None = None,
) -> str:
    """Render a spec-compliant llms.txt string.

    Args:
        site_title: H1 title (required).
        site_description: Blockquote summary. Single paragraph preferred.
        sections: Ordered list of sections with curated page summaries.
        full_txt_url: If provided, appended as an Optional/Full section.

    Returns:
        Markdown string ending with a newline. H1 is always first line.
    """
    lines: list[str] = []

    # H1 — required to be first non-empty line per spec
    title = site_title.strip() or "Untitled Site"
    lines.append(f"# {title}")
    lines.append("")

    # Blockquote — required
    desc = site_description.strip() or "Documentation for this site."
    # Support multi-line descriptions: prefix each line with > 
    for line in desc.splitlines():
        line = line.strip()
        if line:
            lines.append(f"> {line}")
        else:
            lines.append(">")
    lines.append("")

    if not sections:
        lines.append("_No sections generated._")
        lines.append("")
    else:
        for section in sections:
            lines.append(f"## {section.name.strip()}")
            lines.append("")
            if section.description and section.description.strip():
                lines.append(section.description.strip())
                lines.append("")
            for page in section.pages:
                # Escape brackets in title minimally
                safe_title = page.title.strip().replace("[", "\\[").replace("]", "\\]")
                safe_desc = page.description.strip().replace("\n", " ")
                lines.append(f"- [{safe_title}]({page.url}): {safe_desc}")
            lines.append("")

    if full_txt_url:
        lines.append("## Optional")
        lines.append("")
        lines.append(f"- [Full documentation dump]({full_txt_url}): Complete markdown for all pages")
        lines.append("")

    # Ensure single trailing newline, no excessive blank lines at end
    text = "\n".join(lines).rstrip() + "\n"
    return text


def render_llms_full_txt(pages: list[Page], site_title: str = "") -> str:
    """Render llms-full.txt — concatenated markdown of all pages."""
    if not pages:
        return ""

    parts: list[str] = []
    if site_title:
        parts.append(f"# {site_title} — Full Documentation")
        parts.append("")

    for page in pages:
        parts.append(f"# {page.title.strip()}")
        parts.append("")
        parts.append(f"Source: {page.url}")
        parts.append("")
        body = page.markdown.strip()
        if body:
            parts.append(body)
        else:
            parts.append("_No content extracted._")
        parts.append("")
        parts.append("---")
        parts.append("")

    text = "\n".join(parts).rstrip() + "\n"
    return text


def validate_llms_txt(text: str) -> list[str]:
    """Lint llms.txt; return list of warning strings (empty = valid)."""
    warnings: list[str] = []
    stripped = text.strip()
    if not stripped:
        return ["File is empty"]

    lines = [line for line in text.splitlines() if line.strip() != ""]
    if not lines:
        return ["File is empty"]

    if not lines[0].startswith("# "):
        warnings.append("First non-empty line must be an H1 title ('# ...')")

    has_blockquote = any(line.lstrip().startswith(">") for line in text.splitlines())
    if not has_blockquote:
        warnings.append("Missing blockquote summary ('> ...') after H1")

    # Check for at least one section
    has_h2 = any(line.startswith("## ") for line in text.splitlines())
    if not has_h2:
        warnings.append("No H2 sections found — at least one '## ...' expected")

    # Check for malformed list items (naive)
    for i, line in enumerate(text.splitlines(), start=1):
        if line.startswith("- [") and "](" not in line:
            warnings.append(f"Line {i}: malformed link — missing ']('")

    return warnings
