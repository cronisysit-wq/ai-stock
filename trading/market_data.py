"""
Market data fetcher using yfinance with pandas-ta technical indicators.

Provides helpers for historical OHLCV data, latest prices, ticker info,
and a standard set of technical indicators (SMA, EMA, RSI, MACD, Bollinger
Bands, VWAP, ATR).
"""

import yfinance as yf
import pandas as pd
import pandas_ta as ta
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

    # Moving Averages
    df["sma_20"] = ta.sma(df["close"], length=20)
    df["sma_50"] = ta.sma(df["close"], length=50)
    df["ema_12"] = ta.ema(df["close"], length=12)
    df["ema_26"] = ta.ema(df["close"], length=26)

    # RSI
    df["rsi"] = ta.rsi(df["close"], length=14)

    # MACD
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None:
        df = pd.concat([df, macd], axis=1)

    # Bollinger Bands
    bbands = ta.bbands(df["close"], length=20, std=2)
    if bbands is not None:
        df = pd.concat([df, bbands], axis=1)

    # VWAP (only works for intraday with full OHLCV)
    try:
        vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
        if vwap is not None:
            df["vwap"] = vwap
    except Exception:
        pass

    # ATR for volatility
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)

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
