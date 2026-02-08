"""
Main analysis pipeline.

Orchestrates data fetching → indicators → patterns → levels → trend →
money flow → signal scoring → scenario building → formatting.
"""
import asyncio
import logging
from typing import Dict

from crypto_analyzer import fetch_multi_tf
from indicators import compute_all
from patterns import detect_patterns
from analysis_components import (
    find_key_levels,
    analyze_trend_mtf,
    analyze_money_flow,
    build_scenarios,
    get_session_context,
)
from signal_engine import compute_signal
from formatter import format_analysis

logger = logging.getLogger(__name__)


async def analyze_coin(symbol: str, timeframe: str = "15m") -> str:
    """
    Full analysis for a symbol.

    1. Fetch multi-TF data (primary + 1h + 4h in parallel)
    2. Compute indicators on the primary timeframe
    3. Detect candlestick patterns
    4. Find support / resistance levels
    5. Multi-TF trend analysis
    6. Money-flow analysis
    7. Composite signal scoring
    8. Build data-driven scenarios
    9. Get session context
    10. Format everything into a rich Telegram message
    """
    # 1 — Data
    data = await fetch_multi_tf(symbol, timeframe)
    ohlcv = data["primary"]
    ohlcv_1h = data["1h"]
    ohlcv_4h = data["4h"]

    # 2 — Indicators
    indicators = compute_all(ohlcv)

    # 3 — Candle patterns
    patterns = detect_patterns(ohlcv)

    # 4 — Levels
    levels = find_key_levels(ohlcv)

    # 5 — Multi-TF trend
    trend = analyze_trend_mtf(ohlcv, ohlcv_1h, ohlcv_4h)

    # 6 — Money flow
    flow = analyze_money_flow(ohlcv, ohlcv_1h, ohlcv_4h)

    # 7 — Signal score
    signal = compute_signal(indicators, levels, trend, flow, patterns)

    # 8 — Scenarios
    scenarios = build_scenarios(indicators, levels, trend, flow, patterns)

    # 9 — Session
    session = get_session_context()

    # 10 — Format
    return format_analysis(
        symbol, timeframe, indicators, levels, trend, flow,
        scenarios, patterns, signal, session,
    )


async def analyze_coin_raw(symbol: str, timeframe: str = "15m") -> Dict:
    """Return raw analysis data (for programmatic use)."""
    data = await fetch_multi_tf(symbol, timeframe)
    ohlcv = data["primary"]
    ohlcv_1h = data["1h"]
    ohlcv_4h = data["4h"]

    indicators = compute_all(ohlcv)
    patterns = detect_patterns(ohlcv)
    levels = find_key_levels(ohlcv)
    trend = analyze_trend_mtf(ohlcv, ohlcv_1h, ohlcv_4h)
    flow = analyze_money_flow(ohlcv, ohlcv_1h, ohlcv_4h)
    signal = compute_signal(indicators, levels, trend, flow, patterns)
    scenarios = build_scenarios(indicators, levels, trend, flow, patterns)
    session = get_session_context()

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "indicators": indicators,
        "patterns": patterns,
        "levels": levels,
        "trend": trend,
        "flow": flow,
        "signal": signal,
        "scenarios": scenarios,
        "session": session,
    }


if __name__ == "__main__":
    result = asyncio.run(analyze_coin("BTC/USDT", "15m"))
    print(result)
