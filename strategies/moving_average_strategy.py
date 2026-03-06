
import pandas as pd
from strategies.base_strategy import BaseStrategy

class MovingAverageStrategy(BaseStrategy):

    def __init__(self, symbol, short_window=9, long_window=21):
        super().__init__(symbol)
        self.short_window = short_window
        self.long_window = long_window

    def generate_signal(self, data: pd.DataFrame):

        data['short_ma'] = data['close'].rolling(self.short_window).mean()
        data['long_ma'] = data['close'].rolling(self.long_window).mean()

        if data['short_ma'].iloc[-1] > data['long_ma'].iloc[-1]:
            return "BUY_CALL"

        if data['short_ma'].iloc[-1] < data['long_ma'].iloc[-1]:
            return "BUY_PUT"

        return "HOLD"
