"""
Telegram bot — interactive crypto analysis interface.

Features:
  • Inline market/symbol/timeframe picker
  • /analyze BTC 15m direct command
  • /help command
  • /quick top-4 quick-scan
  • Rich HTML-formatted output
  • Proper error handling with retry buttons
"""
import asyncio
import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from multi_exchange_client import MultiExchangeClient
from main import analyze_coin

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Symbol lists ──────────────────────────────────────────────────────────
CRYPTO_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT",
    "XRP/USDT", "ADA/USDT", "DOGE/USDT", "AVAX/USDT",
    "DOT/USDT", "MATIC/USDT", "LINK/USDT", "UNI/USDT",
]
FOREX_SYMBOLS = [
    "XAU/USDT:USDT", "XAG/USDT:USDT", "EUR/USDT", "GBP/USDT",
    "AUD/USDT", "JPY/USDT", "TRY/USDT", "BRL/USDT",
]
DEFI_SYMBOLS = [
    "AAVE/USDT", "UNI/USDT", "SUSHI/USDT", "COMP/USDT",
    "MKR/USDT", "SNX/USDT", "CRV/USDT", "1INCH/USDT",
]
TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"]

# Temporary user selections
user_data: dict = {}


# ═══════════════════════════════════════════════════════════════════════════
# Display helpers
# ═══════════════════════════════════════════════════════════════════════════

def _display_name(symbol: str, market: str) -> str:
    if market == "crypto":
        return symbol.replace("/USDT", "")
    if market == "forex":
        if symbol == "XAU/USDT:USDT":
            return "XAU/USD (Gold)"
        if symbol == "XAG/USDT:USDT":
            return "XAG/USD (Silver)"
        return symbol.replace("/USDT", "/USD")
    return symbol.replace("/USDT", "")


def _market_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Crypto", callback_data="market_crypto")],
        [InlineKeyboardButton("💱 Forex / Commodities", callback_data="market_forex")],
        [InlineKeyboardButton("🏦 DeFi", callback_data="market_defi")],
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Command handlers
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>🚀 Crypto Analysis Bot</b>\n\n"
        "Get institutional-grade technical analysis right here.\n\n"
        "<b>What you get:</b>\n"
        "• RSI, MACD, Bollinger, Stochastic, ADX, VWAP\n"
        "• Candlestick pattern recognition\n"
        "• Multi-timeframe trend confluence\n"
        "• Money-flow & volume analysis\n"
        "• Composite signal score with confidence %\n"
        "• Data-driven IF/THEN scenarios with R:R\n\n"
        "Pick a market to start 👇",
        reply_markup=_market_keyboard(),
        parse_mode="HTML",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>📖 Commands</b>\n\n"
        "/start — Main menu\n"
        "/analyze <code>SYMBOL [TF]</code> — Quick analysis\n"
        "  e.g. <code>/analyze BTC 15m</code>\n"
        "  e.g. <code>/analyze ETH/USDT 4h</code>\n\n"
        "/quick — Scan BTC, ETH, SOL, XRP (15m)\n"
        "/help — This message\n\n"
        "<b>Timeframes:</b> 5m, 15m, 30m, 1h, 4h, 1d",
        parse_mode="HTML",
    )


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await _run_analysis_direct(update, context)
    else:
        await update.message.reply_text("Select a market:", reply_markup=_market_keyboard())


async def cmd_quick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick scan of top coins."""
    coins = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]
    await update.message.reply_text("⏳ <b>Quick scan starting…</b>", parse_mode="HTML")
    for coin in coins:
        try:
            result = await analyze_coin(coin, "15m")
            await _send_analysis(update.message, result, coin, "crypto")
        except Exception as e:
            await update.message.reply_text(f"❌ {coin}: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# Direct analysis (from /analyze BTC 15m)
# ═══════════════════════════════════════════════════════════════════════════

async def _run_analysis_direct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = context.args[0].upper()
    if "/" not in raw and not raw.endswith("USDT"):
        symbol = f"{raw}/USDT"
    elif "/" not in raw:
        symbol = raw[:-4] + "/USDT"
    else:
        symbol = raw

    timeframe = context.args[1] if len(context.args) > 1 else "15m"

    msg = await update.message.reply_text(
        f"⏳ Analyzing <b>{symbol}</b> on <b>{timeframe}</b>…",
        parse_mode="HTML",
    )

    try:
        result = await analyze_coin(symbol, timeframe)
        await _send_analysis(update.message, result, symbol, "crypto")
    except Exception as e:
        logger.exception("Analysis error for %s", symbol)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Try Again", callback_data="new_analysis"),
        ]])
        await update.message.reply_text(f"❌ <b>Error:</b> {_escape_html(str(e))}", parse_mode="HTML", reply_markup=kb)


# ═══════════════════════════════════════════════════════════════════════════
# Send analysis result (handles chunking + buttons)
# ═══════════════════════════════════════════════════════════════════════════

async def _send_analysis(target, text: str, symbol: str, market: str):
    """Send analysis replying to a message (used by /analyze, /quick)."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 New Analysis", callback_data="new_analysis")],
        [InlineKeyboardButton(f"💰 More {market.title()}", callback_data=f"market_{market}")],
    ])

    if len(text) <= 4096:
        await target.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        chunks = _smart_chunk(text, 4096)
        for i, chunk in enumerate(chunks):
            rm = keyboard if i == len(chunks) - 1 else None
            await target.reply_text(chunk, parse_mode="HTML", reply_markup=rm)


async def _send_analysis_to_chat(chat, text: str, symbol: str, market: str):
    """Send analysis directly to chat (no reply, used by button flow)."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 New Analysis", callback_data="new_analysis")],
        [InlineKeyboardButton(f"💰 More {market.title()}", callback_data=f"market_{market}")],
    ])

    if len(text) <= 4096:
        await chat.send_message(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        chunks = _smart_chunk(text, 4096)
        for i, chunk in enumerate(chunks):
            rm = keyboard if i == len(chunks) - 1 else None
            await chat.send_message(chunk, parse_mode="HTML", reply_markup=rm)


def _smart_chunk(text: str, limit: int) -> list:
    """Split text at paragraph boundaries."""
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n\n", 0, limit)
        if cut == -1:
            cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ═══════════════════════════════════════════════════════════════════════════
# Callback handler (button presses)
# ═══════════════════════════════════════════════════════════════════════════

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    # ── New analysis / More X → strip buttons off current msg, send fresh picker ──
    if data == "new_analysis" or (data.startswith("market_") and query.message.text and len(query.message.text) > 200):
        # This was clicked on an analysis result — don't shrink it
        # Just remove the buttons so result stays clean
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        # Send a fresh picker below
        if data == "new_analysis":
            await query.message.chat.send_message("Select a market 👇", reply_markup=_market_keyboard(), parse_mode="HTML")
        else:
            # It's a market_ button on an analysis, start the flow
            market = data.replace("market_", "")
            user_data[user_id] = {"market": market}
            symbols_map = {"crypto": CRYPTO_SYMBOLS, "forex": FOREX_SYMBOLS, "defi": DEFI_SYMBOLS}
            symbols = symbols_map.get(market, CRYPTO_SYMBOLS)
            title = {"crypto": "💰 Select Crypto:", "forex": "💱 Select Pair:", "defi": "🏦 Select DeFi:"}.get(market, "Select:")
            keyboard = []
            for i in range(0, len(symbols), 2):
                row = [InlineKeyboardButton(_display_name(symbols[i], market), callback_data=f"sym_{symbols[i]}")]
                if i + 1 < len(symbols):
                    row.append(InlineKeyboardButton(_display_name(symbols[i + 1], market), callback_data=f"sym_{symbols[i + 1]}"))
                keyboard.append(row)
            keyboard.append([
                InlineKeyboardButton("🔍 Custom", callback_data=f"custom_{market}"),
                InlineKeyboardButton("⬅️ Back", callback_data="new_analysis"),
            ])
            await query.message.chat.send_message(title, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return

    # ── Custom symbol request → ask user to type the symbol ──
    if data.startswith("custom_"):
        market = data.replace("custom_", "")
        user_data[user_id] = {"market": market, "awaiting_custom": True}
        hint = {
            "crypto": "e.g. <b>PEPE</b>, <b>SHIB</b>, <b>WLD</b>, <b>ARB</b>",
            "forex": "e.g. <b>XAU</b>, <b>EUR</b>, <b>CHF</b>",
            "defi": "e.g. <b>AAVE</b>, <b>PENDLE</b>, <b>LDO</b>, <b>GMX</b>",
        }.get(market, "e.g. <b>BTC</b>")
        back_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data=f"market_{market}")],
        ])
        try:
            await query.edit_message_text(
                f"🔍 <b>Type a symbol</b>\n{hint}\n\n"
                f"Just the base coin — I'll add /USDT automatically.",
                parse_mode="HTML",
                reply_markup=back_kb,
            )
        except Exception:
            await query.message.chat.send_message(
                f"🔍 <b>Type a symbol</b>\n{hint}\n\n"
                f"Just the base coin — I'll add /USDT automatically.",
                parse_mode="HTML",
                reply_markup=back_kb,
            )
        return

    # ── Market selected (from picker, not from analysis) → edit in place ──
    if data.startswith("market_"):
        market = data.replace("market_", "")
        user_data[user_id] = {"market": market}

        symbols_map = {"crypto": CRYPTO_SYMBOLS, "forex": FOREX_SYMBOLS, "defi": DEFI_SYMBOLS}
        symbols = symbols_map.get(market, CRYPTO_SYMBOLS)
        title = {"crypto": "💰 Select Crypto:", "forex": "💱 Select Pair:", "defi": "🏦 Select DeFi:"}.get(market, "Select:")

        keyboard = []
        for i in range(0, len(symbols), 2):
            row = [InlineKeyboardButton(_display_name(symbols[i], market), callback_data=f"sym_{symbols[i]}")]
            if i + 1 < len(symbols):
                row.append(InlineKeyboardButton(_display_name(symbols[i + 1], market), callback_data=f"sym_{symbols[i + 1]}"))
            keyboard.append(row)
        keyboard.append([
            InlineKeyboardButton("🔍 Custom", callback_data=f"custom_{market}"),
            InlineKeyboardButton("⬅️ Back", callback_data="new_analysis"),
        ])

        try:
            await query.edit_message_text(title, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except Exception:
            await query.message.chat.send_message(title, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return

    # ── Symbol selected → edit into timeframe picker ──
    if data.startswith("sym_"):
        symbol = data.replace("sym_", "")
        if user_id not in user_data:
            await query.message.chat.send_message("❌ Session expired. Use /start again.")
            return
        user_data[user_id]["symbol"] = symbol
        market = user_data[user_id]["market"]

        keyboard = []
        for i in range(0, len(TIMEFRAMES), 3):
            row = [InlineKeyboardButton(tf, callback_data=f"tf_{tf}") for tf in TIMEFRAMES[i:i + 3]]
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"market_{market}")])

        dn = _display_name(symbol, market)
        try:
            await query.edit_message_text(f"<b>{dn}</b>  ·  pick a timeframe ⏱", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except Exception:
            await query.message.chat.send_message(f"<b>{dn}</b>  ·  pick a timeframe ⏱", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return

    # ── Timeframe selected → edit into loading, then edit into result ──
    if data.startswith("tf_"):
        timeframe = data.replace("tf_", "")
        if user_id not in user_data or "symbol" not in user_data.get(user_id, {}):
            await query.message.chat.send_message("❌ Session expired. Use /start again.")
            return

        symbol = user_data[user_id]["symbol"]
        market = user_data[user_id]["market"]
        dn = _display_name(symbol, market)

        # Edit picker into loading state
        try:
            await query.edit_message_text(f"⏳ <b>{dn}</b> · {timeframe}  —  analyzing…", parse_mode="HTML")
        except Exception:
            pass

        try:
            result = await analyze_coin(symbol, timeframe)

            nav_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 New Analysis", callback_data="new_analysis")],
                [InlineKeyboardButton(f"💰 More {market.title()}", callback_data=f"market_{market}")],
            ])

            if len(result) <= 4096:
                # Edit the loading message directly into the analysis — seamless
                try:
                    await query.edit_message_text(result, parse_mode="HTML", reply_markup=nav_keyboard)
                except Exception:
                    await query.message.chat.send_message(result, parse_mode="HTML", reply_markup=nav_keyboard)
            else:
                # Too long for one message — delete loading, send chunks
                chunks = _smart_chunk(result, 4096)
                try:
                    await query.message.delete()
                except Exception:
                    pass
                for i, chunk in enumerate(chunks):
                    rm = nav_keyboard if i == len(chunks) - 1 else None
                    await query.message.chat.send_message(chunk, parse_mode="HTML", reply_markup=rm)

        except Exception as e:
            logger.exception("Analysis error for %s", symbol)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Try Again", callback_data="new_analysis")],
                [InlineKeyboardButton("⬅️ Back", callback_data=f"market_{market}")],
            ])
            try:
                await query.edit_message_text(f"❌ <b>Error:</b> {_escape_html(str(e))}", parse_mode="HTML", reply_markup=kb)
            except Exception:
                await query.message.chat.send_message(f"❌ <b>Error:</b> {_escape_html(str(e))}", parse_mode="HTML", reply_markup=kb)

        user_data.pop(user_id, None)


# ═══════════════════════════════════════════════════════════════════════════
# Text message handler — captures custom symbol input
# ═══════════════════════════════════════════════════════════════════════════

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle typed symbol when user clicked 🔍 Custom."""
    user_id = update.effective_user.id
    state = user_data.get(user_id)

    if not state or not state.get("awaiting_custom"):
        return  # Not waiting for custom input — ignore

    raw = update.message.text.strip().upper()
    if not raw or len(raw) > 20:
        await update.message.reply_text("❌ Invalid symbol. Try again (e.g. <b>PEPE</b>)", parse_mode="HTML")
        return

    # Normalize to SYMBOL/USDT
    raw = raw.replace("$", "").replace(" ", "")
    if raw.endswith("/USDT"):
        symbol = raw
    elif raw.endswith("USDT"):
        symbol = raw[:-4] + "/USDT"
    else:
        symbol = f"{raw}/USDT"

    market = state["market"]

    # ── Validate symbol exists on Binance ──
    try:
        client = MultiExchangeClient()
        await client._ensure_markets()
        if symbol not in client.binance.markets:
            await update.message.reply_text(
                f"❌ <b>{raw}</b> not found on Binance.\n"
                f"Check spelling and try again (e.g. <b>PEPE</b>, <b>ARB</b>)",
                parse_mode="HTML",
            )
            return  # Stay in awaiting_custom state so they can retry
    except Exception:
        pass  # Skip validation if exchange unreachable — let analysis handle it

    user_data[user_id] = {"market": market, "symbol": symbol}

    keyboard = []
    for i in range(0, len(TIMEFRAMES), 3):
        row = [InlineKeyboardButton(tf, callback_data=f"tf_{tf}") for tf in TIMEFRAMES[i:i + 3]]
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"market_{market}")])

    dn = _display_name(symbol, market)
    await update.message.reply_text(
        f"<b>{dn}</b>  ·  pick a timeframe ⏱",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# Health-check server (keeps Render free tier happy)
# ═══════════════════════════════════════════════════════════════════════════

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args):
        pass  # Silence health-check logs


def _start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health server on port %d", port)


def main():
    from config import TELEGRAM_BOT_TOKEN

    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: Set TELEGRAM_BOT_TOKEN in your .env file.")
        return

    # Start health-check server for Render
    _start_health_server()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("analyze", cmd_analyze))
    application.add_handler(CommandHandler("quick", cmd_quick))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    logger.info("Bot started.")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
