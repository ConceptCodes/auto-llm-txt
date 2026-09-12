"""Graph wiring — single place where the LangGraph StateGraph is built."""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from auto_llm_txt.nodes import (
    categorize,
    compose,
    curate,
    discover,
    extract,
    fan_out_summaries,
    fetch,
    summarize_page,
    validate,
    write,
)
from auto_llm_txt.state import SiteState


def build_graph() -> StateGraph:
    builder = StateGraph(SiteState)

    # RetryPolicy for transient network and LLM failures
    io_retry_policy = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0)

    builder.add_node("discover", discover, retry_policy=io_retry_policy)
    builder.add_node("fetch", fetch, retry_policy=io_retry_policy)
    builder.add_node("extract", extract)
    builder.add_node("fan_out_summaries", fan_out_summaries)
    builder.add_node("summarize_page", summarize_page, retry_policy=io_retry_policy)
    builder.add_node("curate", curate, retry_policy=io_retry_policy)
    builder.add_node("categorize", categorize, retry_policy=io_retry_policy)
    builder.add_node("compose", compose)
    builder.add_node("validate", validate)
    builder.add_node("write", write)

    builder.add_edge(START, "discover")
    builder.add_edge("discover", "fetch")
    builder.add_edge("fetch", "extract")
    builder.add_edge("extract", "fan_out_summaries")

    # Each summarize_page branch converges on curate (add reducer merges summaries)
    builder.add_edge("summarize_page", "curate")

    builder.add_edge("curate", "categorize")
    builder.add_edge("categorize", "compose")
    builder.add_edge("compose", "validate")
    builder.add_edge("validate", "write")
    builder.add_edge("write", END)

    return builder


# Uncompiled StateGraph builder
graph_uncompiled = build_graph()

_graph = None


def get_graph(checkpointer: BaseCheckpointSaver | None = None):
    global _graph
    if _graph is not None and checkpointer is None:
        return _graph

    builder = build_graph()
    if checkpointer is None:
        # Allow our pydantic state models without msgpack warnings (future strict mode).
        try:
            from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

            serde = JsonPlusSerializer(
                allowed_msgpack_modules=[
                    ("auto_llm_txt.state", "RawPage"),
                    ("auto_llm_txt.state", "Page"),
                    ("auto_llm_txt.state", "PageSummary"),
                    ("auto_llm_txt.state", "Section"),
                    ("auto_llm_txt.state", "FetchError"),
                    ("auto_llm_txt.constants", "PageQuality"),
                ]
            )
            checkpointer = InMemorySaver(serde=serde)
        except Exception:  # noqa: BLE001
            checkpointer = InMemorySaver()

    compiled = builder.compile(checkpointer=checkpointer)
    if _graph is None:
        _graph = compiled
    return compiled


# The CLI owns this checkpointer so it can inspect the final state after streaming.
graph = get_graph()

# LangGraph API and Studio provide persistence and require an uncheckpointed graph.
studio_graph = build_graph().compile()
