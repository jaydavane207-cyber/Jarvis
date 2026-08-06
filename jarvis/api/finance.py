"""
jarvis/api/finance.py — Server-side Yahoo Finance proxy with TTL cache + batching.

Why server-side (#2 / #6)?
──────────────────────────
• Direct browser fetch to query1.finance.yahoo.com fails with CORS errors.
• Firing one fetch() per stock on the frontend = N sequential/parallel round
  trips from the browser; instead we parallelise them server-side with
  asyncio.gather() and return a single JSON response.
• In-memory TTL cache (5 min) prevents re-hitting Yahoo Finance on every
  page reload within that window.

Endpoints
─────────
  GET /api/finance/chart/{ticker}          — single ticker (e.g. RELIANCE.NS)
  GET /api/finance/batch?tickers=T1,T2,...  — parallelised batch
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter, Query, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

# ── TTL cache ─────────────────────────────────────────────────────────────────
# Simple dict: {ticker: (fetched_at_epoch, data_or_None)}
# Each worker process maintains its own cache independently.
# Cache misses in one worker just trigger a fresh Yahoo Finance fetch —
# no correctness issue, only minor extra load (acceptable for 2 workers).

_CACHE_TTL_SECONDS = 300  # 5 minutes
_cache: dict[str, tuple[float, Any]] = {}


def _get_cached(ticker: str) -> tuple[bool, Any]:
    """Return (hit, data). hit=False if missing or expired."""
    entry = _cache.get(ticker)
    if entry is None:
        return False, None
    fetched_at, data = entry
    if time.monotonic() - fetched_at > _CACHE_TTL_SECONDS:
        del _cache[ticker]
        return False, None
    return True, data


def _set_cached(ticker: str, data: Any) -> None:
    _cache[ticker] = (time.monotonic(), data)


# ── Yahoo Finance fetcher ──────────────────────────────────────────────────────

_YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
_YF_PARAMS = {"interval": "1d", "range": "1mo"}
# Realistic browser headers to avoid 429 / 403 from Yahoo
_YF_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
}
_HTTP_TIMEOUT = 8.0  # seconds per request


async def _fetch_ticker(client: httpx.AsyncClient, ticker: str) -> Any:
    """
    Fetch one ticker from Yahoo Finance (server-to-server, no CORS issue).
    Returns the parsed JSON payload, or None on any error.
    Per-ticker errors are isolated so they don't fail the whole batch.
    """
    # 1. Check cache first
    hit, cached_data = _get_cached(ticker)
    if hit:
        logger.debug("FINANCE CACHE HIT  | %s", ticker)
        return cached_data

    logger.debug("FINANCE CACHE MISS | %s  -- fetching from Yahoo Finance", ticker)
    try:
        url = _YF_URL.format(ticker=ticker)
        resp = await client.get(
            url,
            params=_YF_PARAMS,
            headers=_YF_HEADERS,
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
        # Validate minimal structure before caching
        result = data.get("chart", {}).get("result")
        if not result:
            logger.warning("FINANCE | %s -- unexpected payload (no chart.result)", ticker)
            return None
        _set_cached(ticker, data)
        return data
    except httpx.HTTPStatusError as exc:
        logger.error("FINANCE | %s -- HTTP %s: %s", ticker, exc.response.status_code, exc)
    except httpx.TimeoutException:
        logger.error("FINANCE | %s -- request timed out after %.1f s", ticker, _HTTP_TIMEOUT)
    except Exception as exc:
        logger.error("FINANCE | %s -- fetch failed: %s", ticker, exc)
    return None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/chart/{ticker}", summary="Single-ticker chart data (server-side proxy)")
async def finance_chart(ticker: str) -> dict:
    """
    Fetch Yahoo Finance chart data for *ticker* (e.g. ``RELIANCE.NS``).
    Cached for 5 minutes per ticker.

    Returns the raw Yahoo Finance v8/chart JSON, or raises 502 on failure.
    """
    async with httpx.AsyncClient() as client:
        data = await _fetch_ticker(client, ticker)

    if data is None:
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch data for ticker {ticker!r} from Yahoo Finance.",
        )
    return data


@router.get("/batch", summary="Batch-fetch multiple tickers in parallel (server-side proxy)")
async def finance_batch(
    tickers: str = Query(
        ...,
        description="Comma-separated ticker symbols, e.g. RELIANCE.NS,TCS.NS,INFY.NS",
        example="RELIANCE.NS,TCS.NS,INFY.NS",
    ),
) -> dict[str, Any]:
    """
    Fetch Yahoo Finance chart data for all ``tickers`` in **one round-trip**
    from the frontend's perspective.

    Internally, all Yahoo Finance fetches run concurrently via
    ``asyncio.gather()``, so N tickers take roughly the time of one slow
    request rather than N sequential requests.

    Per-ticker errors return ``null`` for that ticker only -- the rest of
    the batch is still returned successfully.

    Cache: each ticker is cached for 5 minutes independently.
    A cache hit is served immediately without any network I/O.
    """
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="No tickers provided.")
    if len(ticker_list) > 20:
        raise HTTPException(
            status_code=400,
            detail="Batch size limited to 20 tickers per request.",
        )

    async with httpx.AsyncClient() as client:
        # All fetches run concurrently; errors already caught inside _fetch_ticker
        results = await asyncio.gather(
            *[_fetch_ticker(client, t) for t in ticker_list],
        )

    payload: dict[str, Any] = {}
    for ticker, data in zip(ticker_list, results):
        payload[ticker] = data  # None if the fetch failed

    cache_hits = sum(1 for t in ticker_list if _get_cached(t)[0])
    logger.info(
        "FINANCE BATCH | %d tickers requested | %d cache hits | %d fetched from Yahoo",
        len(ticker_list), cache_hits, len(ticker_list) - cache_hits,
    )
    return payload


@router.get("/cache/status", summary="Finance cache diagnostics")
async def finance_cache_status() -> dict:
    """Return current cache state for monitoring."""
    now = time.monotonic()
    return {
        "cached_tickers": len(_cache),
        "ttl_seconds": _CACHE_TTL_SECONDS,
        "entries": [
            {
                "ticker": t,
                "age_seconds": round(now - ts, 1),
                "expires_in_seconds": round(_CACHE_TTL_SECONDS - (now - ts), 1),
            }
            for t, (ts, _) in _cache.items()
        ],
    }
