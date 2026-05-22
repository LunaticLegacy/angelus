#!/usr/bin/env python3
"""Test DeepSeek API with tools using llmfetcher."""

import os
import asyncio
from llmfetcher import LLMFetcher, LLMBackendConfig, Agent

async def test_with_tools():
    """Test DeepSeek API with tool calling."""
    
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ DEEPSEEK_API_KEY not set!")
        return
    
    print(f"🔑 API Key: {api_key[:8]}...")
    print()
    
    # Setup backend
    backend = LLMBackendConfig(
        name="deepseek",
        provider="anthropic",
        model="deepseek-chat",
        api_key=api_key,
        api_url="https://api.deepseek.com/anthropic",
        timeout=120.0
    )
    
    fetcher = LLMFetcher(backends=[backend])
    
    # Create agent WITHOUT tools first
    agent = Agent(
        llm_handler=fetcher,
        system_prompt="You are a helpful assistant.",
        provider="anthropic"
    )
    
    print("✅ Backend configured")
    print("✅ Agent created (no tools)")
    print()
    print("📤 Testing basic query...")
    
    try:
        result = await agent.round_call(
            msg="Say hello and tell me what you can do.",
            verbose_info=True,
            max_turns=3
        )
        
        print()
        print("=" * 60)
        print("✅ SUCCESS! Response:")
        print("=" * 60)
        print(result)
        print("=" * 60)
        
    except Exception as e:
        print()
        print(f"❌ Error: {type(e).__name__}")
        print(f"Message: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_with_tools())
