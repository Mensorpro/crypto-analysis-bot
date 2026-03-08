"""
Multi-exchange client — singleton with built-in caching.

Handles Binance geo-restriction (451) by trying multiple exchanges:
  1. KuCoin  (works worldwide, no KYC for public data)
  2. Bybit   (works worldwide for public data)
  3. Gate.io (broad availability)
  4. Binance (last resort — may be blocked on US-based hosts)
"""
import ccxt.async_support as ccxt
from typing import Dict, Optional, List, Tuple
from cache_manager import CacheManager
import config
import logging
import os

logger = logging.getLogger(__name__)

# Optional user-defined proxy
EXCHANGE_PROXY = os.getenv("EXCHANGE_PROXY", "")

# Exchange priority order — Binance last because it geo-blocks US servers
EXCHANGE_CONFIGS: List[Tuple[str, dict]] = [
    ("kucoin", {
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    }),
    ("bybit", {
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    }),
    ("gateio", {
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    }),
    ("binance", {
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    }),
]


class MultiExchangeClient:
    """Manages exchange connections with caching and proper lifecycle."""

    _instance: Optional["MultiExchangeClient"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cache = CacheManager(ttl_seconds=config.CACHE_TTL_SECONDS)
        self._markets_loaded = False
        self._active_exchange = None
        self._exchange_name = "none"
        self._exchanges: List[Tuple[str, ccxt.Exchange]] = []
        self._setup_exchanges()

    def _setup_exchanges(self):
        """Create exchange instances in priority order."""
        for name, opts in EXCHANGE_CONFIGS:
            if EXCHANGE_PROXY:
                opts["proxies"] = {
                    "http": EXCHANGE_PROXY,
                    "https": EXCHANGE_PROXY,
                }
            exchange_class = getattr(ccxt, name)
            exchange = exchange_class(opts)
            self._exchanges.append((name, exchange))
            logger.info("Registered exchange: %s", name)

    @property
    def binance(self):
        """Backward-compatible property — returns the active exchange."""
        if self._active_exchange:
            return self._active_exchange
        # Return first available
        return self._exchanges[0][1] if self._exchanges else None

    async def _try_exchange(self, name: str, exchange) -> bool:
        """Try loading markets from an exchange. Returns True on success."""
        try:
            await exchange.load_markets()
            logger.info("✅ Connected to %s (%d markets)", name, len(exchange.markets))
            return True
        except Exception as e:
            error_str = str(e)
            if "451" in error_str or "restricted" in error_str.lower():
                logger.warning("❌ %s: geo-restricted (451)", name)
            elif "cloudflare" in error_str.lower() or "403" in error_str:
                logger.warning("❌ %s: blocked (403/cloudflare)", name)
            else:
                logger.warning("❌ %s: %s", name, error_str[:150])
            return False

    async def _ensure_markets(self):
        """Load markets, trying each exchange in priority order."""
        if self._markets_loaded:
            return

        errors = []
        for name, exchange in self._exchanges:
            if await self._try_exchange(name, exchange):
                self._active_exchange = exchange
                self._exchange_name = name
                self._markets_loaded = True
                return
            errors.append(name)

        raise ValueError(
            f"Could not connect to any exchange. "
            f"Tried: {', '.join(errors)}. "
            f"All were blocked or unavailable from this server region. "
            f"Consider setting EXCHANGE_PROXY env var to route through a non-restricted region."
        )

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "15m",
                          limit: int = None) -> Dict:
        """Fetch OHLCV with caching and multi-exchange fallback."""
        limit = limit or config.DEFAULT_LOOKBACK
        cache_key = f"{symbol}:{timeframe}:{limit}"

        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit: %s", cache_key)
            return cached

        try:
            if self.is_stock(symbol):
                symbol = self.convert_stock_symbol(symbol)

            await self._ensure_markets()
            exchange = self._active_exchange

            # Check if symbol exists on active exchange
            if symbol not in exchange.markets:
                # Try without the exchange-specific format
                logger.warning(
                    "Symbol %s not on %s, checking alternatives…",
                    symbol, self._exchange_name,
                )

            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

            if not ohlcv:
                raise ValueError(f"No data returned for {symbol}")

            data = {
                "timestamp": [x[0] for x in ohlcv],
                "open": [x[1] for x in ohlcv],
                "high": [x[2] for x in ohlcv],
                "low": [x[3] for x in ohlcv],
                "close": [x[4] for x in ohlcv],
                "volume": [x[5] for x in ohlcv],
            }
            self._cache.set(cache_key, data)
            return data

        except ccxt.BadSymbol:
            raise ValueError(
                f"Symbol {symbol} not found on {self._exchange_name}. "
                "Check the pair exists (e.g. BTC/USDT)."
            )
        except ccxt.NetworkError as e:
            error_str = str(e)
            # If we get a 451/blocked mid-session, reset and retry with next exchange
            if "451" in error_str or "restricted" in error_str.lower():
                logger.warning("Got 451 mid-session on %s, resetting…", self._exchange_name)
                self._markets_loaded = False
                self._active_exchange = None
                # Remove the failed exchange from the list for this session
                self._exchanges = [
                    (n, ex) for n, ex in self._exchanges
                    if n != self._exchange_name
                ]
                await self._ensure_markets()
                # Retry once
                exchange = self._active_exchange
                ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                if not ohlcv:
                    raise ValueError(f"No data returned for {symbol}")
                data = {
                    "timestamp": [x[0] for x in ohlcv],
                    "open": [x[1] for x in ohlcv],
                    "high": [x[2] for x in ohlcv],
                    "low": [x[3] for x in ohlcv],
                    "close": [x[4] for x in ohlcv],
                    "volume": [x[5] for x in ohlcv],
                }
                self._cache.set(cache_key, data)
                return data
            raise ValueError(f"Network error: {e}")
        except ccxt.ExchangeError as e:
            raise ValueError(f"Exchange error ({self._exchange_name}): {e}")
        except Exception as e:
            error_msg = str(e)
            if "does not have market symbol" in error_msg:
                raise ValueError(f"Symbol {symbol} not available on {self._exchange_name}.")
            raise ValueError(f"API error: {error_msg}")

    # ── Symbol classification ─────────────────────────────────────────

    def is_crypto(self, symbol: str) -> bool:
        return "USDT" in symbol or "/BTC" in symbol or "/ETH" in symbol

    def is_forex(self, symbol: str) -> bool:
        forex = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD",
                 "XAU", "XAG", "TRY", "BRL"]
        return any(p in symbol for p in forex)

    def is_stock(self, symbol: str) -> bool:
        return not self.is_crypto(symbol) and not self.is_forex(symbol) and "/" not in symbol

    def convert_stock_symbol(self, symbol: str) -> str:
        stock_map = {
            "AAPL": "AAPLUSDT", "TSLA": "TSLAUSDT",
            "COIN": "COINUSDT", "MSTR": "MSTRUSDT",
        }
        return stock_map.get(symbol, f"{symbol}USDT")

    async def close(self):
        """Close exchange connections and reset singleton."""
        for _, exchange in self._exchanges:
            try:
                await exchange.close()
            except Exception:
                pass
        MultiExchangeClient._instance = None
        self._initialized = False
