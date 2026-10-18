"""Data models for market data."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable snapshot of a single ticker's price at a point in time.

    Carries two distinct baselines: `previous_price` (the previous *tick*,
    ~500ms/2s ago, used for the up/down flash) and `previous_close` (the
    session/day baseline, used for the watchlist's daily change %). Under
    Tapetide, `previous_close` is the exchange's real previous close; under
    the simulator (no real "yesterday" to reference), it is the price the
    ticker's current simulated session started at.
    """

    ticker: str
    price: float
    previous_price: float
    previous_close: float
    timestamp: float = field(default_factory=time.time)  # Unix seconds

    @property
    def change(self) -> float:
        """Absolute price change from previous update (tick-over-tick)."""
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        """Percentage change from previous update (tick-over-tick)."""
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def day_change(self) -> float:
        """Absolute price change from the session/day baseline."""
        return round(self.price - self.previous_close, 4)

    @property
    def day_change_percent(self) -> float:
        """Percentage change from the session/day baseline."""
        if self.previous_close == 0:
            return 0.0
        return round((self.price - self.previous_close) / self.previous_close * 100, 4)

    @property
    def direction(self) -> str:
        """'up', 'down', or 'flat', based on the tick-over-tick change."""
        if self.price > self.previous_price:
            return "up"
        elif self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        """Serialize for JSON / SSE transmission."""
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "previous_close": self.previous_close,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "day_change": self.day_change,
            "day_change_percent": self.day_change_percent,
            "direction": self.direction,
        }
