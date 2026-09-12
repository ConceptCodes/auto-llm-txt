"""Project entry point for the LangGraph Studio development server."""

from __future__ import annotations

from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> None:
    """Launch ``langgraph dev`` and forward any command-line options."""
    from langgraph_cli.cli import dev

    dev.main(
        args=list(argv) if argv is not None else None,
        prog_name="auto-llm-txt-studio",
    )


if __name__ == "__main__":
    main()
