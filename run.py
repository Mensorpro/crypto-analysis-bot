"""
Entry point — runs Telegram bot + Flask admin dashboard together.

• Telegram bot runs on the main asyncio loop
• Flask dashboard runs in a background thread
• Accuracy checker runs as an asyncio background task
"""
import os
import sys
import logging
import threading

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def start_dashboard():
    """Launch Flask dashboard in a daemon thread."""
    from dashboard import run_dashboard
    port = int(os.environ.get("DASHBOARD_PORT", os.environ.get("PORT", 5000)))
    thread = threading.Thread(target=run_dashboard, args=(port,), daemon=True)
    thread.start()
    logger.info("Dashboard thread started on port %d", port)


def main():
    # Start dashboard first (non-blocking thread)
    start_dashboard()

    # Start bot (blocks — runs asyncio event loop)
    # skip_health_server=True because Flask already handles the web port
    from telegram_bot import main as bot_main
    bot_main(skip_health_server=True)


if __name__ == "__main__":
    main()
