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
