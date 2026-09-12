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

import re

from auto_llm_txt.state import Page, Section


def _single_line(value: str, fallback: str = "") -> str:
    """Collapse untrusted text so it cannot inject llms.txt structure."""
    return " ".join(value.split()).strip() or fallback


def _link_title(value: str) -> str:
    return _single_line(value, "Untitled").replace("[", "\\[").replace("]", "\\]")


def _link_url(value: str) -> str:
    """Encode characters that can terminate a Markdown link destination."""
    return value.strip().replace(" ", "%20").replace("(", "%28").replace(")", "%29")


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
    title = _single_line(site_title, "Untitled Site")
    lines.append(f"# {title}")
    lines.append("")

    # The blockquote is optional in v2, but including a useful summary is best practice.
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
            lines.append(f"## {_single_line(section.name, 'Documentation')}")
            lines.append("")
            for page in section.pages:
                safe_title = _link_title(page.title)
                safe_url = _link_url(page.url)
                safe_desc = _single_line(page.description)
                suffix = f": {safe_desc}" if safe_desc else ""
                lines.append(f"- [{safe_title}]({safe_url}){suffix}")
            lines.append("")

    if full_txt_url:
        lines.append("## Optional")
        lines.append("")
        lines.append(
            f"- [Full documentation dump]({_link_url(full_txt_url)}): "
            "Complete markdown for the curated pages"
        )
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
        parts.append(f"# {_single_line(site_title)} — Full Documentation")
        parts.append("")

    for page in pages:
        parts.append(f"# {_single_line(page.title, 'Untitled')}")
        parts.append("")
        parts.append(f"Source: {_single_line(page.url)}")
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

    first_line = lines[0].lstrip("\ufeff")
    if not first_line.startswith("# ") or first_line.startswith("## "):
        warnings.append("First non-empty line must be an H1 title ('# ...')")

    link_pattern = re.compile(r"^-\s+\[(?:\\.|[^]])+\]\(([^)]+)\)(?::\s*.*)?$")
    in_file_list = False
    section_has_link = False
    seen_urls: set[str] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            if in_file_list and not section_has_link:
                warnings.append(f"Line {line_number}: preceding H2 section has no file links")
            in_file_list = True
            section_has_link = False
            continue
        if line.startswith("#") and not line.startswith("## ") and line_number != 1:
            warnings.append(f"Line {line_number}: only the first heading may be an H1")
        if not in_file_list or not line.strip():
            continue
        match = link_pattern.fullmatch(line)
        if not match:
            warnings.append(
                f"Line {line_number}: H2 sections may contain only Markdown file-list links"
            )
            continue
        section_has_link = True
        url = match.group(1)
        if url in seen_urls:
            warnings.append(f"Line {line_number}: duplicate link URL {url}")
        seen_urls.add(url)

    if in_file_list and not section_has_link:
        warnings.append("Final H2 section has no file links")

    return warnings
