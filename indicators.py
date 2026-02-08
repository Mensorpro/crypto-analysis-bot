"""
Technical indicators — computed from raw OHLCV lists.

Every function takes plain Python lists (no pandas/numpy needed) so the bot
stays lightweight.  Each returns either a single float or a list.
"""
from typing import Dict, List, Optional, Tuple
import math
import config


# ═══════════════════════════════════════════════════════════════════════════
# Moving Averages
# ═══════════════════════════════════════════════════════════════════════════

def sma(data: List[float], period: int) -> List[float]:
    """Simple Moving Average — returns list aligned with *data* (NaN-padded)."""
    out: List[float] = [float("nan")] * (period - 1)
    for i in range(period - 1, len(data)):
        out.append(sum(data[i - period + 1 : i + 1]) / period)
    return out


def ema(data: List[float], period: int) -> List[float]:
    """Exponential Moving Average."""
    k = 2 / (period + 1)
    out: List[float] = [data[0]]
    for price in data[1:]:
        out.append(price * k + out[-1] * (1 - k))
    return out


def sma_last(data: List[float], period: int) -> float:
    """Latest SMA value (convenience)."""
    if len(data) < period:
        return sum(data) / len(data)
    return sum(data[-period:]) / period


def ema_last(data: List[float], period: int) -> float:
    """Latest EMA value (convenience)."""
    return ema(data, period)[-1]


# ═══════════════════════════════════════════════════════════════════════════
# RSI
# ═══════════════════════════════════════════════════════════════════════════

def rsi(closes: List[float], period: Optional[int] = None) -> List[float]:
    """Relative Strength Index (Wilder smoothing)."""
    period = period or config.RSI_PERIOD
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rsi_values: List[float] = [float("nan")] * period
    if avg_loss == 0:
        rsi_values.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi_values.append(100 - 100 / (1 + rs))

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - 100 / (1 + rs))

    return rsi_values


def rsi_last(closes: List[float], period: Optional[int] = None) -> float:
    """Latest RSI value."""
    vals = rsi(closes, period)
    return vals[-1] if vals else 50.0


# ═══════════════════════════════════════════════════════════════════════════
# MACD
# ═══════════════════════════════════════════════════════════════════════════

def macd(closes: List[float],
         fast: Optional[int] = None, slow: Optional[int] = None, signal: Optional[int] = None
         ) -> Dict[str, List[float]]:
    """MACD line, signal line, histogram."""
    fast = fast or config.MACD_FAST
    slow = slow or config.MACD_SLOW
    signal = signal or config.MACD_SIGNAL

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]

    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def macd_last(closes: List[float]) -> Dict[str, float]:
    m = macd(closes)
    return {
        "macd": m["macd"][-1],
        "signal": m["signal"][-1],
        "histogram": m["histogram"][-1],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Bollinger Bands
# ═══════════════════════════════════════════════════════════════════════════

def bollinger_bands(closes: List[float],
                    period: Optional[int] = None, std_mult: Optional[float] = None
                    ) -> Dict[str, List[float]]:
    """Upper, middle (SMA), lower bands."""
    period = period or config.BB_PERIOD
    std_mult = std_mult or config.BB_STD

    middle = sma(closes, period)
    upper: List[float] = []
    lower: List[float] = []

    for i in range(len(closes)):
        if math.isnan(middle[i]):
            upper.append(float("nan"))
            lower.append(float("nan"))
        else:
            window = closes[max(0, i - period + 1) : i + 1]
            mean = middle[i]
            variance = sum((x - mean) ** 2 for x in window) / len(window)
            std = math.sqrt(variance)
            upper.append(mean + std_mult * std)
            lower.append(mean - std_mult * std)

    return {"upper": upper, "middle": middle, "lower": lower}


def bb_last(closes: List[float]) -> Dict[str, float]:
    bb = bollinger_bands(closes)
    return {
        "upper": bb["upper"][-1],
        "middle": bb["middle"][-1],
        "lower": bb["lower"][-1],
        "width": (bb["upper"][-1] - bb["lower"][-1]) / bb["middle"][-1] * 100,
        "pct_b": (closes[-1] - bb["lower"][-1]) / (bb["upper"][-1] - bb["lower"][-1])
                 if (bb["upper"][-1] - bb["lower"][-1]) != 0 else 0.5,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ATR (Average True Range)
# ═══════════════════════════════════════════════════════════════════════════

def atr(highs: List[float], lows: List[float], closes: List[float],
        period: Optional[int] = None) -> List[float]:
    """Wilder-smoothed ATR."""
    period = period or config.ATR_PERIOD
    tr_list: List[float] = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)

    atr_vals: List[float] = [float("nan")] * (period - 1)
    atr_vals.append(sum(tr_list[:period]) / period)
    for i in range(period, len(tr_list)):
        atr_vals.append((atr_vals[-1] * (period - 1) + tr_list[i]) / period)

    return atr_vals


def atr_last(highs: List[float], lows: List[float], closes: List[float],
             period: Optional[int] = None) -> float:
    return atr(highs, lows, closes, period)[-1]


# ═══════════════════════════════════════════════════════════════════════════
# Stochastic Oscillator
# ═══════════════════════════════════════════════════════════════════════════

def stochastic(highs: List[float], lows: List[float], closes: List[float],
               k_period: int = 14, d_period: int = 3
               ) -> Dict[str, List[float]]:
    """%K and %D."""
    k_vals: List[float] = []
    for i in range(len(closes)):
        start = max(0, i - k_period + 1)
        h = max(highs[start : i + 1])
        l = min(lows[start : i + 1])
        if h == l:
            k_vals.append(50.0)
        else:
            k_vals.append((closes[i] - l) / (h - l) * 100)

    d_vals = sma(k_vals, d_period)
    return {"k": k_vals, "d": d_vals}


def stochastic_last(highs, lows, closes) -> Dict[str, float]:
    s = stochastic(highs, lows, closes)
    return {"k": s["k"][-1], "d": s["d"][-1]}


# ═══════════════════════════════════════════════════════════════════════════
# ADX (Average Directional Index)
# ═══════════════════════════════════════════════════════════════════════════

def adx(highs: List[float], lows: List[float], closes: List[float],
        period: int = 14) -> Dict[str, float]:
    """Returns latest ADX, +DI, -DI."""
    plus_dm: List[float] = []
    minus_dm: List[float] = []
    tr_list: List[float] = []

    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
        tr_list.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))

    if len(tr_list) < period:
        return {"adx": 25.0, "plus_di": 50.0, "minus_di": 50.0}

    # Wilder smoothing
    def smooth(arr):
        s = [sum(arr[:period])]
        for val in arr[period:]:
            s.append(s[-1] - s[-1] / period + val)
        return s

    str_list = smooth(tr_list)
    sp_dm = smooth(plus_dm)
    sm_dm = smooth(minus_dm)

    plus_di = [(100 * p / t) if t != 0 else 0 for p, t in zip(sp_dm, str_list)]
    minus_di = [(100 * m / t) if t != 0 else 0 for m, t in zip(sm_dm, str_list)]

    dx = [abs(p - m) / (p + m) * 100 if (p + m) != 0 else 0
          for p, m in zip(plus_di, minus_di)]

    if len(dx) < period:
        adx_val = sum(dx) / len(dx) if dx else 25.0
    else:
        adx_val = sum(dx[:period]) / period
        for val in dx[period:]:
            adx_val = (adx_val * (period - 1) + val) / period

    return {
        "adx": round(adx_val, 1),
        "plus_di": round(plus_di[-1], 1),
        "minus_di": round(minus_di[-1], 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# OBV (On-Balance Volume)
# ═══════════════════════════════════════════════════════════════════════════

def obv(closes: List[float], volumes: List[float]) -> List[float]:
    """On-Balance Volume."""
    vals = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            vals.append(vals[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            vals.append(vals[-1] - volumes[i])
        else:
            vals.append(vals[-1])
    return vals


def obv_trend(closes: List[float], volumes: List[float], lookback: int = 20) -> str:
    """Is OBV trending up, down, or flat over recent bars?"""
    o = obv(closes, volumes)
    if len(o) < lookback:
        return "neutral"
    recent = o[-lookback:]
    slope = (recent[-1] - recent[0]) / abs(recent[0]) if recent[0] != 0 else 0
    if slope > 0.05:
        return "rising"
    elif slope < -0.05:
        return "falling"
    return "flat"


# ═══════════════════════════════════════════════════════════════════════════
# VWAP (session-based approximation)
# ═══════════════════════════════════════════════════════════════════════════

def vwap(highs: List[float], lows: List[float], closes: List[float],
         volumes: List[float]) -> float:
    """Cumulative VWAP (latest value)."""
    tp_vol = sum(
        ((h + l + c) / 3) * v
        for h, l, c, v in zip(highs, lows, closes, volumes)
    )
    total_vol = sum(volumes)
    return tp_vol / total_vol if total_vol else closes[-1]


# ═══════════════════════════════════════════════════════════════════════════
# Volume analysis helpers
# ═══════════════════════════════════════════════════════════════════════════

def volume_sma(volumes: List[float], period: Optional[int] = None) -> float:
    period = period or config.VOLUME_MA_PERIOD
    return sma_last(volumes, period)


def volume_ratio(volumes: List[float], period: Optional[int] = None) -> float:
    """Current volume / average volume."""
    avg = volume_sma(volumes, period)
    return volumes[-1] / avg if avg else 1.0


def is_volume_spike(volumes: List[float], threshold: Optional[float] = None) -> bool:
    threshold = threshold or config.VOLUME_SPIKE_THRESHOLD
    return volume_ratio(volumes) >= threshold


def volume_trend(volumes: List[float], lookback: int = 10) -> str:
    """Are recent volumes increasing, decreasing, or stable?"""
    if len(volumes) < lookback:
        return "unknown"
    first_half = sum(volumes[-lookback:-lookback // 2]) / (lookback // 2)
    second_half = sum(volumes[-lookback // 2:]) / (lookback // 2)
    ratio = second_half / first_half if first_half else 1.0
    if ratio > 1.2:
        return "increasing"
    elif ratio < 0.8:
        return "decreasing"
    return "stable"


# ═══════════════════════════════════════════════════════════════════════════
# Composite helpers
# ═══════════════════════════════════════════════════════════════════════════

def compute_all(ohlcv: Dict) -> Dict:
    """Run every indicator on one OHLCV dict; return a flat results dict."""
    c = ohlcv["close"]
    h = ohlcv["high"]
    l = ohlcv["low"]
    v = ohlcv["volume"]

    _rsi = rsi_last(c)
    _macd = macd_last(c)
    _bb = bb_last(c)
    _atr = atr_last(h, l, c)
    _stoch = stochastic_last(h, l, c)
    _adx = adx(h, l, c)
    _vwap = vwap(h, l, c, v)

    return {
        "price": c[-1],
        "rsi": round(_rsi, 1),
        "macd_line": round(_macd["macd"], 6),
        "macd_signal": round(_macd["signal"], 6),
        "macd_hist": round(_macd["histogram"], 6),
        "bb_upper": round(_bb["upper"], 2),
        "bb_middle": round(_bb["middle"], 2),
        "bb_lower": round(_bb["lower"], 2),
        "bb_width": round(_bb["width"], 2),
        "bb_pct_b": round(_bb["pct_b"], 3),
        "atr": round(_atr, 4),
        "atr_pct": round(_atr / c[-1] * 100, 2),
        "stoch_k": round(_stoch["k"], 1),
        "stoch_d": round(_stoch["d"], 1),
        "adx": _adx["adx"],
        "plus_di": _adx["plus_di"],
        "minus_di": _adx["minus_di"],
        "vwap": round(_vwap, 2),
        "price_vs_vwap": round((c[-1] - _vwap) / _vwap * 100, 2),
        "sma_9": round(sma_last(c, config.SMA_FAST), 2),
        "sma_21": round(sma_last(c, config.SMA_MID), 2),
        "sma_50": round(sma_last(c, config.SMA_SLOW), 2),
        "ema_12": round(ema_last(c, config.EMA_FAST), 2),
        "ema_26": round(ema_last(c, config.EMA_SLOW), 2),
        "vol_ratio": round(volume_ratio(v), 2),
        "vol_spike": is_volume_spike(v),
        "vol_trend": volume_trend(v),
        "obv_trend": obv_trend(c, v),
    }
