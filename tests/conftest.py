"""
Pytest configuration for llmfetcher tests.

This file ensures proper test environment setup including:
- Python path configuration
- Async test support
- Mock API keys for testing
"""

import os
import sys
from pathlib import Path

import pytest


# Ensure package parent is in Python path
project_root = Path(__file__).parent.parent
package_parent = project_root.parent
if str(package_parent) not in sys.path:
    sys.path.insert(0, str(package_parent))


@pytest.fixture(autouse=True)
def mock_api_key():
    """Provide a mock API key for tests that don't actually call APIs."""
    if not os.environ.get("DEEPSEEK_API_KEY"):
        os.environ["DEEPSEEK_API_KEY"] = "sk-test-mock-key-for-testing"
    yield
    # Cleanup if needed


@pytest.fixture
def sample_backend_config():
    """Sample LLMBackendConfig for testing."""
    from llmfetcher.llm_fetcher import LLMBackendConfig
    
    return LLMBackendConfig(
        name="test-backend",
        provider="anthropic",
        model="deepseek-chat",
        api_key=os.environ.get("DEEPSEEK_API_KEY", "sk-test-key"),
        api_url="https://api.deepseek.com/anthropic",
        timeout=30.0,
    )
