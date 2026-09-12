import operator
from typing import Annotated

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from auto_llm_txt.constants import PageQuality

# ---------------------------------------------------------------------------
# Pydantic models — structured data passed between nodes / to LLMs
# ---------------------------------------------------------------------------


class RawPage(BaseModel):
    url: str = Field(description="Canonical URL of the page")
    html: str = Field(description="Raw HTML content")
    depth: int = Field(default=0, description="Crawl depth from seed URL")


class Page(BaseModel):
    url: str = Field(description="Canonical URL of the page")
    title: str = Field(description="Page title")
    markdown: str = Field(description="Clean markdown content extracted from HTML")
    depth: int = Field(default=0, description="Crawl depth from seed URL")


class PageSummary(BaseModel):
    url: str
    title: str
    description: str = Field(description="One-line description for llms.txt entry")
    quality: PageQuality = PageQuality.medium


class Section(BaseModel):
    name: str = Field(description="H2 section heading, e.g. 'Docs', 'API Reference'")
    description: str = Field(default="", description="Optional short intro under the H2")
    pages: list[PageSummary] = Field(default_factory=list)


# --- Structured LLM output schemas ---


class SummarizeOutput(BaseModel):
    """LLM output for summarize_page (per page)."""

    description: str = Field(description="One-line description, <=20 words, specific to the page content")
    quality: PageQuality = Field(description="high=core docs, medium=useful, low=boilerplate/nav/legal")


class DropEntry(BaseModel):
    url: str = Field(description="URL of dropped page")
    reason: str = Field(description="Short reason for dropping")


class CurateOutput(BaseModel):
    """LLM output for curate (which URLs to keep)."""

    keep_urls: list[str] = Field(description="URLs to keep, in original order")
    dropped: list[DropEntry] = Field(default_factory=list, description="Dropped pages with reasons")


class CategorizeSectionOutput(BaseModel):
    name: str = Field(description="H2 section heading, Title Cased, 2-4 words")
    description: str = Field(default="", description="One-sentence intro for the section, may be empty")
    page_urls: list[str] = Field(description="URLs assigned to this section, each must be from input list")


class CategorizeOutput(BaseModel):
    """LLM output for categorize (sections + site summary)."""

    site_title: str = Field(description="Site title, e.g. product name")
    site_description: str = Field(description="1-2 sentence site-level summary for blockquote")
    sections: list[CategorizeSectionOutput] = Field(description="3-8 sections grouping the pages")


class FetchError(BaseModel):
    url: str
    stage: str
    detail: str


# ---------------------------------------------------------------------------
# LangGraph state — worker payload & shared graph state
# ---------------------------------------------------------------------------


class SummarizePageState(TypedDict):
    """Private worker payload passed to summarize_page via Send."""

    page: Page


class SiteState(TypedDict, total=False):
    # Inputs
    base_url: str
    output_dir: str
    max_pages: int
    max_depth: int

    # After discover
    urls: list[str]
    raw_pages: list[RawPage]

    # After fetch + extract
    pages: list[Page]

    # Fan-out summaries (needs add reducer for parallel Send branches)
    summaries: Annotated[list[PageSummary], operator.add]

    # After curate
    curated_summaries: list[PageSummary]

    # After categorize
    sections: list[Section]
    site_title: str
    site_description: str  # blockquote summary for top of llms.txt

    # After compose
    llms_txt: str
    llms_full_txt: str

    # Errors / warnings (parallel-safe)
    errors: Annotated[list[FetchError], operator.add]
    warnings: Annotated[list[str], operator.add]

    # Active node for streaming UI
    active_node: str
