"""
Analysis components — levels, money-flow, multi-TF trend, scenarios.
Completely rewritten to use real indicators from indicators.py.
"""
from typing import Dict, List, Tuple
from datetime import datetime
import pytz

import config
from indicators import (
    sma_last, ema_last, rsi_last, macd_last, bb_last,
    atr_last, stochastic_last, adx, obv_trend,
    volume_ratio, is_volume_spike, volume_trend, vwap, compute_all,
)
from patterns import detect_patterns


# ═══════════════════════════════════════════════════════════════════════════
# Support / Resistance
# ═══════════════════════════════════════════════════════════════════════════

def _cluster_levels(prices: List[float], tolerance: float) -> List[Tuple[float, int]]:
    """Return (level_price, touch_count) clusters."""
    if not prices:
        return []
    sorted_p = sorted(prices)
    clusters: List[Tuple[float, int]] = []
    i = 0
    while i < len(sorted_p):
        group = [sorted_p[i]]
        j = i + 1
        while j < len(sorted_p) and (sorted_p[j] - sorted_p[i]) / sorted_p[i] <= tolerance:
            group.append(sorted_p[j])
            j += 1
        if len(group) >= config.MIN_TOUCHES:
            clusters.append((sum(group) / len(group), len(group)))
        i = j if j > i + 1 else i + 1
    return clusters


def find_key_levels(ohlcv: Dict, lookback: int = None) -> Dict:
    """
    Identify support / resistance with touch counts, and
    classify levels by proximity to current price.
    """
    lookback = lookback or config.LEVEL_LOOKBACK
    highs = ohlcv["high"][-lookback:]
    lows = ohlcv["low"][-lookback:]
    closes = ohlcv["close"][-lookback:]
    volumes = ohlcv["volume"][-lookback:]
    current = closes[-1]

    tol = config.CLUSTER_TOLERANCE

    # Resistance from highs; support from lows
    res_clusters = _cluster_levels(highs, tol)
    sup_clusters = _cluster_levels(lows, tol)

    # Sort by distance from current price
    resistances = sorted(
        [(lvl, tc) for lvl, tc in res_clusters if lvl > current * (1 + tol * 0.5)],
        key=lambda x: x[0],
    )
    supports = sorted(
        [(lvl, tc) for lvl, tc in sup_clusters if lvl < current * (1 - tol * 0.5)],
        key=lambda x: x[0],
        reverse=True,
    )

    # Nearest + second levels
    r1 = resistances[0] if resistances else (max(highs) * 1.02, 0)
    r2 = resistances[1] if len(resistances) > 1 else (r1[0] * 1.03, 0)
    s1 = supports[0] if supports else (min(lows) * 0.98, 0)
    s2 = supports[1] if len(supports) > 1 else (s1[0] * 0.97, 0)

    _atr = atr_last(ohlcv["high"], ohlcv["low"], ohlcv["close"])

    return {
        "current": round(current, 6),
        "r1": round(r1[0], 6),
        "r1_touches": r1[1],
        "r2": round(r2[0], 6),
        "r2_touches": r2[1],
        "s1": round(s1[0], 6),
        "s1_touches": s1[1],
        "s2": round(s2[0], 6),
        "s2_touches": s2[1],
        "atr": round(_atr, 6),
        "atr_pct": round(_atr / current * 100, 2) if current else 0,
        "range_high": round(max(highs), 6),
        "range_low": round(min(lows), 6),
        "range_position": round((current - min(lows)) / (max(highs) - min(lows)) * 100, 1)
                          if max(highs) != min(lows) else 50.0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Multi-timeframe trend analysis
# ═══════════════════════════════════════════════════════════════════════════

def analyze_trend_mtf(ohlcv: Dict, ohlcv_1h: Dict, ohlcv_4h: Dict) -> Dict:
    """
    Comprehensive trend analysis across 3 time-frames.
    Returns direction, strength, and detailed per-TF data.
    """

    def _single_tf(data: Dict, label: str) -> Dict:
        c = data["close"]
        h = data["high"]
        l = data["low"]
        current = c[-1]

        sma9 = sma_last(c, config.SMA_FAST)
        sma21 = sma_last(c, config.SMA_MID)
        sma50 = sma_last(c, config.SMA_SLOW)
        _rsi = rsi_last(c)
        _macd = macd_last(c)
        _adx = adx(h, l, c)

        # Trend direction
        if sma9 > sma21 > sma50 and current > sma9:
            direction = "strong_up"
        elif sma9 > sma21 and current > sma21:
            direction = "up"
        elif sma9 < sma21 < sma50 and current < sma9:
            direction = "strong_down"
        elif sma9 < sma21 and current < sma21:
            direction = "down"
        else:
            direction = "sideways"

        # Momentum qualifier
        if _rsi > 70:
            momentum = "overbought"
        elif _rsi < 30:
            momentum = "oversold"
        elif _rsi > 55:
            momentum = "bullish"
        elif _rsi < 45:
            momentum = "bearish"
        else:
            momentum = "neutral"

        return {
            "tf": label,
            "direction": direction,
            "momentum": momentum,
            "rsi": _rsi,
            "macd_hist": _macd["histogram"],
            "adx": _adx["adx"],
            "trend_strength": "strong" if _adx["adx"] > 25 else "weak",
        }

    tf_primary = _single_tf(ohlcv, "primary")
    tf_1h = _single_tf(ohlcv_1h, "1h")
    tf_4h = _single_tf(ohlcv_4h, "4h")

    # Confluence score: +1 for each bullish signal, -1 for bearish
    score = 0
    for tf in (tf_primary, tf_1h, tf_4h):
        if "up" in tf["direction"]:
            score += 1
        elif "down" in tf["direction"]:
            score -= 1
        if tf["momentum"] in ("bullish", "overbought"):
            score += 0.5
        elif tf["momentum"] in ("bearish", "oversold"):
            score -= 0.5

    if score >= 2:
        overall = "bullish"
    elif score <= -2:
        overall = "bearish"
    elif score > 0:
        overall = "lean_bullish"
    elif score < 0:
        overall = "lean_bearish"
    else:
        overall = "neutral"

    return {
        "overall": overall,
        "confluence_score": round(score, 1),
        "primary": tf_primary,
        "tf_1h": tf_1h,
        "tf_4h": tf_4h,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Money flow / Volume analysis
# ═══════════════════════════════════════════════════════════════════════════

def analyze_money_flow(ohlcv: Dict, ohlcv_1h: Dict, ohlcv_4h: Dict) -> Dict:
    """Real money-flow analysis using volume, OBV, VWAP."""
    c = ohlcv["close"]
    h = ohlcv["high"]
    l = ohlcv["low"]
    v = ohlcv["volume"]
    current = c[-1]

    _vwap = vwap(h, l, c, v)
    _obv = obv_trend(c, v)
    _vol_ratio = volume_ratio(v)
    _vol_trend = volume_trend(v)
    _vol_spike = is_volume_spike(v)

    # Price vs VWAP tells us if buyers or sellers are in control
    price_vs_vwap = "above" if current > _vwap else "below"

    # Buying / selling pressure from recent candles
    buy_candles = sum(1 for i in range(-10, 0) if c[i] > ohlcv["open"][i])
    sell_candles = 10 - buy_candles
    buy_volume = sum(v[i] for i in range(-10, 0) if c[i] > ohlcv["open"][i])
    sell_volume = sum(v[i] for i in range(-10, 0) if c[i] <= ohlcv["open"][i])
    total_recent_vol = buy_volume + sell_volume

    if total_recent_vol > 0:
        buy_pct = round(buy_volume / total_recent_vol * 100, 1)
    else:
        buy_pct = 50.0

    # Net flow interpretation
    if buy_pct > 60 and _obv == "rising":
        flow = "strong_inflow"
    elif buy_pct > 55:
        flow = "inflow"
    elif buy_pct < 40 and _obv == "falling":
        flow = "strong_outflow"
    elif buy_pct < 45:
        flow = "outflow"
    else:
        flow = "balanced"

    return {
        "vwap": round(_vwap, 6),
        "price_vs_vwap": price_vs_vwap,
        "obv_trend": _obv,
        "vol_ratio": round(_vol_ratio, 2),
        "vol_spike": _vol_spike,
        "vol_trend": _vol_trend,
        "buy_pct": buy_pct,
        "sell_pct": round(100 - buy_pct, 1),
        "buy_candles": buy_candles,
        "sell_candles": sell_candles,
        "flow": flow,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Scenario builder — data-driven
# ═══════════════════════════════════════════════════════════════════════════

def build_scenarios(indicators: Dict, levels: Dict, trend: Dict,
                    flow: Dict, patterns: List[Dict]) -> List[Dict]:
    """Build IF/THEN scenarios grounded in indicator data."""
    current = levels["current"]
    r1 = levels["r1"]
    s1 = levels["s1"]
    s2 = levels["s2"]
    atr_val = levels["atr"]
    rsi_val = indicators["rsi"]

    scenarios: List[Dict] = []

    # ---------- Bullish scenario ----------
    bull_trigger_parts = []
    bull_confluence = 0

    if rsi_val < 45:
        bull_trigger_parts.append(f"RSI ({rsi_val}) turns up from oversold zone")
        bull_confluence += 1
    if flow["price_vs_vwap"] == "below":
        bull_trigger_parts.append("price reclaims VWAP")
        bull_confluence += 1
    if indicators["macd_hist"] < 0:
        bull_trigger_parts.append("MACD histogram flips positive")
        bull_confluence += 1

    bull_target1 = round(current + atr_val * 1.5, 6)
    bull_target2 = r1
    bull_stop = round(current - atr_val * 1.0, 6)
    bull_rr = round((bull_target2 - current) / (current - bull_stop), 1) if current != bull_stop else 0

    prob = "high" if bull_confluence >= 2 and "bullish" in trend["overall"] else \
           "medium" if bull_confluence >= 1 else "low"

    scenarios.append({
        "label": "BULLISH",
        "emoji": "🟢",
        "trigger": " + ".join(bull_trigger_parts) if bull_trigger_parts else f"price holds above ${s1} and reclaims ${round(current + atr_val * 0.5, 2)}",
        "target": f"${bull_target1} → ${bull_target2}",
        "stop": f"${bull_stop}",
        "rr_ratio": bull_rr,
        "probability": prob,
        "confluence": bull_confluence,
    })

    # ---------- Bearish scenario ----------
    bear_trigger_parts = []
    bear_confluence = 0

    if rsi_val > 55:
        bear_trigger_parts.append(f"RSI ({rsi_val}) rolls over from overbought zone")
        bear_confluence += 1
    if flow["price_vs_vwap"] == "above":
        bear_trigger_parts.append("price loses VWAP")
        bear_confluence += 1
    if indicators["macd_hist"] > 0:
        bear_trigger_parts.append("MACD histogram flips negative")
        bear_confluence += 1

    bear_target1 = round(current - atr_val * 1.5, 6)
    bear_target2 = s1
    bear_stop = round(current + atr_val * 1.0, 6)
    bear_rr = round(abs(current - bear_target2) / (bear_stop - current), 1) if bear_stop != current else 0

    prob_bear = "high" if bear_confluence >= 2 and "bearish" in trend["overall"] else \
                "medium" if bear_confluence >= 1 else "low"

    scenarios.append({
        "label": "BEARISH",
        "emoji": "🔴",
        "trigger": " + ".join(bear_trigger_parts) if bear_trigger_parts else f"price breaks below ${s1}",
        "target": f"${bear_target1} → ${bear_target2}",
        "stop": f"${bear_stop}",
        "rr_ratio": bear_rr,
        "probability": prob_bear,
        "confluence": bear_confluence,
    })

    # ---------- Range / chop scenario ----------
    scenarios.append({
        "label": "RANGE-BOUND",
        "emoji": "🟡",
        "trigger": "price stays between S1 and R1 with low ADX",
        "target": f"Fade extremes: buy near ${s1}, sell near ${r1}",
        "stop": f"Outside range by 1 ATR (${round(s1 - atr_val, 2)} / ${round(r1 + atr_val, 2)})",
        "rr_ratio": round((r1 - s1) / atr_val, 1) if atr_val else 0,
        "probability": "high" if indicators["adx"] < 20 else "medium" if indicators["adx"] < 25 else "low",
        "confluence": 1 if indicators["adx"] < 25 else 0,
    })

    return scenarios


# ═══════════════════════════════════════════════════════════════════════════
# Session context (improved)
# ═══════════════════════════════════════════════════════════════════════════

def get_session_context() -> Dict:
    """Detailed session context with expected volatility."""
    now = datetime.now(pytz.UTC)
    hour = now.hour

    sessions = []
    if 0 <= hour < 9:
        sessions.append("Asia")
    if 7 <= hour < 16:
        sessions.append("London")
    if 13 <= hour < 22:
        sessions.append("New York")

    if not sessions:
        sessions.append("Off-hours")

    # Overlap = higher volatility
    overlap = len(sessions) > 1
    active_label = " + ".join(sessions)

    # Hours until next major session
    if hour < 7:
        next_session = "London"
        hours_until = 7 - hour
    elif hour < 13:
        next_session = "New York"
        hours_until = 13 - hour
    elif hour < 22:
        next_session = "Asia (next day)"
        hours_until = 24 - hour
    else:
        next_session = "Asia"
        hours_until = 24 - hour

    if overlap:
        volatility = "high"
        note = "Session overlap — expect increased volatility and volume"
    elif "Off-hours" in sessions:
        volatility = "low"
        note = "Between sessions — thin liquidity, watch for fakeouts"
    elif "Asia" in sessions and not overlap:
        volatility = "low-medium"
        note = "Asia session — typically lower volume for crypto"
    else:
        volatility = "medium-high"
        note = f"{active_label} session active"

    return {
        "active": active_label,
        "overlap": overlap,
        "volatility": volatility,
        "note": note,
        "next_session": next_session,
        "hours_until_next": hours_until,
        "utc_hour": hour,
    }
