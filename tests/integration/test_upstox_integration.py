"""
Integration tests for Upstox broker (require real credentials).

Set SKIP_INTEGRATION=true (default) to skip in CI.
Run: SKIP_INTEGRATION=false pytest tests/integration/ -v
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import pytest

SKIP = os.getenv("SKIP_INTEGRATION", "true").lower() == "true"
skip_msg = "Set SKIP_INTEGRATION=false to run live integration tests."


@pytest.mark.skipif(SKIP, reason=skip_msg)
class TestUpstoxIntegration:
    @pytest.fixture(scope="class")
    def broker(self):
        from broker.upstox.upstox_broker import UpstoxBroker
        b = UpstoxBroker()
        assert b.connect(), "Broker connection failed — check .env credentials."
        yield b
        b.disconnect()

    def test_profile(self, broker):
        profile = broker.get_profile()
        assert "client_id" in profile or "name" in profile

    def test_get_nifty_ltp(self, broker):
        ltp = broker.get_ltp("NIFTY", "NSE")
        assert ltp is not None and ltp > 10_000

    def test_get_funds(self, broker):
        funds = broker.get_funds()
        assert "available" in funds and funds["total"] >= 0

    def test_get_positions(self, broker):
        positions = broker.get_positions()
        assert isinstance(positions, list)

    def test_market_status(self, broker):
        status = broker.get_market_status()
        assert isinstance(status, dict)
