"""SQLAlchemy ORM models — skips setup gracefully if sqlalchemy not installed."""
from __future__ import annotations
import os
from datetime import datetime

try:
    from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine
    from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trading.db")
    _engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}
                            if "sqlite" in DATABASE_URL else {})
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

    class Base(DeclarativeBase):
        pass

    class TradeRecord(Base):
        __tablename__ = "trades"
        id          = Column(Integer, primary_key=True, index=True)
        trade_id    = Column(String(64), unique=True, index=True)
        symbol      = Column(String(64)); strategy    = Column(String(64))
        option_type = Column(String(4));  entry_price = Column(Float)
        exit_price  = Column(Float);      quantity    = Column(Integer)
        pnl         = Column(Float);      pnl_pct     = Column(Float)
        exit_reason = Column(String(32)); entry_time  = Column(DateTime)
        exit_time   = Column(DateTime);   created_at  = Column(DateTime, default=datetime.utcnow)

    class PositionRecord(Base):
        __tablename__ = "positions"
        id          = Column(Integer, primary_key=True)
        position_id = Column(String(64), unique=True, index=True)
        symbol      = Column(String(64)); strategy    = Column(String(64))
        quantity    = Column(Integer);    entry_price = Column(Float)
        exit_price  = Column(Float, nullable=True)
        stop_loss   = Column(Float);      target      = Column(Float)
        status      = Column(String(16)); pnl         = Column(Float, default=0)
        opened_at   = Column(DateTime, default=datetime.utcnow)
        closed_at   = Column(DateTime, nullable=True)

    class DailyStatsRecord(Base):
        __tablename__ = "daily_stats"
        id             = Column(Integer, primary_key=True)
        date           = Column(String(12), unique=True, index=True)
        realized_pnl   = Column(Float, default=0)
        unrealized_pnl = Column(Float, default=0)
        trades_taken   = Column(Integer, default=0)
        max_loss_hit   = Column(Boolean, default=False)
        created_at     = Column(DateTime, default=datetime.utcnow)

    def init_db() -> None:
        Base.metadata.create_all(bind=_engine)

    def get_session() -> Session:
        return SessionLocal()

    _SQLALCHEMY_AVAILABLE = True

except ImportError:
    _SQLALCHEMY_AVAILABLE = False
    def init_db() -> None:
        pass
    def get_session():
        raise RuntimeError("SQLAlchemy not installed. Run: pip install sqlalchemy")
