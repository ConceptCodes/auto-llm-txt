# auto-llm-txt

Generate `llms.txt` (and `llms-full.txt`) for any documentation site with LangGraph.

- Sitemap-first, BFS fallback; same-path-prefix scope
- HTML → clean markdown via `trafilatura` (fallback: BeautifulSoup)
- LLM summarization + curation + categorization (parallel via LangGraph **Send API**)
- Spec-compliant renderer — [llmstxt.org](https://llmstxt.org)

Structure mirrors [triage-bot](https://github.com/ConceptCodes/triage-bot): `src/auto_llm_txt/agent.py` owns the graph, `nodes/` are pure functions, `tools/` are IO helpers, `prompts.py` centralizes prompts.

## Quick start

```bash
uv sync
cp .env.example .env   # set OPENROUTER_API_KEY
uv run python main.py https://docs.example.com/ -o ./out
cat out/llms.txt
```

Options: `-o/--output`, `--max-pages`, `--max-depth`, `--model`.

Without `OPENROUTER_API_KEY`, LLM steps use scaffold heuristics so the graph still runs.

## LangGraph Studio

```bash
uv run langgraph up
# studio at http://localhost:8123
```

## Project structure

```
src/auto_llm_txt/
├── agent.py          # graph wiring + compilation
├── config.py         # pydantic-settings from .env
├── constants.py
├── state.py          # SiteState TypedDict + pydantic schemas
├── prompts.py
├── nodes/            # discover, fetch, extract, summarize, curate, categorize, compose, validate, write
│   ├── routing.py    # fan_out_summaries (Send API)
│   └── utils.py
└── tools/            # crawler, fetcher, extractor, renderer (pure & unit-testable)
main.py               # thin CLI entry
langgraph.json
```

## Milestones

1. **Scaffold** (current) — graph compiles, renders valid `llms.txt` from placeholder pages
2. Crawler + fetcher + extractor (real HTTP, no LLM)
3. LLM nodes (summarize/curate/categorize) with structured output
4. Compose + validate polish + `llms-full.txt`
5. Retries / rate limits / README polish
