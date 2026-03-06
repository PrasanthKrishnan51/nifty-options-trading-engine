"""
Upstox Data Provider — advanced options analytics built on top of UpstoxBroker.

Provides: PCR, Max Pain, IV Rank, ATM strike, expiry calendar,
          option chain DataFrame, nearest option selector.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


class UpstoxDataProvider:
    def __init__(self, broker) -> None:
        self._broker = broker

    # ── Expiry helpers ────────────────────────────────────────────

    def get_nifty_expiries(self, weeks_ahead: int = 4) -> List[datetime]:
        """Return upcoming Thursday expiries for NIFTY."""
        expiries: List[datetime] = []
        today = date.today()
        days_to_thu = (3 - today.weekday()) % 7
        if days_to_thu == 0:
            days_to_thu = 7
        first_thu = today + timedelta(days=days_to_thu)
        for i in range(weeks_ahead):
            d = first_thu + timedelta(weeks=i)
            expiries.append(datetime.combine(d, datetime.min.time()))
        return expiries

    def get_nearest_expiry(self) -> datetime:
        return self.get_nifty_expiries(1)[0]

    # ── Option chain helpers ──────────────────────────────────────

    def get_option_chain_df(self, underlying: str, expiry: datetime) -> pd.DataFrame:
        """Wide-format DataFrame: one row per strike, CE/PE columns."""
        chain = self._broker.get_option_chain(underlying, expiry)
        if not chain:
            return pd.DataFrame()
        rows: Dict[float, Dict] = {}
        for c in chain:
            strike = c["strike"]
            otype  = c["option_type"]
            if strike not in rows:
                rows[strike] = {"strike": strike}
            for key in ("ltp", "oi", "volume", "iv", "delta", "theta", "vega", "gamma", "tradingsymbol"):
                rows[strike][f"{otype}_{key}"] = c.get(key, 0)
        df = pd.DataFrame(list(rows.values())).set_index("strike").sort_index()
        return df

    def get_pcr(self, underlying: str, expiry: datetime) -> Optional[float]:
        """Put-Call Ratio (by OI). >1 bearish, <1 bullish."""
        chain = self._broker.get_option_chain(underlying, expiry)
        if not chain:
            return None
        pe_oi = sum(c["oi"] for c in chain if c["option_type"] == "PE")
        ce_oi = sum(c["oi"] for c in chain if c["option_type"] == "CE")
        return round(pe_oi / ce_oi, 3) if ce_oi > 0 else None

    def get_max_pain(self, underlying: str, expiry: datetime) -> Optional[float]:
        """Max Pain — strike where total buyer loss is maximum."""
        chain = self._broker.get_option_chain(underlying, expiry)
        if not chain:
            return None
        strikes = list({c["strike"] for c in chain})
        pain: Dict[float, float] = {}
        for s in strikes:
            total = 0.0
            for c in chain:
                if c["option_type"] == "CE":
                    total += max(0.0, s - c["strike"]) * c["oi"]
                else:
                    total += max(0.0, c["strike"] - s) * c["oi"]
            pain[s] = total
        return min(pain, key=pain.get)

    def get_iv_rank(self, underlying: str, expiry: datetime,
                    lookback_iv_history: Optional[List[float]] = None) -> Optional[float]:
        """
        IV Rank = (current IV - 52w low) / (52w high - 52w low) × 100.
        Pass historical ATM IV list for accuracy, or returns raw ATM IV.
        """
        chain = self._broker.get_option_chain(underlying, expiry)
        if not chain:
            return None
        spot = self.get_atm_strike(underlying)
        if spot is None:
            return None
        atm_entries = [c for c in chain if abs(c["strike"] - spot) <= 100]
        if not atm_entries:
            return None
        current_iv = sum(c["iv"] for c in atm_entries) / len(atm_entries)
        if lookback_iv_history:
            low, high = min(lookback_iv_history), max(lookback_iv_history)
            return round((current_iv - low) / (high - low) * 100, 1) if high != low else 50.0
        return round(current_iv, 2)

    def get_atm_strike(self, underlying: str, step: int = 50) -> Optional[float]:
        """Return ATM strike for the underlying based on current LTP."""
        tick = self._broker.get_quote(underlying, "NSE")
        if not tick:
            return None
        return round(tick.ltp / step) * step

    def get_nearest_option(self, underlying: str, expiry: datetime,
                           option_type: str = "CE", otm_offset: int = 0,
                           step: int = 50) -> Optional[Dict[str, Any]]:
        """Pick the nearest OTM or ATM contract for the given side."""
        spot = self._broker.get_quote(underlying, "NSE")
        if not spot:
            return None
        atm = round(spot.ltp / step) * step
        target = atm + otm_offset * step if option_type == "CE" else atm - otm_offset * step
        chain = self._broker.get_option_chain(underlying, expiry)
        contracts = [c for c in chain if c["option_type"] == option_type]
        if not contracts:
            return None
        return min(contracts, key=lambda c: abs(c["strike"] - target))
