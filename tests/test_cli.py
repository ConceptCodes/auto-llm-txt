from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from auto_llm_txt.cli import _stream_updates, parse_args


def test_parse_args_accepts_cli_options():
    args = parse_args(
        [
            "https://docs.example.com/guide",
            "--output",
            "build/docs",
            "--max-pages",
            "25",
            "--max-depth",
            "0",
            "--model",
            "example/model",
            "--no-full",
            "--no-preview",
            "--verbose",
        ]
    )

    assert args.url == "https://docs.example.com/guide"
    assert args.output_dir == "build/docs"
    assert args.max_pages == 25
    assert args.max_depth == 0
    assert args.model == "example/model"
    assert args.no_full is True
    assert args.no_preview is True
    assert args.verbose is True


@pytest.mark.parametrize(
    "url", ["example.com", "ftp://example.com", "https:///missing-host", "https://[invalid"]
)
def test_parse_args_rejects_invalid_urls(url: str):
    with pytest.raises(SystemExit, match="2"):
        parse_args([url])


@pytest.mark.parametrize(
    ("option", "value"),
    [("--max-pages", "0"), ("--max-pages", "nope"), ("--max-depth", "-1")],
)
def test_parse_args_rejects_invalid_limits(option: str, value: str):
    with pytest.raises(SystemExit, match="2"):
        parse_args(["https://example.com", option, value])


class FakeGraph:
    async def astream(self, initial, config, stream_mode):
        assert stream_mode == "updates"
        yield {"discover": {"urls": ["https://example.com/a", "https://example.com/b"]}}
        yield {"fetch": {"raw_pages": [{"url": "a"}, {"url": "b"}]}}
        yield {"extract": {"pages": [{"url": "a"}, {"url": "b"}]}}
        yield {
            "summarize_page": {
                "summaries": [
                    {"title": "Page A", "url": "https://example.com/a", "description": "A page"}
                ]
            }
        }
        yield {
            "summarize_page": {
                "summaries": [
                    {"title": "Page B", "url": "https://example.com/b", "description": "B page"}
                ]
            }
        }
        yield {"curate": {"curated_summaries": [{"url": "a"}]}}
        yield {"categorize": {"sections": [{"name": "Docs"}]}}
        yield {"compose": {}}
        yield {"validate": {}}
        yield {"write": {}}


@pytest.mark.asyncio
async def test_stream_updates_shows_human_progress():
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=100)

    await _stream_updates(FakeGraph(), {}, {}, console, verbose=False)

    rendered = output.getvalue()
    assert "Discovered 2 URLs" in rendered
    assert "Summarized 2 pages" in rendered
    assert "Selected 1 useful page" in rendered
    assert "Wrote output files" in rendered
    assert "Fan Out Summaries" not in rendered


@pytest.mark.asyncio
async def test_verbose_stream_includes_urls_and_summaries():
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=100)

    await _stream_updates(FakeGraph(), {}, {}, console, verbose=True)

    rendered = output.getvalue()
    assert "https://example.com/a" in rendered
    assert "Page A — A page" in rendered
