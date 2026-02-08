# Crypto Analysis Bot

A Telegram bot delivering institutional-grade technical analysis for crypto, forex, and DeFi tokens.

## Links

- **GitHub:** https://github.com/Mensorpro/crypto-analysis-bot
- **Render Dashboard:** https://dashboard.render.com/web/srv-d64gipa4d50c73ef1dog
- **Live URL:** https://crypto-analysis-bot-1u2x.onrender.com

## What It Does

Every analysis runs a **10-step pipeline**:

1. Fetches multi-timeframe OHLCV data (primary + 1h + 4h) in parallel
2. Computes **13+ technical indicators** — RSI, MACD, Bollinger Bands, ATR, Stochastic, ADX, VWAP, OBV, EMAs, SMAs
3. Scans for **candlestick patterns** — Doji, Hammer, Engulfing, Morning/Evening Star, Three Soldiers/Crows, Pin Bars, Tweezer Tops/Bottoms
4. Identifies **support/resistance levels** with touch counts and volume weighting
5. Runs **multi-timeframe trend confluence** analysis (primary + 1h + 4h)
6. Analyzes **money flow** — buy/sell pressure %, OBV trend, VWAP position, volume spikes
7. Produces a **composite signal score** (-100 to +100) with confidence %
8. Generates **data-driven IF/THEN scenarios** with entry, target, stop, and R:R ratios
9. Reports **session context** (Asia/London/NY overlap, expected volatility)
10. Formats everything into a rich HTML Telegram message

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create a `.env` file (see `.env.example`):

```
TELEGRAM_BOT_TOKEN=your_token_here
```

3. Run the bot:

```bash
python telegram_bot.py
```

## Commands

| Command            | Description                                  |
| ------------------ | -------------------------------------------- |
| `/start`           | Main menu with market picker                 |
| `/analyze BTC 15m` | Quick analysis (symbol + optional timeframe) |
| `/quick`           | Scan BTC, ETH, SOL, XRP on 15m               |
| `/help`            | List commands                                |

## Architecture

| File                       | Purpose                                                   |
| -------------------------- | --------------------------------------------------------- |
| `main.py`                  | 10-step analysis orchestrator                             |
| `indicators.py`            | RSI, MACD, BB, ATR, Stochastic, ADX, OBV, VWAP, EMAs/SMAs |
| `patterns.py`              | Candlestick pattern recognition (8+ patterns)             |
| `analysis_components.py`   | Levels, multi-TF trend, money flow, scenarios             |
| `signal_engine.py`         | Composite scoring engine (-100 to +100)                   |
| `formatter.py`             | Rich HTML Telegram output                                 |
| `crypto_analyzer.py`       | Data fetching layer                                       |
| `multi_exchange_client.py` | Singleton exchange client with caching                    |
| `cache_manager.py`         | TTL-based cache                                           |
| `config.py`                | All tunable parameters (loads from `.env`)                |
| `telegram_bot.py`          | Bot commands and UI                                       |

## Configuration

All analysis parameters are tunable in `config.py`:

- Moving average periods (SMA 9/21/50, EMA 12/26)
- RSI period and overbought/oversold thresholds
- MACD fast/slow/signal periods
- Bollinger Band period and std multiplier
- ATR period
- Volume spike threshold
- Level detection tolerance and minimum touches
- Signal scoring weights (trend, momentum, volume, levels, patterns)
- Cache TTL
