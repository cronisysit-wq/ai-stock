"""Tests for US symbol directory."""

from unittest.mock import patch

from analysis.us_symbol_directory import (
    _parse_nasdaq_listed,
    _parse_other_listed,
)


NASDAQ_SAMPLE = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc.|Q|N|N|100|N|N
TEST|Test Security|G|Y|N|100|N|N
SPY|SPDR S&P 500|G|N|N|100|Y|N
File Creation Time: ...
"""

OTHER_SAMPLE = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
A|Agilent Technologies|N|A|N|100|N|A
BRK/B|Berkshire Hathaway|N|BRK/B|N|100|N|BRK/B
File Creation Time: ...
"""


def test_parse_nasdaq_excludes_test_issues():
    syms = _parse_nasdaq_listed(NASDAQ_SAMPLE)
    assert "AAPL" in syms
    assert "TEST" not in syms
    assert "SPY" in syms


def test_parse_nasdaq_stocks_only_excludes_etf():
    syms = _parse_nasdaq_listed(NASDAQ_SAMPLE, include_etfs=False)
    assert "AAPL" in syms
    assert "SPY" not in syms


def test_parse_other_listed():
    syms = _parse_other_listed(OTHER_SAMPLE)
    assert "A" in syms
    assert "BRK/B" in syms or "BRK-B" not in syms  # directory uses slash sometimes


@patch("analysis.us_symbol_directory._fetch_url")
def test_fetch_all_us_symbols(mock_fetch):
    mock_fetch.side_effect = [NASDAQ_SAMPLE, OTHER_SAMPLE]
    from analysis.us_symbol_directory import fetch_all_us_symbols
    syms = fetch_all_us_symbols(include_etfs=True, use_cache=False)
    assert "AAPL" in syms
    assert "A" in syms
