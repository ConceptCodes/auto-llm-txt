"""Graph wiring — single place where the LangGraph StateGraph is built."""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

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

    builder.add_node("discover", discover)
    builder.add_node("fetch", fetch)
    builder.add_node("extract", extract)
    builder.add_node("summarize_page", summarize_page)
    builder.add_node("curate", curate)
    builder.add_node("categorize", categorize)
    builder.add_node("compose", compose)
    builder.add_node("validate", validate)
    builder.add_node("write", write)

    builder.add_edge(START, "discover")
    builder.add_edge("discover", "fetch")
    builder.add_edge("fetch", "extract")

    # Fan-out: one parallel summarize_page per Page via Send API
    builder.add_conditional_edges("extract", fan_out_summaries, ["summarize_page"])

    # Each summarize_page branch converges on curate (add reducer merges summaries)
    builder.add_edge("summarize_page", "curate")

    builder.add_edge("curate", "categorize")
    builder.add_edge("categorize", "compose")
    builder.add_edge("compose", "validate")
    builder.add_edge("validate", "write")
    builder.add_edge("write", END)

    return builder


# LangGraph Studio / CLI expects a prebuilt but uncompiled graph variable.
graph_uncompiled = build_graph()

_graph = None


def get_graph():
    global _graph
    if _graph is not None:
        return _graph

    builder = build_graph()
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
    except Exception:
        checkpointer = InMemorySaver()
    _graph = builder.compile(checkpointer=checkpointer)
    return _graph


# Compiled graph for `langgraph up` / direct import
graph = get_graph()
