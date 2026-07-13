"""Suhas trading profile guardrails.

This module is intentionally isolated from the upstream execution engine. It validates
trade ideas using current quote metadata, risk controls, and confirmation requirements.
It does not fetch market data or place broker orders.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from config import (
    SUHAS_ALLOW_LIVE_EXECUTION,
    SUHAS_MAX_CHASE_PCT,
    SUHAS_MAX_PRICE_AGE_SECONDS,
    SUHAS_MAX_RISK_PER_TRADE_PCT,
    SUHAS_MIN_CONFIRMATION_SOURCES,
    SUHAS_MIN_REWARD_RISK_RATIO,
    SUHAS_TRADING_PROFILE_ENABLED,
)

Direction = Literal["long", "short"]

SUPPORTED_MARKETS = {"NSE", "BSE", "NYSE", "NASDAQ"}
REQUIRED_CONFIRMATIONS = ("news_checked", "technical_checked", "portfolio_checked")


@dataclass(frozen=True)
class TradingPolicy:
    enabled: bool = SUHAS_TRADING_PROFILE_ENABLED
    allow_live_execution: bool = SUHAS_ALLOW_LIVE_EXECUTION
    max_risk_per_trade_pct: float = SUHAS_MAX_RISK_PER_TRADE_PCT
    min_reward_risk_ratio: float = SUHAS_MIN_REWARD_RISK_RATIO
    max_chase_pct: float = SUHAS_MAX_CHASE_PCT
    max_price_age_seconds: int = SUHAS_MAX_PRICE_AGE_SECONDS
    min_confirmation_sources: int = SUHAS_MIN_CONFIRMATION_SOURCES


@dataclass(frozen=True)
class EntryEvaluation:
    action: str
    eligible: bool
    execution_mode: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "eligible": self.eligible,
            "execution_mode": self.execution_mode,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "metrics": self.metrics,
        }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def evaluate_entry(
    *,
    symbol: str,
    market: str,
    direction: Direction,
    current_price: float,
    reference_price: float,
    entry_price: float,
    stop_loss: float,
    target_price: float,
    quantity: float,
    portfolio_value: float,
    price_timestamp: datetime,
    quote_source: str,
    confirmation_source_count: int,
    news_checked: bool,
    technical_checked: bool,
    portfolio_checked: bool,
    live_execution_requested: bool = False,
    now: datetime | None = None,
    policy: TradingPolicy | None = None,
) -> EntryEvaluation:
    """Evaluate whether an entry satisfies the Suhas trading profile.

    ``reference_price`` is the planned trigger/support/resistance reference used to
    detect chasing. Market data acquisition and broker execution remain separate.
    """

    policy = policy or TradingPolicy()
    reasons: list[str] = []
    warnings: list[str] = [
        "Policy validation only: this endpoint does not place broker orders.",
        "Revalidate live price, news, and market conditions immediately before execution.",
    ]

    market = market.upper().strip()
    symbol = symbol.upper().strip()
    quote_source = quote_source.strip()

    if not policy.enabled:
        reasons.append("Suhas trading profile is disabled.")

    if not symbol:
        reasons.append("Symbol is required.")
    if market not in SUPPORTED_MARKETS:
        reasons.append(f"Unsupported market: {market or 'blank'}.")

    numeric_values = {
        "current_price": current_price,
        "reference_price": reference_price,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target_price": target_price,
        "quantity": quantity,
        "portfolio_value": portfolio_value,
    }
    for name, value in numeric_values.items():
        if value <= 0:
            reasons.append(f"{name} must be greater than zero.")

    if not quote_source:
        reasons.append("A live quote source is required.")

    now_utc = _as_utc(now or datetime.now(timezone.utc))
    quote_utc = _as_utc(price_timestamp)
    quote_age_seconds = max(0.0, (now_utc - quote_utc).total_seconds())
    if quote_age_seconds > policy.max_price_age_seconds:
        reasons.append(
            f"Quote is stale ({quote_age_seconds:.0f}s old; maximum {policy.max_price_age_seconds}s)."
        )

    if confirmation_source_count < policy.min_confirmation_sources:
        reasons.append(
            "Insufficient independent confirmation sources "
            f"({confirmation_source_count}; minimum {policy.min_confirmation_sources})."
        )

    confirmations = {
        "news_checked": news_checked,
        "technical_checked": technical_checked,
        "portfolio_checked": portfolio_checked,
    }
    missing_confirmations = [name for name in REQUIRED_CONFIRMATIONS if not confirmations[name]]
    if missing_confirmations:
        reasons.append("Missing confirmations: " + ", ".join(missing_confirmations) + ".")

    risk_per_share = 0.0
    reward_per_share = 0.0
    if min(entry_price, stop_loss, target_price) > 0:
        if direction == "long":
            if not stop_loss < entry_price < target_price:
                reasons.append("Long setup must satisfy stop_loss < entry_price < target_price.")
            risk_per_share = entry_price - stop_loss
            reward_per_share = target_price - entry_price
        else:
            if not target_price < entry_price < stop_loss:
                reasons.append("Short setup must satisfy target_price < entry_price < stop_loss.")
            risk_per_share = stop_loss - entry_price
            reward_per_share = entry_price - target_price

    reward_risk_ratio = (
        reward_per_share / risk_per_share if risk_per_share > 0 and reward_per_share > 0 else 0.0
    )
    if reward_risk_ratio < policy.min_reward_risk_ratio:
        reasons.append(
            f"Reward/risk ratio {reward_risk_ratio:.2f} is below the minimum "
            f"{policy.min_reward_risk_ratio:.2f}."
        )

    position_risk = max(0.0, risk_per_share) * max(0.0, quantity)
    risk_pct_of_capital = (
        (position_risk / portfolio_value) * 100.0 if portfolio_value > 0 else 0.0
    )
    if risk_pct_of_capital > policy.max_risk_per_trade_pct:
        reasons.append(
            f"Position risks {risk_pct_of_capital:.2f}% of portfolio; maximum is "
            f"{policy.max_risk_per_trade_pct:.2f}%."
        )

    chase_pct = 0.0
    if reference_price > 0:
        if direction == "long":
            chase_pct = ((current_price - reference_price) / reference_price) * 100.0
        else:
            chase_pct = ((reference_price - current_price) / reference_price) * 100.0
        if chase_pct > policy.max_chase_pct:
            reasons.append(
                f"Do not chase: price moved {chase_pct:.2f}% beyond the reference level; "
                f"maximum is {policy.max_chase_pct:.2f}%."
            )

    execution_mode = "live" if live_execution_requested else "paper"
    if live_execution_requested and not policy.allow_live_execution:
        execution_mode = "paper"
        reasons.append("Live execution is disabled by policy; use paper mode.")

    eligible = not reasons
    action = "BUY" if eligible and direction == "long" else "SELL" if eligible else "WAIT"

    return EntryEvaluation(
        action=action,
        eligible=eligible,
        execution_mode=execution_mode,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        metrics={
            "quote_age_seconds": round(quote_age_seconds, 2),
            "reward_risk_ratio": round(reward_risk_ratio, 3),
            "risk_pct_of_capital": round(risk_pct_of_capital, 3),
            "chase_pct": round(chase_pct, 3),
            "position_risk": round(position_risk, 2),
        },
    )
