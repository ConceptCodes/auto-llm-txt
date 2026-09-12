"""Thin CLI entry — mirrors triage-bot's main.py style."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from rich.console import Console
from rich.table import Table

from auto_llm_txt.agent import graph
from auto_llm_txt.config import settings

console = Console()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="auto-llm-txt",
        description="Generate llms.txt for a documentation site.",
    )
    p.add_argument("url", help="Seed URL, e.g. https://docs.example.com/")
    p.add_argument(
        "-o",
        "--output",
        dest="output_dir",
        default=None,
        help="Output directory (default: ./out or $OUTPUT_DIR)",
    )
    p.add_argument("--max-pages", type=int, default=None, help="Max pages to crawl (default: 100)")
    p.add_argument("--max-depth", type=int, default=None, help="Max crawl depth (default: 4)")
    p.add_argument("--model", default=None, help="LLM model, e.g. openai/gpt-4o-mini")
    return p.parse_args()


async def _run() -> None:
    args = parse_args()

    base_url = args.url.strip()
    if not base_url.startswith(("http://", "https://")):
        print(f"Error: url must start with http(s):// — got '{base_url}'", file=sys.stderr)
        sys.exit(1)

    # Resolve effective config (CLI overrides > env > defaults)
    output_dir = args.output_dir or settings.output_dir
    max_pages = args.max_pages if args.max_pages is not None else settings.max_pages
    max_depth = args.max_depth if args.max_depth is not None else settings.max_depth
    if args.model:
        # Override in-memory for this run (no mutation of global settings needed elsewhere)
        settings.llm_model = args.model

    thread_id = str(uuid.uuid4())
    console.print(f"[bold]auto-llm-txt[/bold]  seed=[cyan]{base_url}[/cyan]  thread={thread_id}")
    if not settings.openrouter_api_key:
        console.print("[yellow]Warning: OPENROUTER_API_KEY not set — LLM steps will use scaffold heuristics.[/yellow]")

    config = {"configurable": {"thread_id": thread_id}}
    initial = {
        "base_url": base_url,
        "output_dir": output_dir,
        "max_pages": max_pages,
        "max_depth": max_depth,
    }

    current_step = ""
    async for event in graph.astream(initial, config, stream_mode="updates"):
        for node_name, node_output in event.items():
            if node_name != current_step:
                current_step = node_name
                label = node_name.replace("_", " ").title()
                console.print(f"\n[bold]--- {label} ---[/bold]")
            # Surface warnings/errors per node
            if isinstance(node_output, dict):
                for w in node_output.get("warnings", []) or []:
                    console.print(f"  [yellow]warn:[/yellow] {w}")
                for e in node_output.get("errors", []) or []:
                    # e may be FetchError model
                    if isinstance(e, dict):
                        console.print(f"  [red]error:[/red] {e}")
                    else:
                        url = getattr(e, "url", "")
                        detail = getattr(e, "detail", str(e))
                        console.print(f"  [red]error:[/red] {url} — {detail}")

    state = graph.get_state(config).values

    llms_txt: str = state.get("llms_txt") or ""
    llms_full_txt: str = state.get("llms_full_txt") or ""
    errors = state.get("errors") or []
    warnings = state.get("warnings") or []
    sections = state.get("sections") or []
    summaries = state.get("summaries") or state.get("curated_summaries") or []

    # Summary table
    table = Table(title="Result", show_header=False)
    table.add_column("key", style="bold")
    table.add_column("value")
    table.add_row("output_dir", output_dir)
    table.add_row("sections", str(len(sections)))
    table.add_row("pages indexed", str(len(summaries)))
    table.add_row("llms.txt bytes", str(len(llms_txt)))
    table.add_row("llms-full.txt bytes", str(len(llms_full_txt)))
    table.add_row("warnings", str(len(warnings)))
    table.add_row("errors", str(len(errors)))
    console.print(table)

    if llms_txt:
        console.print(f"\n[green]Wrote[/green] {output_dir}/llms.txt")
        # Also print preview (first 40 lines)
        preview = "\n".join(llms_txt.splitlines()[:40])
        console.print("[dim]" + preview + "[/dim]")
        if len(llms_txt.splitlines()) > 40:
            console.print("[dim]... (truncated, see file for full output)[/dim]")
    else:
        console.print("[red]No llms.txt generated.[/red]")

    if llms_full_txt:
        console.print(f"[green]Wrote[/green] {output_dir}/llms-full.txt")

    if errors:
        console.print(f"[red]{len(errors)} error(s) — check output above.[/red]")
        sys.exit(2)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
