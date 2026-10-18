"""Tests for the NSE trading-hours check."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.market.nse_hours import IST, is_nse_trading_hours


class TestIsNseTradingHours:
    """Unit tests for is_nse_trading_hours."""

    def test_weekday_during_hours(self):
        """Wednesday 2026-10-21, 11:00 IST is within trading hours."""
        moment = datetime(2026, 10, 21, 11, 0, tzinfo=IST)
        assert is_nse_trading_hours(moment) is True

    def test_weekday_before_open(self):
        moment = datetime(2026, 10, 21, 9, 0, tzinfo=IST)
        assert is_nse_trading_hours(moment) is False

    def test_weekday_after_close(self):
        moment = datetime(2026, 10, 21, 15, 31, tzinfo=IST)
        assert is_nse_trading_hours(moment) is False

    def test_at_open_boundary(self):
        moment = datetime(2026, 10, 21, 9, 15, tzinfo=IST)
        assert is_nse_trading_hours(moment) is True

    def test_at_close_boundary(self):
        moment = datetime(2026, 10, 21, 15, 30, tzinfo=IST)
        assert is_nse_trading_hours(moment) is True

    def test_saturday(self):
        moment = datetime(2026, 10, 24, 11, 0, tzinfo=IST)  # Saturday
        assert is_nse_trading_hours(moment) is False

    def test_sunday(self):
        moment = datetime(2026, 10, 25, 11, 0, tzinfo=IST)  # Sunday
        assert is_nse_trading_hours(moment) is False

    def test_converts_non_ist_timezone(self):
        """A UTC time equivalent to 11:00 IST should still register as trading hours."""
        utc_moment = datetime(2026, 10, 21, 5, 30, tzinfo=ZoneInfo("UTC"))  # 11:00 IST
        assert is_nse_trading_hours(utc_moment) is True
