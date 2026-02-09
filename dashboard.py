"""
Admin dashboard — Flask web server with REST API.

Serves the admin panel and provides JSON endpoints for all analytics data.
Designed to run alongside the Telegram bot.  Uses Supabase-backed analytics.
"""
import os
import logging
from flask import Flask, render_template, jsonify, request
from analytics import (
    get_overview_stats,
    get_popular_coins,
    get_popular_timeframes,
    get_signal_distribution,
    get_usage_over_time,
    get_hourly_usage,
    get_users,
    get_recent_activity,
    get_accuracy_stats,
    get_accuracy_by_verdict,
    get_accuracy_by_coin,
    get_accuracy_by_confidence,
    get_recent_errors,
)

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["JSON_SORT_KEYS"] = False

# Simple auth — set DASHBOARD_PASSWORD env var to protect the dashboard
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")


def _check_auth():
    """Optional password protection."""
    if not DASHBOARD_PASSWORD:
        return True
    token = request.args.get("token") or request.headers.get("X-Dashboard-Token")
    return token == DASHBOARD_PASSWORD


# ═══════════════════════════════════════════════════════════════════════════
# Pages
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    if not _check_auth() and DASHBOARD_PASSWORD:
        return "Unauthorized", 401
    return render_template("admin.html")


# ═══════════════════════════════════════════════════════════════════════════
# API endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/overview")
def api_overview():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_overview_stats())


@app.route("/api/popular-coins")
def api_popular_coins():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_popular_coins())


@app.route("/api/timeframes")
def api_timeframes():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_popular_timeframes())


@app.route("/api/signal-distribution")
def api_signal_distribution():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_signal_distribution())


@app.route("/api/usage-daily")
def api_usage_daily():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    days = request.args.get("days", 30, type=int)
    return jsonify(get_usage_over_time(days))


@app.route("/api/usage-hourly")
def api_usage_hourly():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_hourly_usage())


@app.route("/api/users")
def api_users():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_users())


@app.route("/api/activity")
def api_activity():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    limit = request.args.get("limit", 50, type=int)
    return jsonify(get_recent_activity(limit))


@app.route("/api/accuracy")
def api_accuracy():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_accuracy_stats())


@app.route("/api/accuracy/by-verdict")
def api_accuracy_by_verdict():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_accuracy_by_verdict())


@app.route("/api/accuracy/by-coin")
def api_accuracy_by_coin():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_accuracy_by_coin())


@app.route("/api/accuracy/by-confidence")
def api_accuracy_by_confidence():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_accuracy_by_confidence())


@app.route("/api/errors")
def api_errors():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401
    limit = request.args.get("limit", 30, type=int)
    return jsonify(get_recent_errors(limit))


@app.route("/health")
@app.route("/api/ping")
def health():
    """Health / uptime check — no auth required."""
    return jsonify({"status": "ok"})


def run_dashboard(port: int = 5000):
    """Run the Flask dashboard (call from a thread)."""
    logger.info("Dashboard starting on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
