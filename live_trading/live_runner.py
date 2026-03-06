
import pandas as pd
from data.market_data import get_mock_data

class LiveTrader:

    def __init__(self, strategy, broker, order_manager):
        self.strategy = strategy
        self.broker = broker
        self.order_manager = order_manager

    def run(self):

        data = get_mock_data()

        signal = self.strategy.generate_signal(data)

        if signal != "HOLD":
            print("Executing trade:", signal)
            self.order_manager.execute(signal, self.strategy.symbol, 50)
