"""
Rich Telegram-formatted analysis output.

Uses HTML parse_mode. Designed for clean reading on mobile Telegram.
Avoids space-based alignment (proportional font breaks it).
Uses <pre> blocks only where alignment matters.
"""
from typing import Dict, List


# ── Tiny helpers ──────────────────────────────────────────────────────────

def _bar(value: float, max_val: float = 100, width: int = 10) -> str:
    filled = max(0, min(width, round(value / max_val * width)))
    return "▓" * filled + "░" * (width - filled)


def _arrow(direction: str) -> str:
    d = direction.lower()
    if "strong_up" in d or "strong up" in d:
        return "🟢⬆️"
    if "up" in d:
        return "🟢↗"
    if "strong_down" in d or "strong down" in d:
        return "🔴⬇️"
    if "down" in d:
        return "🔴↘"
    return "🟡➡️"


def _score_emoji(score: float) -> str:
    if score >= 40: return "🟢"
    if score >= 10: return "🟢"
    if score <= -40: return "🔴"
    if score <= -10: return "🔴"
    return "🟡"


def _rsi_tag(rsi: float) -> str:
    if rsi >= 70: return "⚠️ Overbought"
    if rsi <= 30: return "⚠️ Oversold"
    if rsi >= 55: return "Bullish"
    if rsi <= 45: return "Bearish"
    return "Neutral"


def _divider() -> str:
    return "─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"


def format_analysis(symbol: str, timeframe: str, indicators: Dict,
                    levels: Dict, trend: Dict, flow: Dict,
                    scenarios: List[Dict], patterns: List[Dict],
                    signal: Dict, session: Dict) -> str:
    """Build the full analysis message (HTML)."""

    L: List[str] = []

    # ━━ HEADER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    price = indicators.get("price", 0)
    L.append(f"📊 <b>{symbol}</b>  ·  {timeframe}")
    L.append(f"💲 <b>{price:,.2f}</b>")
    L.append("")

    # ━━ VERDICT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    s = signal
    L.append(f"{s['emoji']} <b>{s['verdict']}</b>")
    L.append(f"Score: <b>{s['score']:+.0f}</b>/100  ·  Confidence: <b>{s['confidence']}%</b>")
    bar = _bar(abs(s["score"]))
    label = "bullish" if s["score"] > 0 else "bearish" if s["score"] < 0 else "flat"
    L.append(f"{bar}  {label}")
    L.append("")
    L.append(_divider())

    # ━━ SCORE BREAKDOWN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    bd = s["breakdown"]
    L.append("")
    L.append("📈 <b>Score Breakdown</b>")
    for key, mx in [("trend", 25), ("momentum", 25), ("volume", 20), ("levels", 15), ("patterns", 15)]:
        val = bd[key]
        emoji = _score_emoji(val / mx * 100 if mx else 0)
        L.append(f"  {emoji} {key.title()}: <b>{val:+.1f}</b>")
    L.append("")
    L.append(_divider())

    # ━━ MULTI-TF TREND ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    L.append("")
    L.append("🔀 <b>Trend by Timeframe</b>")
    for tf_data in (trend["primary"], trend["tf_1h"], trend["tf_4h"]):
        tf_label = tf_data["tf"].upper() if tf_data["tf"] != "primary" else timeframe.upper()
        arrow = _arrow(tf_data["direction"])
        strength = "strong" if tf_data["adx"] > 25 else "weak"
        L.append(f"  {arrow} <b>{tf_label}</b> — {tf_data['direction'].replace('_', ' ')}  ({strength}, ADX {tf_data['adx']})")
    overall = trend["overall"].replace("_", " ")
    L.append(f"  📊 Confluence: <b>{trend['confluence_score']:+.1f}</b> → {overall}")
    L.append("")
    L.append(_divider())

    # ━━ INDICATORS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    L.append("")
    L.append("📉 <b>Indicators</b>")
    L.append("")

    # RSI
    rsi = indicators["rsi"]
    L.append(f"  <b>RSI(14):</b>  {rsi}  — {_rsi_tag(rsi)}")

    # MACD
    hist = indicators["macd_hist"]
    macd_word = "🟢 Bullish" if hist > 0 else "🔴 Bearish"
    L.append(f"  <b>MACD:</b>  {macd_word}")

    # Stochastic
    k, d = indicators["stoch_k"], indicators["stoch_d"]
    stoch_note = ""
    if k < 20: stoch_note = " — ⚠️ Oversold"
    elif k > 80: stoch_note = " — ⚠️ Overbought"
    L.append(f"  <b>Stoch:</b>  K {k:.0f} / D {d:.0f}{stoch_note}")

    # Bollinger
    L.append(f"  <b>BB %B:</b>  {indicators['bb_pct_b']:.2f}  (width {indicators['bb_width']:.1f}%)")

    # ATR
    L.append(f"  <b>ATR:</b>  {indicators['atr']:.4f}  ({indicators['atr_pct']:.1f}%)")

    # VWAP
    vwap_pos = "above ✅" if indicators["price_vs_vwap"] > 0 else "below ❌"
    L.append(f"  <b>VWAP:</b>  {indicators['vwap']:,.2f}  ({vwap_pos})")

    L.append("")
    L.append(_divider())

    # ━━ KEY LEVELS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    L.append("")
    L.append("🎯 <b>Key Levels</b>")
    L.append("")
    L.append(f"  🔺 R2  <b>${levels['r2']}</b>  ({levels['r2_touches']} touches)")
    L.append(f"  🔺 R1  <b>${levels['r1']}</b>  ({levels['r1_touches']} touches)")
    L.append(f"  ▶️ <b>NOW  ${levels['current']}</b>  (range: {levels['range_position']:.0f}%)")
    L.append(f"  🔻 S1  <b>${levels['s1']}</b>  ({levels['s1_touches']} touches)")
    L.append(f"  🔻 S2  <b>${levels['s2']}</b>  ({levels['s2_touches']} touches)")
    L.append("")
    L.append(_divider())

    # ━━ MONEY FLOW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    L.append("")
    L.append("💰 <b>Money Flow</b>")
    flow_map = {"strong_inflow": "🟢🟢 Strong Inflow", "inflow": "🟢 Inflow",
                "balanced": "🟡 Balanced", "outflow": "🔴 Outflow",
                "strong_outflow": "🔴🔴 Strong Outflow"}
    L.append(f"  {flow_map.get(flow['flow'], flow['flow'])}")
    L.append(f"  Buy  {_bar(flow['buy_pct'])}  {flow['buy_pct']:.0f}%")
    L.append(f"  Sell {_bar(flow['sell_pct'])}  {flow['sell_pct']:.0f}%")
    vol_note = "🔥 SPIKE" if flow["vol_spike"] else flow["vol_trend"]
    L.append(f"  Vol: <b>{flow['vol_ratio']:.1f}x</b> avg  {vol_note}")
    L.append(f"  OBV: {flow['obv_trend']}")
    L.append("")
    L.append(_divider())

    # ━━ CANDLE PATTERNS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if patterns:
        L.append("")
        L.append("🕯 <b>Candle Patterns</b>")
        for p in patterns[:4]:
            bias_e = "🟢" if p["bias"] == "bullish" else "🔴" if p["bias"] == "bearish" else "🟡"
            stars = "★" * p["strength"]
            when = "now" if p["bars_ago"] == 0 else f"{p['bars_ago']}b ago"
            L.append(f"  {bias_e} {p['name']}  {stars}  ({when})")
        L.append("")
        L.append(_divider())

    # ━━ SCENARIOS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    L.append("")
    L.append("🗺 <b>Scenarios</b>")
    for sc in scenarios:
        prob_e = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(sc["probability"], "⚪")
        L.append("")
        L.append(f"{sc['emoji']} <b>{sc['label']}</b>  {prob_e} {sc['probability']}")
        L.append(f"  IF → {sc['trigger']}")
        L.append(f"  🎯 Target: {sc['target']}")
        L.append(f"  🛑 Stop: {sc['stop']}")
        if sc.get("rr_ratio"):
            L.append(f"  R:R  <b>{sc['rr_ratio']:.1f}</b>")
    L.append("")
    L.append(_divider())

    # ━━ SESSION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    L.append("")
    L.append(f"⏰ <b>Session:</b>  {session['active']}")
    L.append(f"  Volatility: {session['volatility']}  ·  Next: {session['next_session']} in {session['hours_until_next']}h")
    if session.get("note"):
        L.append(f"  💡 {session['note']}")
    L.append("")

    # ━━ DISCLAIMER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    L.append("<i>⚠️ Not financial advice. DYOR.</i>")

    return "\n".join(L)

