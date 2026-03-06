
from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):

    def __init__(self, symbol: str):
        self.symbol = symbol

    @abstractmethod
    def generate_signal(self, data: pd.DataFrame):
        pass
