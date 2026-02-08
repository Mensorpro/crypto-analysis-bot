"""
Signal scoring engine.

Aggregates all indicators, patterns, multi-TF trend, money flow, and levels
into a single composite score from -100 (max bearish) to +100 (max bullish),
plus a human-readable verdict and confidence level.
"""
from typing import Dict, List
import config


def _clamp(val: float, lo: float = -100, hi: float = 100) -> float:
    return max(lo, min(hi, val))


def score_trend(trend: Dict) -> float:
    """Score from multi-TF trend analysis (-25 … +25)."""
    mapping = {
        "bullish": 25,
        "lean_bullish": 12,
        "neutral": 0,
        "lean_bearish": -12,
        "bearish": -25,
    }
    base = mapping.get(trend["overall"], 0)

    # Bonus if all TFs agree
    dirs = [trend["primary"]["direction"], trend["tf_1h"]["direction"], trend["tf_4h"]["direction"]]
    if all("up" in d for d in dirs):
        base = min(base + 5, 25)
    elif all("down" in d for d in dirs):
        base = max(base - 5, -25)

    return base


def score_momentum(indicators: Dict) -> float:
    """Score from RSI + MACD + Stochastic (-25 … +25)."""
    s = 0.0
    rsi = indicators["rsi"]

    # RSI
    if rsi > 70:
        s -= 8  # overbought = bearish pressure
    elif rsi > 55:
        s += 6
    elif rsi < 30:
        s += 8  # oversold = bullish reversal potential
    elif rsi < 45:
        s -= 6

    # MACD histogram
    hist = indicators["macd_hist"]
    if hist > 0:
        s += min(hist * 500, 8)  # cap contribution
    else:
        s += max(hist * 500, -8)

    # Stochastic
    k, d = indicators["stoch_k"], indicators["stoch_d"]
    if k > 80 and d > 80:
        s -= 4
    elif k < 20 and d < 20:
        s += 4
    elif k > d:
        s += 2
    else:
        s -= 2

    return _clamp(s, -25, 25)


def score_volume(flow: Dict) -> float:
    """Score from volume / money flow (-20 … +20)."""
    s = 0.0
    mapping = {
        "strong_inflow": 18,
        "inflow": 10,
        "balanced": 0,
        "outflow": -10,
        "strong_outflow": -18,
    }
    s += mapping.get(flow["flow"], 0)

    if flow["vol_spike"]:
        # Spike amplifies current direction
        if flow["buy_pct"] > 55:
            s += 2
        elif flow["buy_pct"] < 45:
            s -= 2

    return _clamp(s, -20, 20)


def score_levels(indicators: Dict, levels: Dict) -> float:
    """Score based on price position relative to key levels (-15 … +15)."""
    s = 0.0

    # Price vs VWAP
    if indicators["price_vs_vwap"] > 0:
        s += 4
    else:
        s -= 4

    # Bollinger position
    pct_b = indicators["bb_pct_b"]
    if pct_b > 0.9:
        s -= 4  # near upper band = stretched
    elif pct_b < 0.1:
        s += 4  # near lower band = bounce zone
    elif pct_b > 0.5:
        s += 2
    else:
        s -= 2

    # Range position
    rp = levels["range_position"]
    if rp > 85:
        s -= 4  # near top of range
    elif rp < 15:
        s += 4  # near bottom of range

    return _clamp(s, -15, 15)


def score_patterns(patterns: List[Dict]) -> float:
    """Score from detected candlestick patterns (-15 … +15)."""
    s = 0.0
    for p in patterns:
        weight = p["strength"]
        # Recent patterns matter more
        recency = max(1, 5 - p.get("bars_ago", 0))
        contribution = weight * recency * 0.8
        if p["bias"] == "bullish":
            s += contribution
        elif p["bias"] == "bearish":
            s -= contribution
    return _clamp(s, -15, 15)


def compute_signal(indicators: Dict, levels: Dict, trend: Dict,
                   flow: Dict, patterns: List[Dict]) -> Dict:
    """
    Master scoring function.

    Returns:
        score: -100 … +100
        verdict: human-readable (e.g. "Strong Buy", "Sell", "Neutral")
        confidence: 0-100%
        breakdown: per-category scores
    """
    t = score_trend(trend)
    m = score_momentum(indicators)
    v = score_volume(flow)
    l = score_levels(indicators, levels)
    p = score_patterns(patterns)

    raw = t + m + v + l + p
    score = _clamp(raw, -100, 100)

    # Confidence = how much the sub-scores agree
    signs = [t, m, v, l, p]
    positive = sum(1 for x in signs if x > 2)
    negative = sum(1 for x in signs if x < -2)
    agreement = max(positive, negative)
    confidence = min(100, agreement * 20 + abs(score) // 2)

    # Verdict
    if score >= 60:
        verdict = "Strong Buy"
        emoji = "🟢🟢🟢"
    elif score >= 30:
        verdict = "Buy"
        emoji = "🟢🟢"
    elif score >= 10:
        verdict = "Lean Bullish"
        emoji = "🟢"
    elif score <= -60:
        verdict = "Strong Sell"
        emoji = "🔴🔴🔴"
    elif score <= -30:
        verdict = "Sell"
        emoji = "🔴🔴"
    elif score <= -10:
        verdict = "Lean Bearish"
        emoji = "🔴"
    else:
        verdict = "Neutral"
        emoji = "🟡"

    return {
        "score": round(score, 1),
        "verdict": verdict,
        "emoji": emoji,
        "confidence": round(confidence),
        "breakdown": {
            "trend": round(t, 1),
            "momentum": round(m, 1),
            "volume": round(v, 1),
            "levels": round(l, 1),
            "patterns": round(p, 1),
        },
    }
