"""
Configuration Module

配置和环境变量加载
"""

import os
from pathlib import Path

# Load environment variables from .env file in project root
env_path = Path(__file__).parent.parent.parent / ".env"
from dotenv import load_dotenv

load_dotenv(env_path)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# ==================== Configuration ====================

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Cache / Redis
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
REDIS_URL = os.getenv("REDIS_URL", "").strip()
REDIS_PREFIX = os.getenv("REDIS_PREFIX", "ai_trader").strip() or "ai_trader"

# API Keys
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "demo")
ADANOS_API_KEY = os.getenv("ADANOS_API_KEY", "").strip()

# Market data endpoints
ADANOS_API_BASE_URL = os.getenv("ADANOS_API_BASE_URL", "https://api.adanos.org").strip().rstrip("/")
# Hyperliquid public info endpoint (used for crypto quotes; no API key required)
HYPERLIQUID_API_URL = os.getenv("HYPERLIQUID_API_URL", "https://api.hyperliquid.xyz/info")

# CORS
CORS_ORIGINS = os.getenv("CLAWTRADER_CORS_ORIGINS", "").split(",") if os.getenv("CLAWTRADER_CORS_ORIGINS") else ["http://localhost:3000"]

# Rewards
SIGNAL_PUBLISH_REWARD = 10  # Points for publishing a signal
SIGNAL_ADOPT_REWARD = 1     # Points per follower who receives signal
DISCUSSION_PUBLISH_REWARD = 4  # Points for publishing a discussion
REPLY_PUBLISH_REWARD = 2       # Points for replying to a strategy/discussion

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Suhas trading profile
SUHAS_TRADING_PROFILE_ENABLED = _env_bool("SUHAS_TRADING_PROFILE_ENABLED", True)
SUHAS_ALLOW_LIVE_EXECUTION = _env_bool("SUHAS_ALLOW_LIVE_EXECUTION", False)
SUHAS_MAX_RISK_PER_TRADE_PCT = float(os.getenv("SUHAS_MAX_RISK_PER_TRADE_PCT", "1.0"))
SUHAS_MIN_REWARD_RISK_RATIO = float(os.getenv("SUHAS_MIN_REWARD_RISK_RATIO", "2.0"))
SUHAS_MAX_CHASE_PCT = float(os.getenv("SUHAS_MAX_CHASE_PCT", "1.5"))
SUHAS_MAX_PRICE_AGE_SECONDS = int(os.getenv("SUHAS_MAX_PRICE_AGE_SECONDS", "120"))
SUHAS_MIN_CONFIRMATION_SOURCES = int(os.getenv("SUHAS_MIN_CONFIRMATION_SOURCES", "2"))
