"""Configuration — loads secrets from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Secrets (never hardcode) ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── Default settings ─────────────────────────────────────────────────────
DEFAULT_TIMEFRAME = "15m"
DEFAULT_LOOKBACK = 200  # more bars = better indicator accuracy

# ── Technical analysis parameters ─────────────────────────────────────────
# Trend
SMA_FAST = 9
SMA_MID = 21
SMA_SLOW = 50
EMA_FAST = 12
EMA_SLOW = 26

# RSI
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# MACD
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# Bollinger Bands
BB_PERIOD = 20
BB_STD = 2.0

# ATR
ATR_PERIOD = 14

# Volume
VOLUME_SPIKE_THRESHOLD = 1.5  # 50% above average = spike
VOLUME_MA_PERIOD = 20

# Level detection
CLUSTER_TOLERANCE = 0.015  # 1.5% price tolerance for level clustering
MIN_TOUCHES = 2  # minimum touches to confirm a level
LEVEL_LOOKBACK = 100

# Signal scoring weights
WEIGHT_TREND = 0.25
WEIGHT_MOMENTUM = 0.25
WEIGHT_VOLUME = 0.20
WEIGHT_LEVELS = 0.15
WEIGHT_PATTERNS = 0.15

# Cache
CACHE_TTL_SECONDS = 45
