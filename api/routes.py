"""
FastAPI REST API — 10 endpoints for monitoring and controlling the trading engine.

Swagger UI available at: http://localhost:8000/docs
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Nifty Options Trading Engine",
    description="REST API for monitoring and controlling the algorithmic trading system.",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# Global live trader reference (set by main.py)
_live_trader = None


def set_live_trader(trader) -> None:
    global _live_trader
    _live_trader = trader


def _require_trader():
    if _live_trader is None:
        raise HTTPException(status_code=503, detail="Live trader not running.")
    return _live_trader


# ── Response models ───────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    paper_trading: bool
    broker_connected: bool
    timestamp: str
    open_positions: int

class PositionResponse(BaseModel):
    position_id: str
    symbol: str
    quantity: int
    entry_price: float
    current_pnl: float
    pnl_pct: float
    stop_loss: float
    target: float
    strategy: str
    opened_at: str

class DailyStatsResponse(BaseModel):
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    trades_taken: int
    max_loss_breached: bool

class StrategyInfo(BaseModel):
    name: str
    type: str
    enabled: bool
    parameters: Dict[str, Any]

class ToggleRequest(BaseModel):
    enabled: bool


# ── Endpoints ─────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health():
    """System health check including broker connection status."""
    from config.settings import config
    trader = _live_trader
    return HealthResponse(
        status="running" if trader else "idle",
        paper_trading=config.trading.paper_trading,
        broker_connected=trader._broker.is_connected if trader else False,
        timestamp=datetime.now().isoformat(),
        open_positions=len(trader.portfolio.open_positions) if trader else 0,
    )


@app.get("/positions", response_model=List[PositionResponse], tags=["Trading"])
def get_positions():
    """All currently open positions with live P&L."""
    trader = _require_trader()
    result = []
    for pos in trader.portfolio.open_positions:
        result.append(PositionResponse(
            position_id=pos.position_id,
            symbol=pos.symbol,
            quantity=pos.quantity,
            entry_price=pos.entry_price,
            current_pnl=round(pos.pnl, 2),
            pnl_pct=round(pos.pnl_pct, 2),
            stop_loss=pos.stop_loss,
            target=pos.target,
            strategy=pos.strategy_name,
            opened_at=pos.opened_at.isoformat(),
        ))
    return result


@app.get("/daily-stats", response_model=DailyStatsResponse, tags=["Trading"])
def daily_stats():
    """Today's P&L, trade count, and risk limit status."""
    trader = _require_trader()
    stats = trader.risk.daily_stats
    return DailyStatsResponse(
        realized_pnl=stats.realized_pnl,
        unrealized_pnl=stats.unrealized_pnl,
        total_pnl=stats.total_pnl,
        trades_taken=stats.trades_taken,
        max_loss_breached=stats.max_loss_breached,
    )


@app.get("/strategies", response_model=List[StrategyInfo], tags=["Strategies"])
def get_strategies():
    """List all registered strategies and their configuration."""
    trader = _require_trader()
    return [StrategyInfo(**s) for s in trader.strategy_manager.info()]


@app.post("/strategies/{name}/toggle", tags=["Strategies"])
def toggle_strategy(name: str, body: ToggleRequest):
    """Enable or disable a specific strategy by name."""
    trader = _require_trader()
    sm = trader.strategy_manager
    if name not in sm.strategies:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found.")
    if body.enabled:
        sm.enable(name)
    else:
        sm.disable(name)
    return {"name": name, "enabled": body.enabled}


@app.post("/exit/{position_id}", tags=["Trading"])
def exit_position(position_id: str):
    """Manually close a specific position."""
    trader = _require_trader()
    positions = {p.position_id: p for p in trader.portfolio.open_positions}
    if position_id not in positions:
        raise HTTPException(status_code=404, detail="Position not found.")
    pos = positions[position_id]
    success = trader._execution.close_position(pos, "MANUAL")
    if not success:
        raise HTTPException(status_code=500, detail="Failed to close position.")
    ltp = trader._broker.get_ltp(pos.symbol) or pos.entry_price
    trader.portfolio.close_position(position_id, ltp, "MANUAL")
    return {"status": "closed", "position_id": position_id, "pnl": pos.pnl}


@app.post("/exit-all", tags=["Trading"])
def exit_all():
    """Emergency square-off — close all open positions immediately."""
    trader = _require_trader()
    count = 0
    for pos in list(trader.portfolio.open_positions):
        ltp = trader._broker.get_ltp(pos.symbol) or pos.entry_price
        trader._execution.close_position(pos, "MANUAL_ALL")
        trader.portfolio.close_position(pos.position_id, ltp, "MANUAL_ALL")
        count += 1
    return {"status": "all_closed", "positions_closed": count}


@app.get("/portfolio-summary", tags=["Portfolio"])
def portfolio_summary():
    """Full portfolio summary including net worth and win rate."""
    trader = _require_trader()
    return trader.portfolio.summary()


@app.get("/trades", tags=["Portfolio"])
def get_trades():
    """Closed trade history for today's session."""
    trader = _require_trader()
    trades = trader.portfolio.closed_trades
    return [
        {
            "trade_id":    t.trade_id,
            "symbol":      t.symbol,
            "strategy":    t.strategy_name,
            "entry_price": t.entry_price,
            "exit_price":  t.exit_price,
            "quantity":    t.quantity,
            "pnl":         round(t.pnl, 2),
            "pnl_pct":     round(t.pnl_pct, 2),
            "exit_reason": t.exit_reason,
            "entry_time":  t.entry_time.isoformat() if t.entry_time else None,
            "exit_time":   t.exit_time.isoformat() if t.exit_time else None,
        }
        for t in trades
    ]
