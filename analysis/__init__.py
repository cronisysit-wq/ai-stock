# Analysis package — stock analysis and ranking engine

from analysis.universe import (
    get_universe,
    get_sector_for,
    get_robinhood_universe,
    fetch_sp500_full,
)

__all__ = [
    "get_universe",
    "get_sector_for",
    "get_robinhood_universe",
    "fetch_sp500_full",
]

# Lazy export for full directory
def get_us_symbol_count(include_etfs: bool = True) -> int:
    from analysis.us_symbol_directory import get_symbol_count
    return get_symbol_count(include_etfs=include_etfs)
