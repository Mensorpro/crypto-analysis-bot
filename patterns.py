"""
Candlestick pattern recognition.

Each detector returns a dict with:
  name      – human-readable pattern name
  bias      – "bullish" | "bearish" | "neutral"
  strength  – 1 (weak) … 3 (strong)
  index     – bar index where detected

We scan the last N candles and return all detected patterns sorted by
recency (most recent first).
"""
from typing import Dict, List, Optional


def _body(o: float, c: float) -> float:
    return abs(c - o)


def _upper_shadow(h: float, o: float, c: float) -> float:
    return h - max(o, c)


def _lower_shadow(l: float, o: float, c: float) -> float:
    return min(o, c) - l


def _range(h: float, l: float) -> float:
    return h - l


def _is_bullish(o: float, c: float) -> bool:
    return c > o


def _is_bearish(o: float, c: float) -> bool:
    return o > c


# ═══════════════════════════════════════════════════════════════════════════
# Individual pattern detectors
# ═══════════════════════════════════════════════════════════════════════════

def _detect_doji(o, h, l, c, i) -> Optional[Dict]:
    """Doji — body is < 10% of total range."""
    r = _range(h, l)
    if r == 0:
        return None
    if _body(o, c) / r < 0.10:
        return {"name": "Doji", "bias": "neutral", "strength": 1, "index": i}
    return None


def _detect_hammer(opens, highs, lows, closes, i) -> Optional[Dict]:
    """Hammer / Hanging Man — small body at top, long lower shadow."""
    o, h, l, c = opens[i], highs[i], lows[i], closes[i]
    r = _range(h, l)
    if r == 0:
        return None
    body = _body(o, c)
    ls = _lower_shadow(l, o, c)
    us = _upper_shadow(h, o, c)
    if ls >= body * 2 and us < body * 0.5 and body / r < 0.35:
        # Bullish hammer in downtrend, bearish hanging man in uptrend
        if i >= 3 and closes[i] < closes[i - 3]:
            return {"name": "Hammer", "bias": "bullish", "strength": 2, "index": i}
        elif i >= 3 and closes[i] > closes[i - 3]:
            return {"name": "Hanging Man", "bias": "bearish", "strength": 2, "index": i}
    return None


def _detect_shooting_star(opens, highs, lows, closes, i) -> Optional[Dict]:
    """Shooting Star / Inverted Hammer — small body at bottom, long upper wick."""
    o, h, l, c = opens[i], highs[i], lows[i], closes[i]
    r = _range(h, l)
    if r == 0:
        return None
    body = _body(o, c)
    us = _upper_shadow(h, o, c)
    ls = _lower_shadow(l, o, c)
    if us >= body * 2 and ls < body * 0.5 and body / r < 0.35:
        if i >= 3 and closes[i] > closes[i - 3]:
            return {"name": "Shooting Star", "bias": "bearish", "strength": 2, "index": i}
        elif i >= 3 and closes[i] < closes[i - 3]:
            return {"name": "Inverted Hammer", "bias": "bullish", "strength": 1, "index": i}
    return None


def _detect_engulfing(opens, highs, lows, closes, i) -> Optional[Dict]:
    """Bullish or Bearish Engulfing (2-bar)."""
    if i < 1:
        return None
    o0, c0 = opens[i - 1], closes[i - 1]
    o1, c1 = opens[i], closes[i]

    # Bullish engulfing
    if _is_bearish(o0, c0) and _is_bullish(o1, c1):
        if o1 <= c0 and c1 >= o0:
            return {"name": "Bullish Engulfing", "bias": "bullish", "strength": 3, "index": i}

    # Bearish engulfing
    if _is_bullish(o0, c0) and _is_bearish(o1, c1):
        if o1 >= c0 and c1 <= o0:
            return {"name": "Bearish Engulfing", "bias": "bearish", "strength": 3, "index": i}

    return None


def _detect_morning_evening_star(opens, highs, lows, closes, i) -> Optional[Dict]:
    """Morning Star (bullish) / Evening Star (bearish) — 3-bar patterns."""
    if i < 2:
        return None
    o0, c0 = opens[i - 2], closes[i - 2]
    o1, c1 = opens[i - 1], closes[i - 1]
    o2, c2 = opens[i], closes[i]

    body0 = _body(o0, c0)
    body1 = _body(o1, c1)
    body2 = _body(o2, c2)

    # Morning star: big bearish → small body → big bullish
    if (_is_bearish(o0, c0) and body0 > body1 * 2
            and _is_bullish(o2, c2) and body2 > body1 * 2):
        return {"name": "Morning Star", "bias": "bullish", "strength": 3, "index": i}

    # Evening star: big bullish → small body → big bearish
    if (_is_bullish(o0, c0) and body0 > body1 * 2
            and _is_bearish(o2, c2) and body2 > body1 * 2):
        return {"name": "Evening Star", "bias": "bearish", "strength": 3, "index": i}

    return None


def _detect_three_soldiers_crows(opens, highs, lows, closes, i) -> Optional[Dict]:
    """Three White Soldiers / Three Black Crows."""
    if i < 2:
        return None
    # Three white soldiers
    if all(_is_bullish(opens[i - j], closes[i - j]) for j in range(3)):
        if closes[i] > closes[i - 1] > closes[i - 2]:
            return {"name": "Three White Soldiers", "bias": "bullish", "strength": 3, "index": i}

    # Three black crows
    if all(_is_bearish(opens[i - j], closes[i - j]) for j in range(3)):
        if closes[i] < closes[i - 1] < closes[i - 2]:
            return {"name": "Three Black Crows", "bias": "bearish", "strength": 3, "index": i}

    return None


def _detect_tweezer(opens, highs, lows, closes, i) -> Optional[Dict]:
    """Tweezer Top / Bottom — two candles with near-identical highs or lows."""
    if i < 1:
        return None
    tol = _range(highs[i], lows[i]) * 0.05 if _range(highs[i], lows[i]) else 0.001

    # Tweezer top
    if abs(highs[i] - highs[i - 1]) <= tol and _is_bearish(opens[i], closes[i]) and _is_bullish(opens[i - 1], closes[i - 1]):
        return {"name": "Tweezer Top", "bias": "bearish", "strength": 2, "index": i}

    # Tweezer bottom
    if abs(lows[i] - lows[i - 1]) <= tol and _is_bullish(opens[i], closes[i]) and _is_bearish(opens[i - 1], closes[i - 1]):
        return {"name": "Tweezer Bottom", "bias": "bullish", "strength": 2, "index": i}

    return None


def _detect_pin_bar(opens, highs, lows, closes, i) -> Optional[Dict]:
    """Pin bar — one-sided wick at least 2/3 of total range."""
    o, h, l, c = opens[i], highs[i], lows[i], closes[i]
    r = _range(h, l)
    if r == 0:
        return None
    ls = _lower_shadow(l, o, c)
    us = _upper_shadow(h, o, c)

    if ls / r >= 0.66:
        return {"name": "Bullish Pin Bar", "bias": "bullish", "strength": 2, "index": i}
    if us / r >= 0.66:
        return {"name": "Bearish Pin Bar", "bias": "bearish", "strength": 2, "index": i}
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Scanner
# ═══════════════════════════════════════════════════════════════════════════

def detect_patterns(ohlcv: Dict, lookback: int = 10) -> List[Dict]:
    """
    Scan the last *lookback* bars and return all detected patterns,
    most recent first.
    """
    opens = ohlcv["open"]
    highs = ohlcv["high"]
    lows = ohlcv["low"]
    closes = ohlcv["close"]
    n = len(closes)
    start = max(0, n - lookback)

    patterns: List[Dict] = []
    for i in range(start, n):
        for detector in (
            lambda idx: _detect_doji(opens[idx], highs[idx], lows[idx], closes[idx], idx),
            lambda idx: _detect_hammer(opens, highs, lows, closes, idx),
            lambda idx: _detect_shooting_star(opens, highs, lows, closes, idx),
            lambda idx: _detect_engulfing(opens, highs, lows, closes, idx),
            lambda idx: _detect_morning_evening_star(opens, highs, lows, closes, idx),
            lambda idx: _detect_three_soldiers_crows(opens, highs, lows, closes, idx),
            lambda idx: _detect_tweezer(opens, highs, lows, closes, idx),
            lambda idx: _detect_pin_bar(opens, highs, lows, closes, idx),
        ):
            result = detector(i)
            if result:
                result["bars_ago"] = n - 1 - i
                patterns.append(result)

    # Deduplicate — keep highest-strength per bar
    seen = {}
    for p in patterns:
        key = (p["index"], p["bias"])
        if key not in seen or p["strength"] > seen[key]["strength"]:
            seen[key] = p
    deduped = sorted(seen.values(), key=lambda x: x["index"], reverse=True)
    return deduped
