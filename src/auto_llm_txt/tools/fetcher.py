"""Fetcher — thin httpx wrappers with sensible defaults."""

from __future__ import annotations

import httpx


DEFAULT_HEADERS = {
    "User-Agent": "auto-llm-txt/0.1 (+https://github.com/ConceptCodes/auto-llm-txt)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def build_client(timeout: int = 15) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
    )


async def fetch_text(client: httpx.AsyncClient, url: str) -> tuple[str | None, str | None]:
    """Fetch url; return (text, error). error is None on success."""
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype and "xml" not in ctype and "text" not in ctype:
            return None, f"unsupported content-type: {ctype}"
        return resp.text, None
    except httpx.HTTPStatusError as e:
        return None, f"HTTP {e.response.status_code}"
    except httpx.RequestError as e:
        return None, str(e)
    except Exception as e:  # noqa: BLE001
        return None, str(e)
