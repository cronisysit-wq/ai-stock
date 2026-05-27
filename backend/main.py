"""
FastAPI backend for the AI Stock Trading Assistant.

Provides REST API endpoints for:
- Account and position management
- Signal generation and trade execution
- Risk management and kill switch control
- Backtesting and market data retrieval
- Audit logging and configuration

Can be run standalone: python -m backend.main
Or imported: from backend.main import app
"""

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from config.settings import get_settings
from db.database import init_db, get_db_session
from db.models import Signal, Order, AuditLog, TradeLog
from trading.broker import AlpacaBroker, LiveTradingDisabledError
from trading.market_data import get_historical_data, add_indicators, get_latest_price
from trading.strategies import get_strategy, get_all_strategies, SignalType
from trading.risk_manager import RiskManager
from trading.executor import TradeExecutor, TradingMode
from trading.backtester import Backtester
from ai.analyst import explain_signal
from datetime import datetime, date
import json
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Trading Assistant API",
    description="API for AI-assisted stock trading with risk management",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global instances (initialised on startup)
# ---------------------------------------------------------------------------

broker: Optional[AlpacaBroker] = None
risk_manager: Optional[RiskManager] = None
executor: Optional[TradeExecutor] = None


@app.on_event("startup")
async def startup_event():
    """Initialise DB, broker, risk manager and executor on startup."""
    global broker, risk_manager, executor
    init_db()
    try:
        broker = AlpacaBroker()
        logger.info("Broker initialised successfully.")
    except Exception as e:
        logger.warning(f"Could not initialize broker: {e}")
        broker = None
    risk_manager = RiskManager()
    executor = TradeExecutor(broker=broker, risk_manager=risk_manager)
    logger.info("Startup complete.")


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Health-check response."""
    status: str
    timestamp: str
    broker_connected: bool
    version: str


class AccountResponse(BaseModel):
    """Account information."""
    equity: float
    buying_power: float
    cash: float
    daily_pnl: float


class PositionResponse(BaseModel):
    """Single position."""
    symbol: str
    qty: float
    market_value: float
    unrealized_pl: float
    current_price: float
    avg_entry_price: float
    side: str


class OrderHistoryItem(BaseModel):
    """Single order record."""
    id: Optional[str] = None
    symbol: str
    qty: float
    side: str
    order_type: str
    status: str
    filled_avg_price: Optional[float] = None
    created_at: Optional[str] = None


class SignalRequest(BaseModel):
    """Request body for signal generation."""
    strategy_name: str = Field(..., description="Strategy to use: ma_crossover, rsi, vwap")


class SignalResponse(BaseModel):
    """Generated signal with AI explanation."""
    ticker: str
    signal: str
    confidence: float
    strategy: str
    explanation: str
    ai_explanation: str
    indicators: Dict[str, Any]


class PlaceOrderRequest(BaseModel):
    """Request body for placing an order."""
    ticker: str
    qty: float
    side: str = Field(..., description="buy or sell")
    order_type: str = Field(default="market", description="market or limit")
    mode: str = Field(default="manual", description="manual, semi_auto, or auto")
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None


class PlaceOrderResponse(BaseModel):
    """Response for a placed order."""
    success: bool
    action_taken: str
    message: str
    order_result: Optional[Dict[str, Any]] = None


class KillSwitchRequest(BaseModel):
    """Request body for kill-switch toggle."""
    engage: bool


class KillSwitchResponse(BaseModel):
    """Kill-switch toggle response."""
    kill_switch_engaged: bool
    message: str


class RiskStatusResponse(BaseModel):
    """Current risk metrics."""
    kill_switch_engaged: bool
    daily_pnl: Optional[float] = None
    max_daily_loss: float
    trades_today: int
    max_trades_per_day: int
    details: Dict[str, Any] = {}


class AuditLogResponse(BaseModel):
    """Single audit log entry."""
    id: Optional[int] = None
    event_type: str
    details: str
    level: str
    created_at: Optional[str] = None


class BacktestRequest(BaseModel):
    """Request body for running a backtest."""
    symbol: str
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    strategy_name: str
    initial_capital: float = 10000.0
    position_size_pct: float = 10.0


class BacktestResponse(BaseModel):
    """Backtest results summary."""
    total_return: float
    total_return_pct: float
    win_rate: float
    max_drawdown: float
    num_trades: int
    winning_trades: int
    losing_trades: int
    avg_profit: float
    avg_loss: float
    avg_pnl: float
    sharpe_ratio: float
    initial_capital: float
    final_capital: float
    equity_curve: List[float]
    dates: List[str]
    trades: List[Dict[str, Any]]


class SettingsResponse(BaseModel):
    """Current application settings (API keys redacted)."""
    enable_live_trading: bool
    enable_auto_mode: bool
    max_daily_loss: float
    max_position_size: float
    max_trades_per_day: int
    stop_loss_pct: float
    take_profit_pct: float
    cooldown_seconds: int
    is_paper_trading: bool
    is_live_trading: bool
    alpaca_base_url: str


class MarketDataResponse(BaseModel):
    """Historical market data with indicators."""
    ticker: str
    data: List[Dict[str, Any]]
    length: int


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _log_audit(event_type: str, details: str, level: str = "INFO") -> None:
    """Persist an audit log entry to the database."""
    try:
        session = next(get_db_session())
        log = AuditLog(
            event_type=event_type,
            details=details,
            level=level,
            created_at=datetime.utcnow(),
        )
        session.add(log)
        session.commit()
    except Exception as exc:
        logger.error(f"Failed to write audit log: {exc}")


def _parse_trading_mode(mode_str: str) -> TradingMode:
    """Convert a string mode to the TradingMode enum."""
    mapping = {
        "manual": TradingMode.MANUAL,
        "semi_auto": TradingMode.SEMI_AUTO,
        "auto": TradingMode.AUTO,
    }
    mode = mapping.get(mode_str.lower())
    if mode is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{mode_str}'. Use: manual, semi_auto, auto",
        )
    return mode


# ---------------------------------------------------------------------------
# Mock / demo data helpers (used when broker is None)
# ---------------------------------------------------------------------------

_MOCK_ACCOUNT = {
    "equity": 100000.0,
    "buying_power": 200000.0,
    "cash": 100000.0,
    "daily_pnl": 0.0,
}

_MOCK_POSITIONS: List[Dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "qty": 10,
        "market_value": 1750.0,
        "unrealized_pl": 25.50,
        "current_price": 175.0,
        "avg_entry_price": 172.45,
        "side": "long",
    },
    {
        "symbol": "MSFT",
        "qty": 5,
        "market_value": 2100.0,
        "unrealized_pl": -12.30,
        "current_price": 420.0,
        "avg_entry_price": 422.46,
        "side": "long",
    },
]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

# 1. Health check -------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Return service health status."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        broker_connected=broker is not None,
        version="1.0.0",
    )


# 2. Account info -------------------------------------------------------

@app.get("/api/account", response_model=AccountResponse, tags=["Account"])
async def get_account():
    """Get account information from the broker."""
    try:
        if broker is None:
            _log_audit("account_query", "Using mock account data (broker not connected)")
            return AccountResponse(**_MOCK_ACCOUNT)
        acct = broker.get_account()
        _log_audit("account_query", json.dumps({"equity": acct.get("equity")}))
        return AccountResponse(
            equity=float(acct.get("equity", 0)),
            buying_power=float(acct.get("buying_power", 0)),
            cash=float(acct.get("cash", 0)),
            daily_pnl=float(acct.get("daily_pnl", 0)),
        )
    except Exception as e:
        logger.error(f"Error fetching account: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 3. Positions -----------------------------------------------------------

@app.get("/api/positions", response_model=List[PositionResponse], tags=["Account"])
async def get_positions():
    """Get current positions."""
    try:
        if broker is None:
            _log_audit("positions_query", "Using mock positions (broker not connected)")
            return [PositionResponse(**p) for p in _MOCK_POSITIONS]
        positions = broker.get_positions()
        _log_audit("positions_query", json.dumps({"count": len(positions)}))
        return [
            PositionResponse(
                symbol=p.get("symbol", ""),
                qty=float(p.get("qty", 0)),
                market_value=float(p.get("market_value", 0)),
                unrealized_pl=float(p.get("unrealized_pl", 0)),
                current_price=float(p.get("current_price", 0)),
                avg_entry_price=float(p.get("avg_entry_price", 0)),
                side=p.get("side", "long"),
            )
            for p in positions
        ]
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 4. Orders --------------------------------------------------------------

@app.get("/api/orders", response_model=List[OrderHistoryItem], tags=["Orders"])
async def get_orders(status: Optional[str] = Query(None, description="Filter by status")):
    """Get order history from the broker."""
    try:
        if broker is None:
            _log_audit("orders_query", "No broker connected; returning empty list")
            return []
        orders = broker.get_orders(status=status or "all", limit=50)
        _log_audit("orders_query", json.dumps({"status_filter": status, "count": len(orders)}))
        return [
            OrderHistoryItem(
                id=o.get("id"),
                symbol=o.get("symbol", ""),
                qty=float(o.get("qty", 0)),
                side=o.get("side", ""),
                order_type=o.get("order_type", "market"),
                status=o.get("status", ""),
                filled_avg_price=float(o["filled_avg_price"]) if o.get("filled_avg_price") else None,
                created_at=str(o.get("created_at", "")),
            )
            for o in orders
        ]
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 5. Generate signal -----------------------------------------------------

@app.post("/api/signals/{ticker}", response_model=SignalResponse, tags=["Signals"])
async def generate_signal(ticker: str, body: SignalRequest):
    """Generate a trading signal for the given ticker using the specified strategy."""
    try:
        strategy = get_strategy(body.strategy_name)
        if strategy is None:
            raise HTTPException(status_code=400, detail=f"Unknown strategy: {body.strategy_name}")

        df = get_historical_data(ticker)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No market data available for {ticker}")

        df = add_indicators(df)
        signal_result = strategy.generate_signal(df)

        # AI explanation
        ai_explanation = ""
        try:
            ai_explanation = explain_signal(signal_result, df)
        except Exception as ai_err:
            logger.warning(f"AI explanation failed: {ai_err}")
            ai_explanation = "AI explanation unavailable."

        # Persist signal to DB
        try:
            session = next(get_db_session())
            db_signal = Signal(
                ticker=ticker.upper(),
                strategy=body.strategy_name,
                signal_type=signal_result.signal.value if hasattr(signal_result.signal, "value") else str(signal_result.signal),
                confidence=signal_result.confidence,
                explanation=signal_result.explanation,
                created_at=datetime.utcnow(),
            )
            session.add(db_signal)
            session.commit()
        except Exception as db_err:
            logger.warning(f"Could not persist signal to DB: {db_err}")

        _log_audit(
            "signal_generated",
            json.dumps({
                "ticker": ticker,
                "strategy": body.strategy_name,
                "signal": signal_result.signal.value if hasattr(signal_result.signal, "value") else str(signal_result.signal),
                "confidence": signal_result.confidence,
            }),
        )

        return SignalResponse(
            ticker=ticker.upper(),
            signal=signal_result.signal.value if hasattr(signal_result.signal, "value") else str(signal_result.signal),
            confidence=signal_result.confidence,
            strategy=signal_result.strategy,
            explanation=signal_result.explanation,
            ai_explanation=ai_explanation,
            indicators=signal_result.indicators or {},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating signal for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 6. Place order ----------------------------------------------------------

@app.post("/api/orders", response_model=PlaceOrderResponse, tags=["Orders"])
async def place_order(body: PlaceOrderRequest):
    """Place a trade order through the executor."""
    try:
        mode = _parse_trading_mode(body.mode)

        # Build a minimal SignalResult for the executor
        signal_type = SignalType.BUY if body.side.lower() == "buy" else SignalType.SELL
        from trading.strategies import SignalResult
        signal = SignalResult(
            signal=signal_type,
            confidence=1.0,
            strategy="manual",
            explanation=f"Manual {body.side} order for {body.ticker}",
            indicators={},
        )

        result = executor.execute_signal(
            signal=signal,
            ticker=body.ticker.upper(),
            qty=body.qty,
            mode=mode,
        )

        _log_audit(
            "order_placed",
            json.dumps({
                "ticker": body.ticker,
                "side": body.side,
                "qty": body.qty,
                "mode": body.mode,
                "success": result.success,
                "action": result.action_taken,
            }),
        )

        return PlaceOrderResponse(
            success=result.success,
            action_taken=result.action_taken,
            message=result.message,
            order_result=result.order_result,
        )
    except LiveTradingDisabledError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 7. Cancel order ---------------------------------------------------------

@app.delete("/api/orders/{order_id}", tags=["Orders"])
async def cancel_order(order_id: str):
    """Cancel an open order."""
    try:
        if broker is None:
            raise HTTPException(status_code=503, detail="Broker not connected")
        broker.cancel_order(order_id)
        _log_audit("order_cancelled", json.dumps({"order_id": order_id}))
        return {"status": "cancelled", "order_id": order_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 8. Kill switch ----------------------------------------------------------

@app.post("/api/kill-switch", response_model=KillSwitchResponse, tags=["Risk"])
async def toggle_kill_switch(body: KillSwitchRequest):
    """Engage or disengage the emergency kill switch."""
    try:
        if body.engage:
            risk_manager.engage_kill_switch()
            if broker is not None:
                broker.engage_kill_switch()
            _log_audit("kill_switch", json.dumps({"action": "engaged"}), level="WARNING")
            return KillSwitchResponse(
                kill_switch_engaged=True,
                message="Kill switch ENGAGED — all trading halted.",
            )
        else:
            risk_manager.disengage_kill_switch()
            if broker is not None:
                broker.disengage_kill_switch()
            _log_audit("kill_switch", json.dumps({"action": "disengaged"}), level="WARNING")
            return KillSwitchResponse(
                kill_switch_engaged=False,
                message="Kill switch disengaged — trading resumed.",
            )
    except Exception as e:
        logger.error(f"Error toggling kill switch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 9. Risk status ----------------------------------------------------------

@app.get("/api/risk-status", response_model=RiskStatusResponse, tags=["Risk"])
async def get_risk_status():
    """Get current risk metrics."""
    try:
        status = risk_manager.get_risk_status()
        settings = get_settings()
        _log_audit("risk_status_query", json.dumps({"kill_switch": status.get("kill_switch_engaged", False)}))
        return RiskStatusResponse(
            kill_switch_engaged=status.get("kill_switch_engaged", False),
            daily_pnl=status.get("daily_pnl"),
            max_daily_loss=settings.MAX_DAILY_LOSS,
            trades_today=status.get("trades_today", 0),
            max_trades_per_day=settings.MAX_TRADES_PER_DAY,
            details=status,
        )
    except Exception as e:
        logger.error(f"Error fetching risk status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 10. Audit logs ----------------------------------------------------------

@app.get("/api/logs", response_model=List[AuditLogResponse], tags=["System"])
async def get_logs(
    limit: int = Query(50, ge=1, le=500, description="Max number of logs"),
    level: Optional[str] = Query(None, description="Filter by log level"),
):
    """Get recent audit log entries."""
    try:
        session = next(get_db_session())
        query = session.query(AuditLog).order_by(AuditLog.created_at.desc())
        if level:
            query = query.filter(AuditLog.level == level.upper())
        logs = query.limit(limit).all()
        return [
            AuditLogResponse(
                id=log.id,
                event_type=log.event_type,
                details=log.details or "",
                level=log.level or "INFO",
                created_at=str(log.created_at) if log.created_at else None,
            )
            for log in logs
        ]
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 11. Backtest -------------------------------------------------------------

@app.post("/api/backtest", response_model=BacktestResponse, tags=["Backtest"])
async def run_backtest(body: BacktestRequest):
    """Run a backtest for the given parameters."""
    try:
        bt = Backtester()
        result = bt.run(
            symbol=body.symbol.upper(),
            start=body.start_date,
            end=body.end_date,
            strategy_name=body.strategy_name,
            initial_capital=body.initial_capital,
            position_size_pct=body.position_size_pct,
        )

        _log_audit(
            "backtest_run",
            json.dumps({
                "symbol": body.symbol,
                "strategy": body.strategy_name,
                "start": body.start_date,
                "end": body.end_date,
                "total_return_pct": result.total_return_pct,
            }),
        )

        return BacktestResponse(
            total_return=result.total_return,
            total_return_pct=result.total_return_pct,
            win_rate=result.win_rate,
            max_drawdown=result.max_drawdown,
            num_trades=result.num_trades,
            winning_trades=result.winning_trades,
            losing_trades=result.losing_trades,
            avg_profit=result.avg_profit,
            avg_loss=result.avg_loss,
            avg_pnl=result.avg_pnl,
            sharpe_ratio=result.sharpe_ratio,
            initial_capital=result.initial_capital,
            final_capital=result.final_capital,
            equity_curve=result.equity_curve,
            dates=[str(d) for d in result.dates],
            trades=[t if isinstance(t, dict) else vars(t) for t in result.trades],
        )
    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 12. Settings -------------------------------------------------------------

@app.get("/api/settings", response_model=SettingsResponse, tags=["System"])
async def get_current_settings():
    """Get current application settings (API keys redacted)."""
    try:
        settings = get_settings()
        _log_audit("settings_query", "Settings retrieved (keys redacted)")
        return SettingsResponse(
            enable_live_trading=settings.ENABLE_LIVE_TRADING,
            enable_auto_mode=settings.ENABLE_AUTO_MODE,
            max_daily_loss=settings.MAX_DAILY_LOSS,
            max_position_size=settings.MAX_POSITION_SIZE,
            max_trades_per_day=settings.MAX_TRADES_PER_DAY,
            stop_loss_pct=settings.STOP_LOSS_PCT,
            take_profit_pct=settings.TAKE_PROFIT_PCT,
            cooldown_seconds=settings.COOLDOWN_SECONDS,
            is_paper_trading=settings.is_paper_trading,
            is_live_trading=settings.is_live_trading,
            alpaca_base_url=settings.ALPACA_BASE_URL,
        )
    except Exception as e:
        logger.error(f"Error fetching settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 13. Market data ----------------------------------------------------------

@app.get("/api/market-data/{ticker}", response_model=MarketDataResponse, tags=["Market Data"])
async def get_market_data(ticker: str):
    """Get historical market data with technical indicators for a ticker."""
    try:
        df = get_historical_data(ticker.upper())
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No data available for {ticker}")

        df = add_indicators(df)

        # Convert DataFrame to list of dicts for JSON serialisation
        records = []
        for idx, row in df.iterrows():
            record: Dict[str, Any] = {"date": str(idx)}
            for col in df.columns:
                val = row[col]
                # Handle NaN values
                if hasattr(val, "__float__"):
                    val = float(val)
                    if val != val:  # NaN check
                        val = None
                record[col] = val
            records.append(record)

        _log_audit("market_data_query", json.dumps({"ticker": ticker, "rows": len(records)}))
        return MarketDataResponse(
            ticker=ticker.upper(),
            data=records,
            length=len(records),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching market data for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
