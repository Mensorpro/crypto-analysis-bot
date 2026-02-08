"""
Core data-fetching layer.

This module is intentionally thin — it just fetches OHLCV data and hands it off
to the indicator / analysis modules.  All heavy calculation lives in
indicators.py, patterns.py, analysis_components.py, and signal_engine.py.
"""
import asyncio
from typing import Dict
from multi_exchange_client import MultiExchangeClient
import config


async def fetch_ohlcv(symbol: str, timeframe: str,
                      limit: int = None) -> Dict:
    """Fetch OHLCV data through the singleton exchange client."""
    limit = limit or config.DEFAULT_LOOKBACK
    client = MultiExchangeClient()          # returns singleton
    return await client.fetch_ohlcv(symbol, timeframe, limit)


async def fetch_multi_tf(symbol: str, primary_tf: str) -> Dict:
    """
    Fetch primary + 1h + 4h data in parallel for multi-TF analysis.
    Returns {"primary": ..., "1h": ..., "4h": ...}.
    """
    primary, h1, h4 = await asyncio.gather(
        fetch_ohlcv(symbol, primary_tf),
        fetch_ohlcv(symbol, "1h"),
        fetch_ohlcv(symbol, "4h"),
    )
    return {"primary": primary, "1h": h1, "4h": h4}

