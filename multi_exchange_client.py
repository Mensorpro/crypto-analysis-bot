"""
Multi-exchange client — singleton with built-in caching.

Handles Binance geo-restriction (451) by:
  1. Trying alternate Binance API hosts (api1–api4)
  2. Falling back to Bybit if all Binance endpoints fail
"""
import ccxt.async_support as ccxt
from typing import Dict, Optional, List
from cache_manager import CacheManager
import config
import logging
import os

logger = logging.getLogger(__name__)

# Alternate Binance REST endpoints (same data, different CDN edges)
BINANCE_HOSTS = [
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://api4.binance.com",
    "https://api.binance.com",
]

# Optional user-defined proxy (e.g. SOCKS5 or HTTP proxy)
EXCHANGE_PROXY = os.getenv("EXCHANGE_PROXY", "")


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
        self._active_exchange = None  # Will be set on first use
        self._exchange_name = None

        # Build exchange instances
        self._binance_instances: List = []
        self._bybit = None
        self._setup_exchanges()

    def _setup_exchanges(self):
        """Create exchange instances with various endpoints."""
        # Create a Binance instance for each alternate host
        for host in BINANCE_HOSTS:
            opts = {
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
                "urls": {
                    "api": {
                        "public": host + "/api/v3",
                        "private": host + "/api/v3",
                        "sapi": host + "/sapi/v1",
                        "sapiV2": host + "/sapi/v2",
                        "sapiV3": host + "/sapi/v3",
                        "sapiV4": host + "/sapi/v4",
                    }
                },
            }
            if EXCHANGE_PROXY:
                opts["proxies"] = {
                    "http": EXCHANGE_PROXY,
                    "https": EXCHANGE_PROXY,
                }
            exchange = ccxt.binance(opts)
            self._binance_instances.append(exchange)

        # Bybit fallback (no geo-restriction for public data)
        bybit_opts = {
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        if EXCHANGE_PROXY:
            bybit_opts["proxies"] = {
                "http": EXCHANGE_PROXY,
                "https": EXCHANGE_PROXY,
            }
        self._bybit = ccxt.bybit(bybit_opts)

    @property
    def binance(self):
        """Backward-compatible property — returns the active exchange."""
        if self._active_exchange:
            return self._active_exchange
        return self._binance_instances[0] if self._binance_instances else self._bybit

    async def _try_load_markets(self, exchange, name: str) -> bool:
        """Try loading markets from an exchange. Returns True on success."""
        try:
            await exchange.load_markets()
            logger.info("Successfully connected to %s", name)
            return True
        except Exception as e:
            error_str = str(e)
            if "451" in error_str or "restricted location" in error_str.lower():
                logger.warning("%s blocked (451 geo-restriction), trying next…", name)
            else:
                logger.warning("%s failed: %s", name, error_str[:120])
            return False

    async def _ensure_markets(self):
        """Load markets, trying all Binance endpoints then Bybit."""
        if self._markets_loaded:
            return

        # Try each Binance endpoint
        for i, exchange in enumerate(self._binance_instances):
            host = BINANCE_HOSTS[i]
            if await self._try_load_markets(exchange, f"Binance ({host})"):
                self._active_exchange = exchange
                self._exchange_name = f"Binance ({host})"
                self._markets_loaded = True
                return

        # All Binance endpoints failed — try Bybit
        logger.warning("All Binance endpoints blocked. Falling back to Bybit…")
        if await self._try_load_markets(self._bybit, "Bybit"):
            self._active_exchange = self._bybit
            self._exchange_name = "Bybit"
            self._markets_loaded = True
            return

        raise ValueError(
            "Could not connect to any exchange. "
            "All Binance endpoints returned 451 (geo-restricted) and Bybit also failed. "
            "Consider setting EXCHANGE_PROXY env var to a proxy in a non-restricted region."
        )

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "15m",
                          limit: int = None) -> Dict:
        """Fetch OHLCV with caching."""
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
                f"Symbol {symbol} not found on {self._exchange_name or 'exchange'}. "
                "Check the pair exists (e.g. BTC/USDT)."
            )
        except ccxt.NetworkError as e:
            error_str = str(e)
            # If we get a 451 mid-session, reset and retry
            if "451" in error_str or "restricted location" in error_str.lower():
                logger.warning("Got 451 mid-session, resetting exchange…")
                self._markets_loaded = False
                self._active_exchange = None
                await self._ensure_markets()
                # Retry once after switching
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
            raise ValueError(f"Exchange error: {e}")
        except Exception as e:
            error_msg = str(e)
            if "does not have market symbol" in error_msg:
                raise ValueError(f"Symbol {symbol} not available.")
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
        for exchange in self._binance_instances:
            try:
                await exchange.close()
            except Exception:
                pass
        try:
            if self._bybit:
                await self._bybit.close()
        except Exception:
            pass
        MultiExchangeClient._instance = None
        self._initialized = False
