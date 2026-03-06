
import pandas as pd
import numpy as np

def get_mock_data():

    df = pd.DataFrame({
        "close": np.random.random(100) * 20000
    })

    return df
