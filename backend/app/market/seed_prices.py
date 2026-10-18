"""Seed prices and per-ticker parameters for the market simulator."""

# Realistic starting prices for the default NSE watchlist (fetched from Tapetide, 2026-10-16)
SEED_PRICES: dict[str, float] = {
    "HEROMOTOCO": 5225.00,
    "BEL": 376.85,
    "PIDILITIND": 1502.80,
    "LTF": 253.85,
    "HDFCBANK": 728.85,
    "INFY": 1161.20,
    "RELIANCE": 1211.20,
    "TCS": 2465.00,
    "ICICIBANK": 1397.00,
    "TATAMOTORS": 421.05,
}

# Per-ticker GBM parameters
# sigma: annualized volatility (higher = more price movement)
# mu: annualized drift / expected return
TICKER_PARAMS: dict[str, dict[str, float]] = {
    "HEROMOTOCO": {"sigma": 0.28, "mu": 0.10},
    "BEL": {"sigma": 0.35, "mu": 0.12},  # Defence/PSU, high drift
    "PIDILITIND": {"sigma": 0.22, "mu": 0.09},
    "LTF": {"sigma": 0.32, "mu": 0.08},  # NBFC, higher volatility
    "HDFCBANK": {"sigma": 0.20, "mu": 0.09},  # Large-cap bank
    "INFY": {"sigma": 0.25, "mu": 0.08},
    "RELIANCE": {"sigma": 0.24, "mu": 0.09},
    "TCS": {"sigma": 0.22, "mu": 0.08},
    "ICICIBANK": {"sigma": 0.21, "mu": 0.09},  # Large-cap bank
    "TATAMOTORS": {"sigma": 0.38, "mu": 0.07},  # Auto, high volatility
}

# Default parameters for tickers not in the list above (dynamically added)
DEFAULT_PARAMS: dict[str, float] = {"sigma": 0.25, "mu": 0.08}

# Correlation groups for the simulator's Cholesky decomposition
# Tickers in the same group have higher intra-group correlation
CORRELATION_GROUPS: dict[str, set[str]] = {
    "banking": {"HDFCBANK", "ICICIBANK"},
    "it": {"INFY", "TCS"},
    "auto": {"HEROMOTOCO", "TATAMOTORS"},
}

# Correlation coefficients
INTRA_GROUP_CORR = 0.6  # Tickers in the same sector group move together
CROSS_GROUP_CORR = 0.3  # Between sectors / unknown tickers

# Curated universe of recognized NSE symbols, used to validate watchlist
# additions when the simulator (not Tapetide) is the active data source.
# Tapetide itself is the source of truth when it is active (a quote lookup
# either finds the symbol or it doesn't); this list exists only so the
# simulator has an equivalent, deterministic notion of "a real ticker".
NSE_SYMBOL_UNIVERSE: frozenset[str] = frozenset(
    {
        "ADANIENT", "ADANIGREEN", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT",
        "AXISBANK", "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BEL",
        "BHARTIARTL", "BPCL", "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB",
        "DMART", "DRREDDY", "EICHERMOT", "ETERNAL", "GAIL", "GRASIM",
        "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO",
        "HINDUNILVR", "ICICIBANK", "INDUSINDBK", "INFY", "IOC", "ITC",
        "JSWSTEEL", "KOTAKBANK", "LT", "LTF", "LTIM", "M&M", "MARUTI",
        "NESTLEIND", "NTPC", "ONGC", "PIDILITIND", "PNB", "POWERGRID",
        "RELIANCE", "SBILIFE", "SBIN", "SHREECEM", "SUNPHARMA", "TATACONSUM",
        "TATAMOTORS", "TATASTEEL", "TCS", "TECHM", "TITAN", "ULTRACEMCO",
        "UPL", "VEDL", "WIPRO",
    }
)
