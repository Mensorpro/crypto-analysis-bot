"""
Entry point — runs Telegram bot + Flask admin dashboard together.

• Flask dashboard runs in a background thread on PORT (Render-compatible)
• Telegram bot runs on the main asyncio loop
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
    """Launch Flask dashboard in a daemon thread.
    
    IMPORTANT: Always uses PORT env var so Render/hosting can route traffic correctly.
    """
    from dashboard import run_dashboard
    # Always use PORT (set by Render/Koyeb), never a separate DASHBOARD_PORT
    port = int(os.environ.get("PORT", 8000))
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
