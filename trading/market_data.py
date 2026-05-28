"""
Market data fetcher using yfinance with pandas-based technical indicators.

Provides helpers for historical OHLCV data, latest prices, ticker info,
and a standard set of technical indicators (SMA, EMA, RSI, MACD, Bollinger
Bands, VWAP, ATR).
"""

import yfinance as yf
import pandas as pd
import numpy as np
import logging
from typing import Optional
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def get_historical_data(
    symbol: str,
    start: str = None,
    end: str = None,
    period: str = "6mo",
    interval: str = "1d",
) -> pd.DataFrame:
    """Fetch historical OHLCV data for a symbol.

    Args:
        symbol: Ticker symbol (e.g. "AAPL").
        start: Start date string (YYYY-MM-DD). If provided with *end*,
               overrides *period*.
        end: End date string (YYYY-MM-DD).
        period: yfinance period string (default "6mo").
        interval: Bar interval (default "1d").

    Returns:
        DataFrame with columns: open, high, low, close, volume.
        Empty DataFrame on error.
    """
    try:
        ticker = yf.Ticker(symbol)
        if start and end:
            df = ticker.history(start=start, end=end, interval=interval)
        else:
            df = ticker.history(period=period, interval=interval)

        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return pd.DataFrame()

        df.index = pd.to_datetime(df.index)
        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        # Drop any extra columns like Dividends, Stock Splits
        df = df[["open", "high", "low", "close", "volume"]]
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators to a DataFrame with OHLCV data.

    Indicators added:
        - SMA 20 & 50
        - EMA 12 & 26
        - RSI (14)
        - MACD (12, 26, 9)
        - Bollinger Bands (20, 2σ)
        - VWAP (intraday only)
        - ATR (14)

    Args:
        df: DataFrame with columns open, high, low, close, volume.

    Returns:
        A copy of *df* with indicator columns appended.
    """
    if df.empty:
        return df

    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Moving Averages
    df["sma_20"] = close.rolling(20).mean()
    df["sma_50"] = close.rolling(50).mean()
    df["ema_12"] = close.ewm(span=12, adjust=False).mean()
    df["ema_26"] = close.ewm(span=26, adjust=False).mean()

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((loss == 0) & (gain > 0), 100.0)
    rsi = rsi.mask((gain == 0) & (loss > 0), 0.0)
    rsi = rsi.mask((gain == 0) & (loss == 0), 50.0)
    df["rsi"] = rsi

    # MACD
    df["macd"] = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # Bollinger Bands
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df["bb_upper"] = bb_mid + 2 * bb_std
    df["bb_lower"] = bb_mid - 2 * bb_std
    df["bb_mid"] = bb_mid

    # VWAP (rolling approximation for daily bars)
    typical_price = (high + low + close) / 3
    vol_sum = volume.rolling(20).sum()
    df["vwap"] = (typical_price * volume).rolling(20).sum() / vol_sum.replace(0, np.nan)

    # ATR for volatility
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["atr_pct"] = df["atr"] / close * 100

    return df


def get_latest_price(symbol: str) -> Optional[float]:
    """Get the latest price for a symbol (prefers live quote when available)."""
    quote = get_live_quote(symbol)
    if quote and quote.get("price"):
        return float(quote["price"])
    return None


def get_live_quote(symbol: str) -> dict:
    """
    Best-effort live or near-live quote via yfinance.

    Returns dict: price, source (live|market|intraday|daily_close), as_of (ISO str).
    """
    symbol = symbol.strip().upper()
    result = {"symbol": symbol, "price": None, "source": "unavailable", "as_of": None}

    try:
        ticker = yf.Ticker(symbol)

        # 1) fast_info last price (closest to real-time on free tier)
        try:
            fi = ticker.fast_info
            for attr in ("last_price", "lastPrice"):
                val = getattr(fi, attr, None) if hasattr(fi, attr) else fi.get(attr) if hasattr(fi, "get") else None
                if val and float(val) > 0:
                    result["price"] = round(float(val), 4)
                    result["source"] = "live"
                    result["as_of"] = datetime.now(timezone.utc).isoformat()
                    return result
        except Exception:
            pass

        # 2) info dict — regular / pre / post market
        try:
            info = ticker.info or {}
            for key in (
                "regularMarketPrice",
                "currentPrice",
                "postMarketPrice",
                "preMarketPrice",
                "bid",
            ):
                val = info.get(key)
                if val and float(val) > 0:
                    result["price"] = round(float(val), 4)
                    result["source"] = "market"
                    ts = info.get("regularMarketTime") or info.get("postMarketTime")
                    if ts:
                        try:
                            result["as_of"] = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
                        except Exception:
                            result["as_of"] = datetime.now(timezone.utc).isoformat()
                    else:
                        result["as_of"] = datetime.now(timezone.utc).isoformat()
                    return result
        except Exception:
            pass

        # 3) Intraday 1m bar (today's last trade)
        try:
            intraday = ticker.history(period="1d", interval="1m", prepost=True)
            if intraday is not None and not intraday.empty:
                col = "Close" if "Close" in intraday.columns else "close"
                px = float(intraday[col].iloc[-1])
                if px > 0:
                    result["price"] = round(px, 4)
                    result["source"] = "intraday"
                    idx = intraday.index[-1]
                    if hasattr(idx, "to_pydatetime"):
                        dt = idx.to_pydatetime()
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        result["as_of"] = dt.isoformat()
                    else:
                        result["as_of"] = datetime.now(timezone.utc).isoformat()
                    return result
        except Exception:
            pass

        # 4) Daily close fallback
        daily = ticker.history(period="5d", interval="1d")
        if daily is not None and not daily.empty:
            col = "Close" if "Close" in daily.columns else "close"
            px = float(daily[col].iloc[-1])
            if px > 0:
                result["price"] = round(px, 4)
                result["source"] = "daily_close"
                idx = daily.index[-1]
                if hasattr(idx, "to_pydatetime"):
                    dt = idx.to_pydatetime()
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    result["as_of"] = dt.isoformat()
                return result
    except Exception as e:
        logger.debug("get_live_quote failed for %s: %s", symbol, e)

    return result


def get_ticker_info(symbol: str) -> dict:
    """Get basic fundamental info about a ticker.

    Returns:
        Dictionary with keys: symbol, name, sector, industry, market_cap,
        pe_ratio, dividend_yield, fifty_two_week_high, fifty_two_week_low.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return {
            "symbol": symbol,
            "name": info.get("longName", info.get("shortName", symbol)),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE", None),
            "dividend_yield": info.get("dividendYield", None),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh", None),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow", None),
        }
    except Exception as e:
        logger.error(f"Error getting ticker info for {symbol}: {e}")
        return {"symbol": symbol, "name": symbol}
