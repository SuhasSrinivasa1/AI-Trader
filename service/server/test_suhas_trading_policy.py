from datetime import datetime, timezone

from suhas_trading_policy import TradingPolicy, evaluate_entry


def _base_request():
    return {
        "symbol": "AAPL",
        "market": "NASDAQ",
        "direction": "long",
        "current_price": 101.0,
        "reference_price": 100.0,
        "entry_price": 101.0,
        "stop_loss": 99.0,
        "target_price": 105.0,
        "quantity": 10,
        "portfolio_value": 100000.0,
        "price_timestamp": datetime.now(timezone.utc),
        "quote_source": "verified-live-feed",
        "confirmation_source_count": 2,
        "news_checked": True,
        "technical_checked": True,
        "portfolio_checked": True,
    }


def test_valid_long_setup_is_eligible_in_paper_mode():
    result = evaluate_entry(**_base_request())
    assert result.eligible is True
    assert result.action == "BUY"
    assert result.execution_mode == "paper"
    assert result.metrics["reward_risk_ratio"] == 2.0


def test_stale_quote_is_rejected():
    request = _base_request()
    request["price_timestamp"] = datetime(2020, 1, 1, tzinfo=timezone.utc)
    result = evaluate_entry(**request)
    assert result.eligible is False
    assert result.action == "WAIT"
    assert any("stale" in reason.lower() for reason in result.reasons)


def test_chasing_is_rejected():
    request = _base_request()
    request["current_price"] = 103.0
    result = evaluate_entry(**request)
    assert result.eligible is False
    assert any("do not chase" in reason.lower() for reason in result.reasons)


def test_live_execution_falls_back_to_paper_by_default():
    request = _base_request()
    request["live_execution_requested"] = True
    result = evaluate_entry(**request)
    assert result.eligible is False
    assert result.execution_mode == "paper"
    assert any("live execution is disabled" in reason.lower() for reason in result.reasons)


def test_position_risk_limit_is_enforced():
    request = _base_request()
    request["quantity"] = 1000
    result = evaluate_entry(**request)
    assert result.eligible is False
    assert any("position risks" in reason.lower() for reason in result.reasons)


def test_policy_can_be_overridden_explicitly_for_controlled_testing():
    request = _base_request()
    request["live_execution_requested"] = True
    result = evaluate_entry(
        **request,
        policy=TradingPolicy(allow_live_execution=True),
    )
    assert result.eligible is True
    assert result.execution_mode == "live"
