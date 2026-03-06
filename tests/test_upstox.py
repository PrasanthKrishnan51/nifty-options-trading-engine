"""
Unit tests for Upstox broker adapter.

Tests cover:
  - Instrument key resolution
  - Auth URL generation
  - Order model mapping
  - Status mapping
  - Option chain data structure
  - Data provider utilities (PCR, max pain, ATM strike)
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.models import Order, OrderSide, OrderStatus, OrderType


# ─────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def upstox_broker():
    """Create UpstoxBroker without connecting to real API."""
    from broker.upstox.upstox_broker import UpstoxBroker
    broker = UpstoxBroker()
    broker._connected = True
    broker._access_token = "fake_token_for_testing"
    broker._set_auth_header()
    return broker


@pytest.fixture
def sample_option_chain():
    """Mock option chain data matching Upstox response structure."""
    return [
        {
            "instrument_key": "NSE_FO|49999",
            "tradingsymbol":  "NIFTY24JAN22000CE",
            "strike":         22000.0,
            "option_type":    "CE",
            "expiry":         "2024-01-25",
            "ltp":   150.0, "bid": 148.0, "ask": 152.0,
            "iv":    18.5,  "delta": 0.52, "theta": -8.2,
            "vega":  12.0,  "gamma": 0.001,
            "oi":    500000, "volume": 12000,
        },
        {
            "instrument_key": "NSE_FO|50001",
            "tradingsymbol":  "NIFTY24JAN22000PE",
            "strike":         22000.0,
            "option_type":    "PE",
            "expiry":         "2024-01-25",
            "ltp":   145.0, "bid": 143.0, "ask": 147.0,
            "iv":    19.1,  "delta": -0.48, "theta": -7.9,
            "vega":  11.8,  "gamma": 0.001,
            "oi":    620000, "volume": 9500,
        },
        {
            "instrument_key": "NSE_FO|49997",
            "tradingsymbol":  "NIFTY24JAN21950CE",
            "strike":         21950.0,
            "option_type":    "CE",
            "expiry":         "2024-01-25",
            "ltp":   180.0, "bid": 178.0, "ask": 182.0,
            "iv":    17.8,  "delta": 0.61, "theta": -7.5,
            "vega":  11.2,  "gamma": 0.0012,
            "oi":    350000, "volume": 8000,
        },
        {
            "instrument_key": "NSE_FO|50003",
            "tradingsymbol":  "NIFTY24JAN21950PE",
            "strike":         21950.0,
            "option_type":    "PE",
            "expiry":         "2024-01-25",
            "ltp":   115.0, "bid": 113.0, "ask": 117.0,
            "iv":    20.2,  "delta": -0.39, "theta": -6.8,
            "vega":  10.5,  "gamma": 0.0009,
            "oi":    280000, "volume": 6200,
        },
    ]


# ─────────────────────────────────────────────
#  UpstoxBroker — Instrument Resolution
# ─────────────────────────────────────────────

class TestInstrumentKeyResolution:

    def test_nifty_index_key(self, upstox_broker):
        key = upstox_broker.get_instrument_key("NIFTY")
        assert key == "NSE_INDEX|Nifty 50"

    def test_nifty50_index_key(self, upstox_broker):
        key = upstox_broker.get_instrument_key("NIFTY 50")
        assert key == "NSE_INDEX|Nifty 50"

    def test_banknifty_index_key(self, upstox_broker):
        key = upstox_broker.get_instrument_key("BANKNIFTY")
        assert key == "NSE_INDEX|Nifty Bank"

    def test_finnifty_index_key(self, upstox_broker):
        key = upstox_broker.get_instrument_key("FINNIFTY")
        assert key == "NSE_INDEX|Nifty Fin Service"

    def test_sensex_index_key(self, upstox_broker):
        key = upstox_broker.get_instrument_key("SENSEX", "BSE")
        assert key == "BSE_INDEX|SENSEX"

    def test_unknown_symbol_fallback(self, upstox_broker):
        """Unknown symbols should produce a fallback key, not None."""
        key = upstox_broker.get_instrument_key("RELIANCE", "NSE")
        assert key is not None
        assert "RELIANCE" in key

    def test_instrument_map_lookup(self, upstox_broker):
        """If token_map is populated, it should be used."""
        upstox_broker._token_map["NIFTY24JAN22000CE"] = "NSE_FO|49999"
        key = upstox_broker.get_instrument_key("NIFTY24JAN22000CE", "NFO")
        assert key == "NSE_FO|49999"

    def test_case_insensitive_lookup(self, upstox_broker):
        upstox_broker._token_map["RELIANCE"] = "NSE_EQ|2885"
        key = upstox_broker.get_instrument_key("reliance", "NSE")
        assert key == "NSE_EQ|2885"


# ─────────────────────────────────────────────
#  UpstoxBroker — Auth
# ─────────────────────────────────────────────

class TestUpstoxAuth:

    def test_auth_url_contains_client_id(self, upstox_broker):
        from config.settings import config
        config.upstox.api_key = "test_api_key"
        url = upstox_broker._build_auth_url("test_api_key", "https://127.0.0.1/")
        assert "test_api_key" in url
        assert "response_type=code" in url
        assert "https://api.upstox.com" in url

    def test_connect_with_no_token_returns_false(self):
        """connect() should return False gracefully when no token is available."""
        from broker.upstox.upstox_broker import UpstoxBroker
        from config.settings import config
        config.upstox.access_token = None
        config.upstox.rtoken = None
        broker = UpstoxBroker()
        result = broker.connect()
        assert result is False
        assert broker.is_connected is False


# ─────────────────────────────────────────────
#  UpstoxBroker — Order Mapping
# ─────────────────────────────────────────────

class TestUpstoxOrderMapping:

    def test_raw_to_order_complete(self, upstox_broker):
        raw = {
            "order_id":       "ord_001",
            "tradingsymbol":  "NIFTY24JAN22000CE",
            "exchange":       "NFO",
            "transaction_type": "BUY",
            "order_type":     "MARKET",
            "quantity":       50,
            "price":          0.0,
            "trigger_price":  0.0,
            "average_price":  152.5,
            "filled_quantity": 50,
            "status":         "complete",
            "tag":            "test_tag",
        }
        order = upstox_broker._raw_to_order(raw)
        assert order.broker_order_id == "ord_001"
        assert order.symbol == "NIFTY24JAN22000CE"
        assert order.side == OrderSide.BUY
        assert order.status == OrderStatus.COMPLETE
        assert order.filled_qty == 50
        assert order.avg_price == 152.5

    def test_raw_to_order_rejected(self, upstox_broker):
        raw = {
            "order_id": "ord_002",
            "tradingsymbol": "NIFTY24JAN22000PE",
            "exchange": "NFO",
            "transaction_type": "SELL",
            "quantity": 50,
            "price": 0,
            "trigger_price": 0,
            "average_price": 0,
            "filled_quantity": 0,
            "status": "rejected",
            "status_message": "Insufficient margin",
        }
        order = upstox_broker._raw_to_order(raw)
        assert order.status == OrderStatus.REJECTED
        assert order.error_message == "Insufficient margin"

    def test_status_map_coverage(self, upstox_broker):
        """All known Upstox status strings should map to valid OrderStatus."""
        test_statuses = [
            "complete", "open", "cancelled", "rejected",
            "trigger pending", "open pending", "validation pending",
        ]
        for s in test_statuses:
            result = upstox_broker._STATUS_MAP.get(s)
            assert result is not None, f"Status '{s}' not in STATUS_MAP"
            assert isinstance(result, OrderStatus)

    def test_order_type_map_complete(self, upstox_broker):
        """All OrderType enum values should be in _ORDER_TYPE_MAP."""
        for ot in (OrderType.MARKET, OrderType.LIMIT, OrderType.SL, OrderType.SL_M):
            assert ot in upstox_broker._ORDER_TYPE_MAP

    def test_product_map(self, upstox_broker):
        assert upstox_broker._PRODUCT_MAP["MIS"] == "I"
        assert upstox_broker._PRODUCT_MAP["NRML"] == "D"
        assert upstox_broker._PRODUCT_MAP["CNC"] == "D"


# ─────────────────────────────────────────────
#  UpstoxBroker — Mocked API calls
# ─────────────────────────────────────────────

class TestUpstoxAPICalls:

    def test_get_quote_returns_tick(self, upstox_broker):
        mock_response = {
            "status": "success",
            "data": {
                "NSE_INDEX|Nifty 50": {
                    "last_price": 22150.75,
                    "volume":     1_234_567,
                    "oi":         0,
                    "depth": {
                        "buy":  [{"price": 22149.0, "quantity": 100}],
                        "sell": [{"price": 22152.0, "quantity": 100}],
                    },
                }
            },
        }
        with patch.object(upstox_broker, "_get", return_value=mock_response):
            tick = upstox_broker.get_quote("NIFTY", "NSE")
        assert tick is not None
        assert tick.ltp == 22150.75
        assert tick.bid == 22149.0
        assert tick.ask == 22152.0

    def test_get_quote_failure_returns_none(self, upstox_broker):
        with patch.object(upstox_broker, "_get", return_value=None):
            tick = upstox_broker.get_quote("NIFTY", "NSE")
        assert tick is None

    def test_get_funds_parses_correctly(self, upstox_broker):
        mock_response = {
            "status": "success",
            "data": {"equity": {
                "available_margin": 250_000.0,
                "used_margin":      50_000.0,
                "net_margin":       300_000.0,
            }},
        }
        with patch.object(upstox_broker, "_get", return_value=mock_response):
            funds = upstox_broker.get_funds()
        assert funds["available"] == 250_000.0
        assert funds["used"] == 50_000.0
        assert funds["total"] == 300_000.0

    def test_place_order_success(self, upstox_broker):
        upstox_broker._token_map["NIFTY24JAN22000CE"] = "NSE_FO|49999"
        mock_response = {
            "status": "success",
            "data": {"order_id": "upstox_ord_12345"},
        }
        with patch.object(upstox_broker, "_post", return_value=mock_response):
            order = Order(
                symbol="NIFTY24JAN22000CE",
                exchange="NFO",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=50,
            )
            result = upstox_broker.place_order(order)
        assert result.status == OrderStatus.OPEN
        assert result.broker_order_id == "upstox_ord_12345"

    def test_place_order_rejected(self, upstox_broker):
        upstox_broker._token_map["NIFTY24JAN22000CE"] = "NSE_FO|49999"
        mock_response = {
            "status": "error",
            "message": "Insufficient margin",
        }
        with patch.object(upstox_broker, "_post", return_value=mock_response):
            order = Order(
                symbol="NIFTY24JAN22000CE",
                exchange="NFO",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=50,
            )
            result = upstox_broker.place_order(order)
        assert result.status == OrderStatus.REJECTED
        assert "margin" in (result.error_message or "").lower()

    def test_cancel_order_success(self, upstox_broker):
        mock_response = {"status": "success", "data": {"order_id": "ord_001"}}
        with patch.object(upstox_broker, "_delete", return_value=mock_response):
            result = upstox_broker.cancel_order("ord_001")
        assert result is True

    def test_cancel_order_failure(self, upstox_broker):
        with patch.object(upstox_broker, "_delete", return_value=None):
            result = upstox_broker.cancel_order("ord_bad")
        assert result is False

    def test_get_order_status(self, upstox_broker):
        mock_response = {
            "status": "success",
            "data": {"status": "complete"},
        }
        with patch.object(upstox_broker, "_get", return_value=mock_response):
            status = upstox_broker.get_order_status("ord_001")
        assert status == OrderStatus.COMPLETE

    def test_get_positions_filters_zero_qty(self, upstox_broker):
        mock_response = {
            "status": "success",
            "data": [
                {"tradingsymbol": "NIFTY24CE", "exchange": "NFO", "quantity": 50, "average_price": 150.0},
                {"tradingsymbol": "NIFTY24PE", "exchange": "NFO", "quantity": 0,  "average_price": 0.0},
            ],
        }
        with patch.object(upstox_broker, "_get", return_value=mock_response):
            positions = upstox_broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "NIFTY24CE"

    def test_get_historical_data_structure(self, upstox_broker):
        mock_response = {
            "status": "success",
            "data": {"candles": [
                ["2024-01-15T09:15:00+05:30", 21980.0, 22050.0, 21950.0, 22020.0, 125000, 0],
                ["2024-01-15T09:16:00+05:30", 22020.0, 22080.0, 22000.0, 22060.0, 98000,  0],
                ["2024-01-15T09:17:00+05:30", 22060.0, 22120.0, 22040.0, 22100.0, 112000, 0],
            ]},
        }
        from datetime import timedelta
        with patch.object(upstox_broker, "_get", return_value=mock_response):
            df = upstox_broker.get_historical_data(
                "NIFTY", "NSE", "minute",
                datetime(2024, 1, 15, 9, 15),
                datetime(2024, 1, 15, 9, 30),
            )
        assert not df.empty
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 3
        assert df["close"].iloc[-1] == 22100.0

    def test_get_option_chain_structure(self, upstox_broker, sample_option_chain):
        mock_api_response = {
            "status": "success",
            "data": [
                {
                    "strike_price": 22000.0,
                    "call_options": {
                        "instrument_key": "NSE_FO|49999",
                        "tradingsymbol":  "NIFTY24JAN22000CE",
                        "market_data": {
                            "ltp": 150.0, "bid_price": 148.0, "ask_price": 152.0,
                            "oi": 500000, "volume": 12000,
                        },
                        "option_greeks": {
                            "iv": 18.5, "delta": 0.52, "theta": -8.2, "vega": 12.0, "gamma": 0.001,
                        },
                    },
                    "put_options": {
                        "instrument_key": "NSE_FO|50001",
                        "tradingsymbol":  "NIFTY24JAN22000PE",
                        "market_data": {
                            "ltp": 145.0, "bid_price": 143.0, "ask_price": 147.0,
                            "oi": 620000, "volume": 9500,
                        },
                        "option_greeks": {
                            "iv": 19.1, "delta": -0.48, "theta": -7.9, "vega": 11.8, "gamma": 0.001,
                        },
                    },
                },
            ],
        }
        with patch.object(upstox_broker, "_get", return_value=mock_api_response):
            chain = upstox_broker.get_option_chain("NIFTY", datetime(2024, 1, 25))

        assert len(chain) == 2
        ce_entry = next(c for c in chain if c["option_type"] == "CE")
        pe_entry = next(c for c in chain if c["option_type"] == "PE")

        assert ce_entry["strike"] == 22000.0
        assert ce_entry["ltp"] == 150.0
        assert ce_entry["iv"] == 18.5
        assert ce_entry["delta"] == 0.52
        assert pe_entry["oi"] == 620000


# ─────────────────────────────────────────────
#  UpstoxDataProvider
# ─────────────────────────────────────────────

class TestUpstoxDataProvider:

    @pytest.fixture
    def provider(self, upstox_broker, sample_option_chain):
        from data.providers.upstox_data import UpstoxDataProvider
        prov = UpstoxDataProvider(upstox_broker)
        return prov, sample_option_chain

    def test_get_nifty_expiries_returns_thursdays(self, upstox_broker):
        from data.providers.upstox_data import UpstoxDataProvider
        prov = UpstoxDataProvider(upstox_broker)
        expiries = prov.get_nifty_expiries(weeks_ahead=3)
        assert len(expiries) == 3
        for exp in expiries:
            assert exp.weekday() == 3, f"{exp} is not a Thursday"

    def test_pcr_calculation(self, provider):
        prov, chain = provider
        with patch.object(prov._broker, "get_option_chain", return_value=chain):
            pcr = prov.get_pcr("NIFTY", datetime(2024, 1, 25))
        # PE OI = 620k + 280k = 900k, CE OI = 500k + 350k = 850k
        expected_pcr = (620_000 + 280_000) / (500_000 + 350_000)
        assert pcr is not None
        assert abs(pcr - round(expected_pcr, 3)) < 0.001

    def test_max_pain_calculation(self, provider):
        prov, chain = provider
        with patch.object(prov._broker, "get_option_chain", return_value=chain):
            max_pain = prov.get_max_pain("NIFTY", datetime(2024, 1, 25))
        assert max_pain is not None
        assert max_pain in [21950.0, 22000.0]  # Must be one of the strikes

    def test_option_chain_df_structure(self, provider):
        prov, chain = provider
        with patch.object(prov._broker, "get_option_chain", return_value=chain):
            df = prov.get_option_chain_df("NIFTY", datetime(2024, 1, 25))
        assert not df.empty
        assert "strike" in df.columns
        assert "CE_ltp" in df.columns
        assert "PE_ltp" in df.columns
        assert "CE_oi" in df.columns
        assert "PE_oi" in df.columns

    def test_get_atm_strike_rounds_to_50(self, provider):
        from core.models import Tick
        prov, _ = provider
        mock_tick = Tick(symbol="NIFTY", ltp=22075.3)
        with patch.object(prov._broker, "get_quote", return_value=mock_tick):
            atm = prov.get_atm_strike("NIFTY")
        assert atm == 22100.0  # 22075 rounds to nearest 50 = 22100

    def test_get_nearest_option_atm(self, provider):
        prov, chain = provider
        mock_tick = MagicMock()
        mock_tick.ltp = 21990.0  # Closest to 22000
        with patch.object(prov._broker, "get_quote", return_value=mock_tick), \
             patch.object(prov._broker, "get_option_chain", return_value=chain):
            opt = prov.get_nearest_option("NIFTY", datetime(2024, 1, 25), "CE", otm_offset=0)
        assert opt is not None
        assert opt["option_type"] == "CE"


# ─────────────────────────────────────────────
#  Broker Factory
# ─────────────────────────────────────────────

class TestBrokerFactory:

    def test_factory_returns_upstox(self):
        from broker.factory import get_broker
        from broker.upstox.upstox_broker import UpstoxBroker
        broker = get_broker("upstox")
        assert isinstance(broker, UpstoxBroker)

    def test_factory_lists_all_brokers(self):
        from broker.factory import list_brokers
        brokers = list_brokers()
        assert "upstox" in brokers
        assert "zerodha" in brokers
        assert "angelone" in brokers
        assert "fyers" in brokers

    def test_factory_raises_on_unknown_broker(self):
        from broker.factory import get_broker
        with pytest.raises(ValueError, match="Unknown broker"):
            get_broker("unknown_broker_xyz")

    def test_factory_is_case_insensitive(self):
        from broker.factory import get_broker
        from broker.upstox.upstox_broker import UpstoxBroker
        broker = get_broker("UPSTOX")
        assert isinstance(broker, UpstoxBroker)
