"""
Moving Average Strategy — compatibility wrapper around MACrossoverStrategy.
"""
from strategies.additional_strategies import MACrossoverStrategy

class MovingAverageStrategy(MACrossoverStrategy):
    """Alias for MACrossoverStrategy (kept for backwards compatibility)."""
    def __init__(self, symbol: str = "NIFTY", short_window: int = 9, long_window: int = 21):
        super().__init__(fast_period=short_window, slow_period=long_window)
