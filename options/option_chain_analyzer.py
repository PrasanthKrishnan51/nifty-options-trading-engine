"""
Option Chain Analyzer — derives market sentiment metrics from option chain data.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


class OptionChainAnalyzer:
    """Compute PCR, Max Pain, IV skew, and support/resistance from an option chain."""

    def __init__(self, chain: List[Dict[str, Any]]) -> None:
        self._raw = chain
        self._df  = self._to_df(chain)

    @staticmethod
    def _to_df(chain: List[Dict[str, Any]]) -> pd.DataFrame:
        if not chain:
            return pd.DataFrame()
        df = pd.DataFrame(chain)
        for col in ("ltp", "oi", "volume", "iv", "delta", "theta", "vega", "gamma", "strike"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return df

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    def get_pcr(self) -> Optional[float]:
        """Put-Call Ratio by OI (>1 → bearish bias, <1 → bullish bias)."""
        if self._df.empty or "option_type" not in self._df.columns:
            return None
        pe_oi = self._df[self._df["option_type"] == "PE"]["oi"].sum()
        ce_oi = self._df[self._df["option_type"] == "CE"]["oi"].sum()
        return round(pe_oi / ce_oi, 3) if ce_oi > 0 else None

    def get_max_pain(self) -> Optional[float]:
        """Max Pain strike — where total option buyers lose the most at expiry."""
        if self._df.empty:
            return None
        strikes = self._df["strike"].unique()
        pain_by_strike: Dict[float, float] = {}
        for strike in strikes:
            total_pain = 0.0
            for _, row in self._df.iterrows():
                if row["option_type"] == "CE":
                    total_pain += max(0.0, strike - row["strike"]) * row["oi"]
                else:
                    total_pain += max(0.0, row["strike"] - strike) * row["oi"]
            pain_by_strike[strike] = total_pain
        return min(pain_by_strike, key=pain_by_strike.get)

    def get_atm_strike(self, spot: float, step: int = 50) -> float:
        """Return the nearest strike to spot rounded to `step`."""
        return round(spot / step) * step

    def get_pivot_table(self) -> pd.DataFrame:
        """Wide-format pivot: one row per strike, CE/PE columns side-by-side."""
        if self._df.empty:
            return pd.DataFrame()
        ce = self._df[self._df["option_type"] == "CE"].set_index("strike")[["ltp","oi","iv","delta"]].add_prefix("CE_")
        pe = self._df[self._df["option_type"] == "PE"].set_index("strike")[["ltp","oi","iv","delta"]].add_prefix("PE_")
        return ce.join(pe, how="outer").sort_index()

    def get_iv_skew(self, atm_strike: float) -> Dict[str, float]:
        """IV skew: ATM IV vs OTM put vs OTM call IV."""
        try:
            atm_ce = self._df[(self._df["strike"] == atm_strike) & (self._df["option_type"] == "CE")]["iv"].values
            atm_pe = self._df[(self._df["strike"] == atm_strike) & (self._df["option_type"] == "PE")]["iv"].values
            return {
                "atm_ce_iv": float(atm_ce[0]) if len(atm_ce) else 0.0,
                "atm_pe_iv": float(atm_pe[0]) if len(atm_pe) else 0.0,
            }
        except Exception:
            return {}

    def get_oi_buildup(self, top_n: int = 5) -> Dict[str, List[float]]:
        """Top N strikes by OI for CE and PE (potential resistance/support)."""
        if self._df.empty:
            return {"ce_resistance": [], "pe_support": []}
        ce_top = (self._df[self._df["option_type"] == "CE"]
                  .nlargest(top_n, "oi")["strike"].tolist())
        pe_top = (self._df[self._df["option_type"] == "PE"]
                  .nlargest(top_n, "oi")["strike"].tolist())
        return {"ce_resistance": ce_top, "pe_support": pe_top}
