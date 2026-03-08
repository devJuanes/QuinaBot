"""
QuinaBot Exchange Client — Resilient market data fetching.
- Binance: automatic endpoint fallback (api, api1, api2, api3)
- Retry with exponential backoff (5s, 10s, 30s)
- CoinGecko fallback when Binance is blocked (451)
"""
import asyncio
import logging
import os
import time
from typing import Optional

import ccxt
import pandas as pd
import requests

# --- Logging ---
logger = logging.getLogger("quinabot.exchange")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)

# --- Binance endpoints (fallback order) ---
BINANCE_ENDPOINTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]

# --- Retry policy ---
RETRY_DELAYS = [5, 10, 30]  # seconds
MAX_RETRIES = 3
BINANCE_COOLDOWN = 600  # 10 min: no retry Binance si todos dan 451

# --- State: cooldown cuando Binance da 451 ---
_binance_blocked_until = 0.0
_in_cooldown_last_fetch = False
_cooldown_entered_logged = False
_cooldown_fallback_logged = False

# --- CoinGecko symbol mapping ---
SYMBOL_TO_COINGECKO = {
    "BTC/USDT": "bitcoin",
    "ETH/USDT": "ethereum",
    "SOL/USDT": "solana",
    "BNB/USDT": "binancecoin",
    "XRP/USDT": "ripple",
    "DOGE/USDT": "dogecoin",
    "ADA/USDT": "cardano",
    "AVAX/USDT": "avalanche-2",
    "MATIC/USDT": "matic-network",
    "LINK/USDT": "chainlink",
    "DOT/USDT": "polkadot",
    "LTC/USDT": "litecoin",
    "ATOM/USDT": "cosmos",
    "UNI/USDT": "uniswap",
    "ETC/USDT": "ethereum-classic",
}


def _get_proxy_config() -> Optional[dict]:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        return {"http": proxy, "https": proxy}
    return None


def _create_binance_exchange(base_url: str, use_futures: bool = True) -> ccxt.binance:
    """Create Binance ccxt instance with custom base URL."""
    proxy = _get_proxy_config()
    api_base = f"{base_url}/api/v3"
    opts = {
        "enableRateLimit": True,
        "trust_env": True,
        "urls": {
            "api": {"public": api_base, "private": api_base},
        },
    }
    if proxy:
        opts["proxies"] = proxy
    if use_futures:
        opts["options"] = {"defaultType": "future"}
    return ccxt.binance(opts)


def _is_blocked_error(exc: Exception) -> bool:
    """Check if error is HTTP 451 (region blocked)."""
    msg = str(exc).lower()
    return "451" in msg or "restricted location" in msg or "service unavailable" in msg


async def _try_binance_once(
    symbol: str,
    timeframe: str,
    limit: int,
    use_spot: bool = False,
) -> pd.DataFrame:
    """
    Single Binance attempt (one endpoint). Returns df or raises.
    On 451: sets cooldown and raises.
    """
    global _binance_blocked_until, _cooldown_entered_logged, _in_cooldown_last_fetch
    endpoint = BINANCE_ENDPOINTS[0]
    exchange = _create_binance_exchange(endpoint, use_futures=not use_spot)
    try:
        ohlcv = await asyncio.to_thread(
            exchange.fetch_ohlcv, symbol, timeframe, limit=limit
        )
        if ohlcv:
            df = pd.DataFrame(
                ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df
    except Exception as e:
        if _is_blocked_error(e):
            _binance_blocked_until = time.time() + BINANCE_COOLDOWN
            _in_cooldown_last_fetch = True
            if not _cooldown_entered_logged:
                logger.warning("Binance blocked (451). Entering cooldown for 10 minutes.")
                _cooldown_entered_logged = True
        raise e
    return pd.DataFrame()


def get_coingecko_price(coin_id: str) -> Optional[float]:
    """
    Fetch current price from CoinGecko public API.
    https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd
    """
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coin_id, "vs_currencies": "usd"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return float(data.get(coin_id, {}).get("usd", 0))
    except Exception as e:
        logger.warning(f"CoinGecko price fetch failed: {e}")
        return None


def get_coingecko_ohlcv(coin_id: str, days: int = 1) -> pd.DataFrame:
    """
    Fetch price history from CoinGecko market_chart and convert to OHLCV.
    Returns DataFrame with timestamp, open, high, low, close, volume.
    """
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/coins/" + coin_id + "/market_chart",
            params={"vs_currency": "usd", "days": days},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        prices = data.get("prices", [])
        volumes = {t: v for t, v in data.get("total_volumes", [])}

        if not prices:
            return pd.DataFrame()

        # Build OHLCV: each point becomes a candle (open=high=low=close for simplicity)
        rows = []
        for ts_ms, price in prices:
            vol = volumes.get(ts_ms, 0)
            rows.append([ts_ms, price, price, price, price, vol])
        df = pd.DataFrame(
            rows,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        logger.warning(f"CoinGecko market_chart fetch failed: {e}")
        return pd.DataFrame()


async def fetch_market_data(
    symbol: str,
    timeframe_1m: str = "1m",
    timeframe_15m: str = "15m",
    limit_1m: int = 300,
    limit_15m: int = 200,
    use_spot: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """
    Main entry point: fetch market data with graceful degradation.
    Returns (df_1m, df_15m, source) where source is "binance" or "coingecko".
    """
    global _in_cooldown_last_fetch, _cooldown_fallback_logged, _cooldown_entered_logged
    now = time.time()
    in_cooldown = now < _binance_blocked_until

    if in_cooldown:
        _in_cooldown_last_fetch = True
        if not _cooldown_fallback_logged:
            logger.info("Using CoinGecko fallback during cooldown.")
            _cooldown_fallback_logged = True
    else:
        if _in_cooldown_last_fetch:
            logger.info("Retrying Binance after cooldown.")
            _in_cooldown_last_fetch = False
            _cooldown_fallback_logged = False
            _cooldown_entered_logged = False
        try:
            raw_1m, raw_15m = await asyncio.gather(
                _try_binance_once(symbol, timeframe_1m, limit_1m, use_spot),
                _try_binance_once(symbol, timeframe_15m, limit_15m, use_spot),
            )
            if not raw_1m.empty and not raw_15m.empty:
                return raw_1m, raw_15m, "binance"
        except Exception:
            pass  # cooldown already set by _try_binance_once if 451
    coin_id = SYMBOL_TO_COINGECKO.get(symbol, "bitcoin")
    cg_df = get_coingecko_ohlcv(coin_id, days=1)
    if cg_df.empty:
        price = get_coingecko_price(coin_id)
        if price is not None:
            # Minimal synthetic data: single row
            now_ms = int(time.time() * 1000)
            row = [now_ms, price, price, price, price, 0]
            cg_df = pd.DataFrame(
                [row],
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            cg_df["timestamp"] = pd.to_datetime(cg_df["timestamp"], unit="ms")

    if cg_df.empty:
        return pd.DataFrame(), pd.DataFrame(), "none"

    # Use same data for 1m and 15m (degraded mode)
    return cg_df, cg_df, "coingecko"


def get_default_markets() -> dict:
    """Default markets when Binance is unavailable."""
    defaults = [
        {"symbol": "BTC/USDT", "type": "future", "base": "BTC", "quote": "USDT", "label": "BTC/USDT (F)"},
        {"symbol": "ETH/USDT", "type": "future", "base": "ETH", "quote": "USDT", "label": "ETH/USDT (F)"},
        {"symbol": "SOL/USDT", "type": "future", "base": "SOL", "quote": "USDT", "label": "SOL/USDT (F)"},
    ]
    return {"markets": defaults, "futures": defaults, "spot": []}


async def get_binance_markets() -> dict:
    """Fetch available markets from Binance with endpoint fallback."""
    for endpoint in BINANCE_ENDPOINTS:
        for attempt in range(MAX_RETRIES):
            try:
                exchange = _create_binance_exchange(endpoint)
                await asyncio.to_thread(exchange.load_markets)
                futures, spot = [], []
                for sid, m in exchange.markets.items():
                    if m.get("quote") == "USDT" and m.get("type") in ("future", "swap", "linear") and m.get("active", True):
                        futures.append({"symbol": sid, "type": "future", "base": m.get("base"), "quote": "USDT"})
                for sid, m in exchange.markets.items():
                    if m.get("quote") == "USDT" and m.get("type") == "spot" and m.get("active", True):
                        spot.append({"symbol": sid, "type": "spot", "base": m.get("base"), "quote": "USDT"})
                seen = set()
                combined = []
                for x in futures[:50]:
                    if x["symbol"] not in seen:
                        seen.add(x["symbol"])
                        combined.append({**x, "label": f"{x['symbol']} (F)"})
                for x in spot[:30]:
                    if x["symbol"] not in seen:
                        seen.add(x["symbol"])
                        combined.append({**x, "label": f"{x['symbol']} (S)"})
                return {"markets": combined, "futures": futures[:30], "spot": spot[:20]}
            except Exception as e:
                if _is_blocked_error(e):
                    break
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
    return get_default_markets()
