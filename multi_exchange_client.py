"""
Multi-exchange client — singleton with built-in caching.
"""
import ccxt.async_support as ccxt
from typing import Dict, Optional
from cache_manager import CacheManager
import config
import logging

logger = logging.getLogger(__name__)


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
        self.binance = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        self._cache = CacheManager(ttl_seconds=config.CACHE_TTL_SECONDS)
        self._markets_loaded = False

    async def _ensure_markets(self):
        if not self._markets_loaded:
            await self.binance.load_markets()
            self._markets_loaded = True

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
            ohlcv = await self.binance.fetch_ohlcv(symbol, timeframe, limit=limit)

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
                f"Symbol {symbol} not found on Binance. "
                "Check the pair exists (e.g. BTC/USDT)."
            )
        except ccxt.NetworkError as e:
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
        try:
            await self.binance.close()
        except Exception:
            pass
        MultiExchangeClient._instance = None
        self._initialized = False
