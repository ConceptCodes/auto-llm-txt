"""Command-line interface for auto-llm-txt."""

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from auto_llm_txt import __version__
from auto_llm_txt.config import settings


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return number


def _http_url(value: str) -> str:
    url = value.strip()
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a valid URL") from exc
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise argparse.ArgumentTypeError("must be an absolute http:// or https:// URL")
    return url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto-llm-txt",
        description="Generate llms.txt for a website.",
    )
    parser.add_argument("url", type=_http_url, help="seed URL, e.g. https://docs.example.com/")
    parser.add_argument(
        "-o",
        "--output",
        dest="output_dir",
        default=None,
        metavar="DIR",
        help=f"output directory (environment/default: {settings.output_dir})",
    )
    parser.add_argument(
        "--max-pages",
        type=_positive_int,
        default=None,
        metavar="N",
        help=f"maximum pages to crawl (environment/default: {settings.max_pages})",
    )
    parser.add_argument(
        "--max-depth",
        type=_non_negative_int,
        default=None,
        metavar="N",
        help=f"maximum crawl depth (environment/default: {settings.max_depth})",
    )
    parser.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help=f"LLM model (environment/default: {settings.llm_model})",
    )
    parser.add_argument(
        "--no-full",
        action="store_true",
        help="do not generate llms-full.txt or link to it",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="do not print an llms.txt preview",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show configuration, discovered URLs, and per-page summaries",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def _counted(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


async def _stream_updates(
    graph, initial: dict, config: dict, console: Console, verbose: bool
) -> None:
    """Render graph updates as user-facing progress instead of internal node names."""
    next_status = {
        "discover": "Fetching pages",
        "fetch": "Extracting readable content",
        "curate": "Organizing sections",
        "categorize": "Rendering files",
        "compose": "Validating output",
        "validate": "Writing files",
    }
    pages_to_summarize = 0
    summaries_completed = 0

    with console.status("[cyan]Discovering pages...[/cyan]", spinner="dots") as status:
        async for event in graph.astream(initial, config, stream_mode="updates"):
            for node_name, node_output in event.items():
                output = node_output if isinstance(node_output, dict) else {}

                if node_name == "discover":
                    urls = output.get("urls", []) or []
                    console.print(
                        f"[green]✓[/green] Discovered [bold]{_counted(len(urls), 'URL')}[/bold]"
                    )
                    if verbose:
                        for url in urls:
                            console.print(Text(f"    {url}", style="dim"))
                elif node_name == "fetch":
                    raw_pages = output.get("raw_pages", []) or []
                    console.print(
                        f"[green]✓[/green] Fetched [bold]{_counted(len(raw_pages), 'page')}[/bold]"
                    )
                elif node_name == "extract":
                    pages = output.get("pages", []) or []
                    pages_to_summarize = len(pages)
                    console.print(
                        f"[green]✓[/green] Extracted "
                        f"[bold]{_counted(pages_to_summarize, 'page')}[/bold]"
                    )
                    status.update(f"[cyan]Summarizing pages 0/{pages_to_summarize}...[/cyan]")
                elif node_name == "summarize_page":
                    page_summaries = output.get("summaries", []) or []
                    summaries_completed += len(page_summaries) or 1
                    status.update(
                        "[cyan]Summarizing pages "
                        f"{min(summaries_completed, pages_to_summarize)}/{pages_to_summarize}...[/cyan]"
                    )
                    if verbose:
                        for summary in page_summaries:
                            if isinstance(summary, dict):
                                title = summary.get("title", "Untitled")
                                url = summary.get("url", "")
                                description = summary.get("description", "")
                            else:
                                title = summary.title
                                url = summary.url
                                description = summary.description
                            detail = Text("    ")
                            detail.append(str(title), style="bold")
                            detail.append(f" — {description}\n", style="dim")
                            detail.append(f"      {url}", style="cyan")
                            console.print(detail)
                    if summaries_completed >= pages_to_summarize:
                        console.print(
                            f"[green]✓[/green] Summarized "
                            f"[bold]{_counted(summaries_completed, 'page')}[/bold]"
                        )
                        status.update("[cyan]Curating useful pages...[/cyan]")
                elif node_name == "curate":
                    curated = output.get("curated_summaries", []) or []
                    console.print(
                        f"[green]✓[/green] Selected "
                        f"[bold]{_counted(len(curated), 'useful page')}[/bold]"
                    )
                elif node_name == "categorize":
                    sections = output.get("sections", []) or []
                    console.print(
                        f"[green]✓[/green] Organized "
                        f"[bold]{_counted(len(sections), 'section')}[/bold]"
                    )
                elif node_name == "compose":
                    console.print("[green]✓[/green] Rendered llms.txt files")
                elif node_name == "validate":
                    console.print("[green]✓[/green] Validated output")
                elif node_name == "write":
                    console.print("[green]✓[/green] Wrote output files")

                if node_name in next_status:
                    status.update(f"[cyan]{next_status[node_name]}...[/cyan]")

                for warning in output.get("warnings", []) or []:
                    console.print(f"  [yellow]warning:[/yellow] {escape(str(warning))}")
                for error in output.get("errors", []) or []:
                    if isinstance(error, dict):
                        console.print(f"  [red]error:[/red] {escape(str(error))}")
                    else:
                        url = getattr(error, "url", "")
                        detail = getattr(error, "detail", str(error))
                        console.print(
                            f"  [red]error:[/red] {escape(str(url))} — {escape(str(detail))}"
                        )


async def run(args: argparse.Namespace, console: Console) -> int:
    from auto_llm_txt.agent import graph

    output_dir = Path(args.output_dir or settings.output_dir).expanduser()
    max_pages = args.max_pages if args.max_pages is not None else settings.max_pages
    max_depth = args.max_depth if args.max_depth is not None else settings.max_depth
    include_full = settings.include_full and not args.no_full
    if args.model:
        settings.llm_model = args.model

    thread_id = str(uuid.uuid4())
    heading = Text()
    heading.append("Generate llms.txt", style="bold")
    heading.append("\n")
    heading.append(args.url, style="cyan")
    heading.append(f"\nUp to {max_pages} pages · crawl depth {max_depth}", style="dim")
    console.print(
        Panel.fit(
            heading,
            title="[bold cyan]auto-llm-txt[/bold cyan]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    if args.verbose:
        details = Table.grid(padding=(0, 2))
        details.add_column(style="bold")
        details.add_column()
        details.add_row("Output", Text(str(output_dir.resolve())))
        details.add_row("Model", Text(settings.llm_model))
        details.add_row("Full document", "yes" if include_full else "no")
        details.add_row("Thread", thread_id)
        console.print(details)
        console.print()
    if not settings.openrouter_api_key:
        console.print(
            "[yellow]Warning: OPENROUTER_API_KEY is not set; "
            "LLM steps will use scaffold heuristics.[/yellow]"
        )

    config = {"configurable": {"thread_id": thread_id}}
    initial = {
        "base_url": args.url,
        "output_dir": str(output_dir),
        "max_pages": max_pages,
        "max_depth": max_depth,
        "include_full": include_full,
    }

    await _stream_updates(graph, initial, config, console, args.verbose)

    state = graph.get_state(config).values
    llms_txt: str = state.get("llms_txt") or ""
    llms_full_txt: str = state.get("llms_full_txt") or ""
    errors = state.get("errors") or []
    warnings = state.get("warnings") or []
    sections = state.get("sections") or []
    summaries = state.get("summaries") or state.get("curated_summaries") or []
    linked_pages = sum(len(section.pages) for section in sections)

    table = Table(title="Result", show_header=False)
    table.add_column("key", style="bold")
    table.add_column("value")
    table.add_row("output directory", Text(str(output_dir.resolve())))
    table.add_row("sections", str(len(sections)))
    table.add_row("pages crawled", str(len(summaries)))
    table.add_row("pages linked", str(linked_pages))
    table.add_row("llms.txt bytes", str(len(llms_txt.encode("utf-8"))))
    if include_full:
        table.add_row("llms-full.txt bytes", str(len(llms_full_txt.encode("utf-8"))))
    table.add_row("warnings", str(len(warnings)))
    table.add_row("errors", str(len(errors)))
    console.print(table)

    if not llms_txt:
        console.print("[red]No llms.txt generated.[/red]")
        return 2

    console.print(f"\n[green]Wrote[/green] {escape(str(output_dir / 'llms.txt'))}")
    if not args.no_preview:
        lines = llms_txt.splitlines()
        console.print(Text("\n".join(lines[:40]), style="dim"))
        if len(lines) > 40:
            console.print("[dim]... (truncated; see file for full output)[/dim]")

    if llms_full_txt:
        console.print(f"[green]Wrote[/green] {escape(str(output_dir / 'llms-full.txt'))}")
    if errors:
        console.print(f"[red]{len(errors)} error(s); check the output above.[/red]")
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    console = Console(stderr=False)
    try:
        exit_code = asyncio.run(run(parse_args(argv), console))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        exit_code = 130
    except OSError as exc:
        Console(stderr=True).print(f"[red]Error:[/red] {escape(str(exc))}")
        exit_code = 1
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
