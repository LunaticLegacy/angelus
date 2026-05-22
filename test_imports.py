#!/usr/bin/env python3
"""Quick test to verify llmfetcher module imports work correctly."""

import sys
from pathlib import Path

# Add parent directory to path so the llmfetcher package can be imported.
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root.parent))

print("🧪 Testing llmfetcher module imports...")
print(f"Python path: {sys.path[0]}")
print()

try:
    from llmfetcher import LLMFetcher, Agent, Tool
    print("✅ Core imports successful")
except ImportError as e:
    print(f"❌ Core import failed: {e}")
    sys.exit(1)

try:
    from llmfetcher.llm_fetcher import LLMBackendConfig
    print("✅ LLMBackendConfig import successful")
except ImportError as e:
    print(f"❌ LLMBackendConfig import failed: {e}")
    sys.exit(1)

try:
    from llmfetcher.swarm.swarm import AgentSwarm
    print("✅ AgentSwarm import successful")
except ImportError as e:
    print(f"❌ AgentSwarm import failed: {e}")
    sys.exit(1)

try:
    from llmfetcher.agent_io import AgentFileIOManager
    print("✅ AgentFileIOManager import successful")
except ImportError as e:
    print(f"❌ AgentFileIOManager import failed: {e}")
    sys.exit(1)

print()
print("=" * 60)
print("✅ All imports successful!")
print("=" * 60)
