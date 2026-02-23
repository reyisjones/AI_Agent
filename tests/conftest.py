"""
pytest configuration.
"""
from __future__ import annotations

import os

import pytest

# Ensure a dummy API key is always present so settings don't fail import
os.environ.setdefault("OPENAI_API_KEY", "sk-test-00000000000000000000000000000000")


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """
    Clear the lru_cache on get_settings() between tests so env-var overrides
    in individual tests take effect.
    """
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
