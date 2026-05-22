#!/usr/bin/env python3
"""Test DeepSeek API with llmfetcher - no tools."""

import os
import asyncio
from llmfetcher import LLMFetcher, LLMBackendConfig

async def test_no_tools():
    """Test DeepSeek API without any tools."""
    
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
    
    print("✅ Backend configured")
    print("📤 Testing direct API call (no tools)...")
    print()
    
    try:
        # Direct API call without tools
        response = await fetcher.fetch(
            msg="Say hello!",
            system_prompt=None,
            prev_messages=[],
            tools=None  # ← No tools
        )
        
        print("✅ Response received!")
        print(f"Content: {response.content}")
        print()
        print("🎉 Basic API call works!")
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}")
        print(f"Message: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_no_tools())
