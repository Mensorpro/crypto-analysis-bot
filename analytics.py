"""
Analytics engine — tracks every bot interaction, signal, and accuracy.

Supabase-backed (PostgreSQL). Logs:
  • Every analysis request (who, what coin, what timeframe, result)
  • Signal accuracy (checks price after 1h, 4h, 24h)
  • User activity
  • Error counts

Uses sync `requests` for dashboard queries and provides async wrappers
for the Telegram bot context.
"""
import os
import time
import asyncio
import logging
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


# ═══════════════════════════════════════════════════════════════════════════
# Low-level Supabase REST helpers  (sync)
# ═══════════════════════════════════════════════════════════════════════════

def _post(table: str, data: dict) -> Optional[List[dict]]:
    """INSERT into a table and return the created row(s)."""
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            json=data, headers=_HEADERS, timeout=10,
        )
        if r.status_code in (200, 201):
            return r.json()
        logger.error("Supabase POST %s → %s: %s", table, r.status_code, r.text[:300])
    except Exception as e:
        logger.error("Supabase POST %s error: %s", table, e)
    return None


def _patch(table: str, filters: str, data: dict) -> bool:
    """UPDATE rows matching filters."""
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}?{filters}",
            json=data, headers=_HEADERS, timeout=10,
        )
        return r.status_code in (200, 204)
    except Exception as e:
        logger.error("Supabase PATCH %s error: %s", table, e)
        return False


def _get(table: str, params: str = "") -> List[dict]:
    """SELECT from a table with optional query params."""
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        if params:
            url += f"?{params}"
        r = requests.get(url, headers=_HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json()
        logger.error("Supabase GET %s → %s: %s", table, r.status_code, r.text[:300])
    except Exception as e:
        logger.error("Supabase GET %s error: %s", table, e)
    return []


def _rpc(fn_name: str, params: Optional[dict] = None) -> Optional[list]:
    """Call a Supabase RPC function."""
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/{fn_name}",
            json=params or {}, headers=_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            return r.json()
        logger.error("Supabase RPC %s → %s: %s", fn_name, r.status_code, r.text[:300])
    except Exception as e:
        logger.error("Supabase RPC %s error: %s", fn_name, e)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Logging functions  (sync — call via asyncio.to_thread from bot)
# ═══════════════════════════════════════════════════════════════════════════

def log_analysis(user_id: Optional[int] = None, username: Optional[str] = None, first_name: Optional[str] = None,
                 symbol: str = "", timeframe: str = "", source: str = "telegram",
                 signal: Optional[Dict] = None, indicators: Optional[Dict] = None, levels: Optional[Dict] = None,
                 trend: Optional[Dict] = None, flow: Optional[Dict] = None, scenarios: Optional[List] = None,
                 response_time_ms: int = 0, error: Optional[str] = None) -> Optional[int]:
    """Log a completed analysis to Supabase. Returns the analysis row ID."""
    try:
        # ── Upsert user ──
        if user_id:
            _upsert_user(user_id, username, first_name)

        # ── Extract signal data ──
        score = signal.get("score", 0) if signal else None
        verdict = signal.get("verdict", "") if signal else None
        confidence = signal.get("confidence", 0) if signal else None
        price = indicators.get("price", 0) if indicators else None
        rsi_val = indicators.get("rsi") if indicators else None
        macd_hist = indicators.get("macd_hist") if indicators else None
        adx_val = indicators.get("adx") if indicators else None
        bb_pct_b = indicators.get("bb_pct_b") if indicators else None
        vol_ratio = indicators.get("vol_ratio") if indicators else None
        trend_overall = trend.get("overall", "") if trend else None
        flow_dir = flow.get("flow", "") if flow else None

        # ── Extract scenario targets ──
        target_bull = target_bear = stop_bull = stop_bear = None
        if scenarios:
            for sc in scenarios:
                if sc.get("label") == "BULLISH":
                    t = sc.get("target", "")
                    parts = t.replace("$", "").split("→")
                    if len(parts) >= 2:
                        try: target_bull = float(parts[1].strip())
                        except ValueError: pass
                    s = sc.get("stop", "").replace("$", "").strip()
                    try: stop_bull = float(s)
                    except ValueError: pass
                elif sc.get("label") == "BEARISH":
                    t = sc.get("target", "")
                    parts = t.replace("$", "").split("→")
                    if len(parts) >= 2:
                        try: target_bear = float(parts[1].strip())
                        except ValueError: pass
                    s = sc.get("stop", "").replace("$", "").strip()
                    try: stop_bear = float(s)
                    except ValueError: pass

        # ── Insert analysis row ──
        row = {
            "telegram_id": user_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "market": "crypto",
            "source": source,
            "score": score,
            "verdict": verdict,
            "confidence": confidence,
            "price_at_signal": price,
            "trend_score": signal.get("breakdown", {}).get("trend") if signal else None,
            "momentum_score": signal.get("breakdown", {}).get("momentum") if signal else None,
            "volume_score": signal.get("breakdown", {}).get("volume") if signal else None,
            "levels_score": signal.get("breakdown", {}).get("levels") if signal else None,
            "patterns_score": signal.get("breakdown", {}).get("patterns") if signal else None,
            "rsi": rsi_val,
            "macd_hist": macd_hist,
            "adx": adx_val,
            "bb_pct_b": bb_pct_b,
            "vol_ratio": vol_ratio,
            "trend_overall": trend_overall,
            "flow_direction": flow_dir,
        }
        result = _post("analyses", row)
        if not result:
            return None

        analysis_id = result[0]["id"]

        # ── Create accuracy tracking record ──
        if price and price > 0 and verdict:
            acc_row = {
                "analysis_id": analysis_id,
                "symbol": symbol,
                "verdict": verdict,
                "score": score or 0,
                "confidence": confidence or 0,
                "price_at_signal": price,
                "bull_target": target_bull,
                "bear_target": target_bear,
                "bull_stop": stop_bull,
                "bear_stop": stop_bear,
            }
            _post("signal_accuracy", acc_row)

        return analysis_id

    except Exception as e:
        logger.exception("Failed to log analysis: %s", e)
        return None


def _upsert_user(user_id: int, username: Optional[str] = None, first_name: Optional[str] = None):
    """Create or update a user record in Supabase."""
    now_iso = datetime.now(timezone.utc).isoformat()
    # Check if user exists
    existing = _get("bot_users", f"telegram_id=eq.{user_id}&select=id,total_analyses")
    if existing:
        # Update
        new_count = (existing[0].get("total_analyses") or 0) + 1
        _patch("bot_users", f"telegram_id=eq.{user_id}", {
            "username": username,
            "first_name": first_name,
            "last_seen": now_iso,
            "total_analyses": new_count,
        })
    else:
        # Insert
        _post("bot_users", {
            "telegram_id": user_id,
            "username": username,
            "first_name": first_name,
            "first_seen": now_iso,
            "last_seen": now_iso,
            "total_analyses": 1,
        })


def log_error(error_type: str = "analysis_error", details: str = "",
              telegram_id: Optional[int] = None, symbol: Optional[str] = None, timeframe: Optional[str] = None):
    """Log a bot error to Supabase."""
    try:
        _post("bot_errors", {
            "telegram_id": telegram_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "error_type": error_type,
            "error_message": str(details)[:500],
        })
    except Exception:
        pass


def log_event(event_type: str, details: str = ""):
    """Log a general bot event (startup, command, etc.)."""
    log_error(event_type, details)


# ═══════════════════════════════════════════════════════════════════════════
# Async wrappers for the Telegram bot context
# ═══════════════════════════════════════════════════════════════════════════

async def async_log_analysis(**kwargs) -> Optional[int]:
    """Non-blocking wrapper for log_analysis."""
    return await asyncio.to_thread(log_analysis, **kwargs)


async def async_log_error(**kwargs):
    """Non-blocking wrapper for log_error."""
    await asyncio.to_thread(log_error, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# Signal accuracy checker  (async background task)
# ═══════════════════════════════════════════════════════════════════════════

ACCURACY_WINDOWS = {
    "1h": 3600,
    "4h": 14400,
    "24h": 86400,
}


async def check_signal_accuracy():
    """
    Background task: checks old signals against current prices.
    Runs every 5 minutes.
    """
    from multi_exchange_client import MultiExchangeClient

    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes

            now = datetime.now(timezone.utc)

            for window_name, window_seconds in ACCURACY_WINDOWS.items():
                checked_col = f"checked_{window_name}"
                price_col = f"price_{window_name}"
                return_col = f"return_{window_name}"
                correct_col = f"correct_{window_name}"

                # Pending records for this window
                cutoff = (now - timedelta(seconds=window_seconds)).isoformat()
                rows = _get(
                    "signal_accuracy",
                    f"{checked_col}=eq.false"
                    f"&created_at=lte.{cutoff}"
                    f"&price_at_signal=gt.0"
                    f"&select=id,symbol,score,verdict,price_at_signal,bull_target,bear_target,bull_stop,bear_stop"
                    f"&limit=25"
                )
                if not rows:
                    continue

                client = MultiExchangeClient()

                # Fetch current prices (group by symbol)
                symbols = set(r["symbol"] for r in rows)
                current_prices = {}
                for sym in symbols:
                    try:
                        ohlcv = await client.fetch_ohlcv(sym, "1m", limit=1)
                        if ohlcv and ohlcv["close"]:
                            current_prices[sym] = ohlcv["close"][-1]
                    except Exception:
                        continue

                for row in rows:
                    sym = row["symbol"]
                    if sym not in current_prices:
                        continue

                    price_now = current_prices[sym]
                    price_then = row["price_at_signal"]
                    score = row["score"] or 0

                    if price_then == 0:
                        continue

                    change_pct = round(((price_now - price_then) / price_then) * 100, 4)

                    # Direction correct?
                    if score > 5:
                        correct = change_pct > 0
                    elif score < -5:
                        correct = change_pct < 0
                    else:
                        correct = abs(change_pct) < 1  # Neutral = stayed flat

                    # Target / stop hit?
                    target_hit = None
                    stop_hit = None
                    if score > 0 and row.get("bull_target"):
                        target_hit = price_now >= row["bull_target"]
                        if row.get("bull_stop"):
                            stop_hit = price_now <= row["bull_stop"]
                    elif score < 0 and row.get("bear_target"):
                        target_hit = price_now <= row["bear_target"]
                        if row.get("bear_stop"):
                            stop_hit = price_now >= row["bear_stop"]

                    update = {
                        price_col: price_now,
                        return_col: change_pct,
                        correct_col: correct,
                        checked_col: True,
                    }
                    if target_hit is not None:
                        update["target_hit"] = target_hit
                    if stop_hit is not None:
                        update["stop_hit"] = stop_hit

                    await asyncio.to_thread(
                        _patch, "signal_accuracy", f"id=eq.{row['id']}", update
                    )

                logger.info("Accuracy check [%s]: processed %d signals", window_name, len(rows))

        except Exception as e:
            logger.exception("Accuracy checker error: %s", e)
            await asyncio.sleep(60)


# ═══════════════════════════════════════════════════════════════════════════
# Query functions  (sync — used by Flask dashboard)
# ═══════════════════════════════════════════════════════════════════════════

def get_overview_stats() -> Dict:
    """High-level stats for the dashboard header."""
    now = datetime.now(timezone.utc)
    today_iso = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_iso = (now - timedelta(days=7)).isoformat()
    day_iso = (now - timedelta(hours=24)).isoformat()

    total_users = len(_get("bot_users", "select=id"))
    active_24h = len(_get("bot_users", f"select=id&last_seen=gte.{day_iso}"))
    total_analyses = len(_get("analyses", "select=id"))
    analyses_today = len(_get("analyses", f"select=id&created_at=gte.{today_iso}"))
    analyses_week = len(_get("analyses", f"select=id&created_at=gte.{week_iso}"))
    errors_today = len(_get("bot_errors", f"select=id&created_at=gte.{today_iso}"))

    success_rate = round(
        ((analyses_today - errors_today) / analyses_today * 100)
        if analyses_today > 0 else 100, 1
    )

    return {
        "total_analyses": total_analyses,
        "total_users": total_users,
        "analyses_today": analyses_today,
        "analyses_week": analyses_week,
        "active_users_24h": active_24h,
        "errors_today": errors_today,
        "success_rate": success_rate,
    }


def get_popular_coins(limit: int = 15) -> List[Dict]:
    """Most analyzed coins with avg score."""
    rows = _get("analyses", "select=symbol,score,confidence,verdict")
    if not rows:
        return []
    buckets: Dict[str, dict] = {}
    for r in rows:
        sym = r["symbol"]
        if sym not in buckets:
            buckets[sym] = {"symbol": sym, "count": 0, "total_score": 0, "total_conf": 0}
        buckets[sym]["count"] += 1
        buckets[sym]["total_score"] += (r["score"] or 0)
        buckets[sym]["total_conf"] += (r["confidence"] or 0)
    ranked = sorted(buckets.values(), key=lambda x: x["count"], reverse=True)[:limit]
    for s in ranked:
        n = s["count"]
        s["avg_score"] = round(s.pop("total_score") / n, 1) if n else 0
        s["avg_conf"] = round(s.pop("total_conf") / n, 0) if n else 0
    return ranked


def get_popular_timeframes() -> List[Dict]:
    """Timeframe usage distribution."""
    rows = _get("analyses", "select=timeframe")
    if not rows:
        return []
    dist: Dict[str, int] = {}
    for r in rows:
        tf = r.get("timeframe", "?")
        dist[tf] = dist.get(tf, 0) + 1
    return [{"timeframe": k, "count": v} for k, v in sorted(dist.items(), key=lambda x: -x[1])]


def get_signal_distribution() -> List[Dict]:
    """How many of each verdict type."""
    rows = _get("analyses", "select=verdict")
    if not rows:
        return []
    dist: Dict[str, int] = {}
    for r in rows:
        v = r.get("verdict") or "Unknown"
        dist[v] = dist.get(v, 0) + 1
    return [{"verdict": k, "count": v} for k, v in sorted(dist.items(), key=lambda x: -x[1])]


def get_usage_over_time(days: int = 30) -> List[Dict]:
    """Analyses per day."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = _get("analyses", f"select=created_at&created_at=gte.{since}")
    if not rows:
        return []
    daily: Dict[str, int] = {}
    for r in rows:
        day = r.get("created_at", "")[:10]
        daily[day] = daily.get(day, 0) + 1
    return [{"day": k, "count": v} for k, v in sorted(daily.items())]


def get_hourly_usage(days: int = 7) -> List[Dict]:
    """Analyses by hour-of-day (aggregated)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = _get("analyses", f"select=created_at&created_at=gte.{since}")
    if not rows:
        return []
    hourly: Dict[int, int] = {}
    for r in rows:
        ts = r.get("created_at", "")
        if len(ts) >= 13:
            try:
                h = int(ts[11:13])
                hourly[h] = hourly.get(h, 0) + 1
            except ValueError:
                pass
    return [{"hour": k, "count": v} for k, v in sorted(hourly.items())]


def get_users(limit: int = 50) -> List[Dict]:
    """User list with stats."""
    rows = _get("bot_users", f"select=telegram_id,username,first_name,last_name,first_seen,last_seen,total_analyses&order=total_analyses.desc&limit={limit}")
    # Enrich with favourite symbol/timeframe
    for u in rows:
        tid = u["telegram_id"]
        # Get their most-used symbol
        user_analyses = _get("analyses", f"select=symbol,timeframe&telegram_id=eq.{tid}&limit=200")
        if user_analyses:
            sym_counts: Dict[str, int] = {}
            tf_counts: Dict[str, int] = {}
            for a in user_analyses:
                sym_counts[a["symbol"]] = sym_counts.get(a["symbol"], 0) + 1
                tf_counts[a["timeframe"]] = tf_counts.get(a["timeframe"], 0) + 1
            u["fav_symbol"] = max(sym_counts, key=lambda k: sym_counts[k]) if sym_counts else None
            u["fav_timeframe"] = max(tf_counts, key=lambda k: tf_counts[k]) if tf_counts else None
        else:
            u["fav_symbol"] = None
            u["fav_timeframe"] = None
    return rows


def get_recent_activity(limit: int = 50) -> List[Dict]:
    """Recent analysis activity feed."""
    return _get(
        "analyses",
        f"select=id,telegram_id,symbol,timeframe,score,verdict,confidence,"
        f"price_at_signal,trend_overall,flow_direction,source,created_at"
        f"&order=created_at.desc&limit={limit}"
    )


def get_accuracy_stats() -> Dict:
    """Signal accuracy metrics across all check windows."""
    rows = _get("signal_accuracy", "select=checked_1h,checked_4h,checked_24h,correct_1h,correct_4h,correct_24h,return_1h,return_4h,return_24h,target_hit,stop_hit")
    if not rows:
        return {w: {"total_checked": 0, "direction_accuracy": 0, "avg_price_change": 0, "target_hit_rate": 0, "stop_hit_rate": 0} for w in ACCURACY_WINDOWS}

    result = {}
    for window in ACCURACY_WINDOWS:
        checked_key = f"checked_{window}"
        correct_key = f"correct_{window}"
        return_key = f"return_{window}"

        checked = [r for r in rows if r.get(checked_key)]
        total = len(checked)
        correct = sum(1 for r in checked if r.get(correct_key))
        avg_change = sum(r.get(return_key, 0) or 0 for r in checked) / total if total else 0
        targets = sum(1 for r in checked if r.get("target_hit"))
        stops = sum(1 for r in checked if r.get("stop_hit"))

        result[window] = {
            "total_checked": total,
            "direction_accuracy": round((correct / total * 100) if total > 0 else 0, 1),
            "avg_price_change": round(avg_change, 3),
            "target_hit_rate": round((targets / total * 100) if total > 0 else 0, 1),
            "stop_hit_rate": round((stops / total * 100) if total > 0 else 0, 1),
        }
    return result


def get_accuracy_by_verdict() -> List[Dict]:
    """Accuracy broken down by signal verdict (4h window)."""
    rows = _get("signal_accuracy", "select=verdict,correct_4h,checked_4h,return_4h")
    if not rows:
        return []
    buckets: Dict[str, dict] = {}
    for r in rows:
        v = r.get("verdict", "Unknown")
        if v not in buckets:
            buckets[v] = {"verdict": v, "total": 0, "correct": 0, "returns": []}
        if r.get("checked_4h"):
            buckets[v]["total"] += 1
            if r.get("correct_4h"):
                buckets[v]["correct"] += 1
            if r.get("return_4h") is not None:
                buckets[v]["returns"].append(r["return_4h"])

    result = []
    for v, d in buckets.items():
        result.append({
            "verdict": v,
            "total": d["total"],
            "correct": d["correct"],
            "accuracy_pct": round(d["correct"] / d["total"] * 100, 1) if d["total"] else 0,
            "avg_change": round(sum(d["returns"]) / len(d["returns"]), 3) if d["returns"] else 0,
        })
    return sorted(result, key=lambda x: -x["total"])


def get_accuracy_by_coin() -> List[Dict]:
    """Accuracy broken down by coin (4h window)."""
    rows = _get("signal_accuracy", "select=symbol,correct_4h,checked_4h,return_4h")
    if not rows:
        return []
    buckets: Dict[str, dict] = {}
    for r in rows:
        sym = r["symbol"]
        if sym not in buckets:
            buckets[sym] = {"symbol": sym, "total": 0, "correct": 0, "returns": []}
        if r.get("checked_4h"):
            buckets[sym]["total"] += 1
            if r.get("correct_4h"):
                buckets[sym]["correct"] += 1
            if r.get("return_4h") is not None:
                buckets[sym]["returns"].append(r["return_4h"])

    result = []
    for sym, d in buckets.items():
        if d["total"] < 2:
            continue
        result.append({
            "symbol": sym,
            "total": d["total"],
            "correct": d["correct"],
            "accuracy_pct": round(d["correct"] / d["total"] * 100, 1) if d["total"] else 0,
            "avg_change": round(sum(d["returns"]) / len(d["returns"]), 3) if d["returns"] else 0,
        })
    return sorted(result, key=lambda x: -x["accuracy_pct"])


def get_accuracy_by_confidence() -> List[Dict]:
    """Do higher confidence signals perform better?"""
    rows = _get("signal_accuracy", "select=confidence,correct_4h,checked_4h,return_4h")
    if not rows:
        return []
    buckets = {
        "High (70-100%)": {"total": 0, "correct": 0, "returns": []},
        "Medium (40-69%)": {"total": 0, "correct": 0, "returns": []},
        "Low (0-39%)": {"total": 0, "correct": 0, "returns": []},
    }
    for r in rows:
        if not r.get("checked_4h"):
            continue
        conf = r.get("confidence") or 0
        if conf >= 70:
            b = "High (70-100%)"
        elif conf >= 40:
            b = "Medium (40-69%)"
        else:
            b = "Low (0-39%)"
        buckets[b]["total"] += 1
        if r.get("correct_4h"):
            buckets[b]["correct"] += 1
        if r.get("return_4h") is not None:
            buckets[b]["returns"].append(r["return_4h"])

    result = []
    for label, d in buckets.items():
        result.append({
            "confidence_bucket": label,
            "total": d["total"],
            "correct": d["correct"],
            "accuracy_pct": round(d["correct"] / d["total"] * 100, 1) if d["total"] else 0,
            "avg_change": round(sum(d["returns"]) / len(d["returns"]), 3) if d["returns"] else 0,
        })
    return result


def get_recent_errors(limit: int = 30) -> List[Dict]:
    """Recent bot errors."""
    return _get(
        "bot_errors",
        f"select=id,telegram_id,symbol,timeframe,error_type,error_message,created_at"
        f"&order=created_at.desc&limit={limit}"
    )
