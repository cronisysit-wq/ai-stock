"""Tests for trading chat."""

from unittest.mock import patch

from ai.trading_chat import extract_tickers, chat, ChatMessage


def test_extract_tickers_from_message():
    assert "NVDA" in extract_tickers("What about NVDA and AMD?")
    assert extract_tickers("Tell me about Apple", focus_ticker="AAPL") == ["AAPL"]


def test_extract_skips_common_words():
    assert "I" not in extract_tickers("I want to learn trading")


@patch("ai.trading_chat._gather_stock_context", return_value="=== AAPL ===\nPrice: $180")
@patch("ai.analyst.call_ai_stock", return_value=("Here is educational context about AAPL.", "openai"))
def test_chat_with_ai(mock_stock, mock_ctx):
    resp = chat("Tell me about AAPL", history=[], focus_ticker="AAPL")
    assert resp.ai_powered is True
    assert resp.ai_provider == "openai"
    assert "AAPL" in resp.tickers_used


@patch("ai.trading_chat._gather_stock_context", return_value="")
@patch("ai.analyst.call_ai", return_value=("RSI measures momentum.", "gemini"))
def test_chat_general_uses_gemini(mock_ai, mock_ctx):
    resp = chat("Explain the RSI indicator for beginners", history=[])
    assert resp.ai_provider == "gemini"


@patch("ai.trading_chat._gather_stock_context", return_value="")
@patch("ai.analyst.call_ai", return_value=(None, "rule-based"))
def test_chat_rule_fallback(mock_ai, mock_ctx):
    resp = chat("Explain the RSI indicator", history=[])
    assert resp.ai_powered is False
    assert "Rule-based" in resp.reply or "OPENAI" in resp.reply


def test_chat_history_included_in_prompt():
    with patch("ai.analyst.call_ai_stock", return_value=("OK", "openai")) as mock_call:
        with patch("ai.trading_chat._gather_stock_context", return_value=""):
            chat(
                "Follow up question",
                history=[
                    ChatMessage(role="user", content="First question"),
                    ChatMessage(role="assistant", content="First answer"),
                ],
            )
    prompt = mock_call.call_args[0][0]
    assert "First question" in prompt
