
class OrderManager:

    def __init__(self, broker):
        self.broker = broker

    def execute(self, signal, symbol, qty):

        if signal == "BUY_CALL":
            return self.broker.place_order(symbol, qty, "BUY")

        if signal == "BUY_PUT":
            return self.broker.place_order(symbol, qty, "BUY")
