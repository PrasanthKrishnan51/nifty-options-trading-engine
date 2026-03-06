"""
Option Selector — picks the best strike/expiry given a trading signal.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from core.models import OptionType, Signal

logger = logging.getLogger(__name__)


class OptionSelector:
    """
    Selects the optimal option contract for execution.

    Strategy:
      - ATM or nearest OTM strike based on signal direction.
      - Nearest weekly expiry (Thursday for NIFTY).
      - Filters by minimum OI and maximum bid-ask spread.
    """

    def __init__(self, otm_offset: int = 0, min_oi: int = 50_000,
                 max_spread_pct: float = 2.0) -> None:
        self.otm_offset    = otm_offset    # number of strikes OTM (0 = ATM)
        self.min_oi        = min_oi
        self.max_spread_pct = max_spread_pct

    def select(self, chain: List[Dict[str, Any]], signal: Signal,
               spot: float, step: int = 50) -> Optional[Dict[str, Any]]:
        """
        Return the best option contract dict from chain for the given signal.
        Returns None if no suitable contract found.
        """
        if not chain:
            return None

        opt_type = "CE" if signal.option_type == OptionType.CE else "PE"
        contracts = [c for c in chain if c.get("option_type") == opt_type]

        if not contracts:
            return None

        # Filter by liquidity
        contracts = [c for c in contracts if c.get("oi", 0) >= self.min_oi]

        # Filter by spread
        filtered = []
        for c in contracts:
            ltp = c.get("ltp", 0)
            ask = c.get("ask", ltp)
            bid = c.get("bid", ltp)
            spread_pct = (ask - bid) / ltp * 100 if ltp > 0 else 100
            if spread_pct <= self.max_spread_pct:
                filtered.append(c)

        if not filtered:
            filtered = contracts  # relax spread constraint if nothing passes

        # Find target strike
        atm = round(spot / step) * step
        if opt_type == "CE":
            target_strike = atm + self.otm_offset * step
        else:
            target_strike = atm - self.otm_offset * step

        # Pick closest strike
        best = min(filtered, key=lambda c: abs(c.get("strike", 0) - target_strike))
        logger.info("Selected: %s %s strike=%.0f ltp=%.2f oi=%d",
                    opt_type, best.get("tradingsymbol",""), best.get("strike",0),
                    best.get("ltp",0), best.get("oi",0))
        return best

    @staticmethod
    def next_expiry(n: int = 0) -> datetime:
        """Return the n-th upcoming Thursday expiry."""
        today = datetime.now().date()
        days_until_thu = (3 - today.weekday()) % 7
        if days_until_thu == 0 and datetime.now().hour >= 15:
            days_until_thu = 7
        base = today + timedelta(days=days_until_thu + n * 7)
        return datetime.combine(base, datetime.min.time())
