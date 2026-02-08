"""
Multi-exchange client — singleton with built-in caching.
Uses Bybit (primary) with KuCoin fallback.
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
        # Primary: Bybit (no geo-restrictions)
        self._primary = ccxt.bybit({
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        # Fallback: KuCoin (no geo-restrictions)
        self._fallback = ccxt.kucoin({
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        self._active = self._primary
        self._active_name = "Bybit"
        self._cache = CacheManager(ttl_seconds=config.CACHE_TTL_SECONDS)
        self._markets_loaded = False

    @property
    def binance(self):
        """Backward compat — returns the active exchange."""
        return self._active

    async def _ensure_markets(self):
        if not self._markets_loaded:
            # Try primary (Bybit) with retry
            for attempt in range(3):
                try:
                    await self._active.load_markets()
                    self._markets_loaded = True
                    logger.info("%s markets loaded (%d symbols)", self._active_name, len(self._active.markets))
                    return
                except Exception as e:
                    logger.warning("%s markets attempt %d failed: %s", self._active_name, attempt + 1, e)
                    if attempt < 2:
                        import asyncio
                        await asyncio.sleep(2)
            # Primary failed after retries — switch to fallback (KuCoin)
            logger.warning("Switching to KuCoin fallback")
            self._active = self._fallback
            self._active_name = "KuCoin"
            await self._active.load_markets()
            self._markets_loaded = True
            logger.info("KuCoin markets loaded (%d symbols)", len(self._active.markets))

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
            ohlcv = await self._active.fetch_ohlcv(symbol, timeframe, limit=limit)

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
                f"Symbol {symbol} not found on {self._active_name}. "
                "Check the pair exists (e.g. BTC/USDT)."
            )
        except ccxt.NetworkError as e:
            raise ValueError(f"Network error: {e}")
        except ccxt.ExchangeError as e:
            raise ValueError(f"Exchange error: {e}")
        except Exception as e:
            error_msg = str(e)
            if "does not have market symbol" in error_msg:
                raise ValueError(f"Symbol {symbol} not available on {self._active_name}.")
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
        for ex in [self._primary, self._fallback]:
            try:
                await ex.close()
            except Exception:
                pass
        MultiExchangeClient._instance = None
        self._initialized = False
