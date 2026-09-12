from __future__ import annotations

from auto_llm_txt import studio
from auto_llm_txt.agent import studio_graph


def test_studio_forwards_arguments(monkeypatch):
    received = {}

    def fake_main(*, args, prog_name):
        received.update(args=args, prog_name=prog_name)

    monkeypatch.setattr("langgraph_cli.cli.dev.main", fake_main)

    studio.main(["--port", "8000", "--no-browser"])

    assert received == {
        "args": ["--port", "8000", "--no-browser"],
        "prog_name": "auto-llm-txt-studio",
    }


def test_studio_graph_defers_persistence_to_langgraph_api():
    assert studio_graph.checkpointer is None
