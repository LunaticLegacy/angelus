#!/usr/bin/env python3
"""Debug: Check what messages are being sent to DeepSeek."""

import os
import asyncio
from llmfetcher import LLMFetcher, LLMBackendConfig

async def debug_messages():
    """Debug message format being sent to API."""
    
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ DEEPSEEK_API_KEY not set!")
        return
    
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
    
    # Build messages like Agent does
    messages = fetcher._build_messages(
        msg="Say hello!",
        prev_messages=[],
        system_prompt=None
    )
    
    print("📝 Messages being sent:")
    for i, msg in enumerate(messages):
        print(f"  [{i}] role={msg['role']}, content='{msg['content']}'")
    print()
    
    # Now try with Anthropic conversion
    print("🔄 Converting to Anthropic format...")
    anthropic_messages, system_prompt = fetcher._convert_to_anthropic_messages(messages)
    
    print(f"System prompt: {system_prompt}")
    print("Anthropic messages:")
    for i, msg in enumerate(anthropic_messages):
        print(f"  [{i}] role={msg['role']}, content type={type(msg['content'])}")
        if isinstance(msg['content'], list):
            for j, item in enumerate(msg['content']):
                print(f"      [{j}] {item}")
        else:
            print(f"      '{msg['content']}'")

if __name__ == "__main__":
    asyncio.run(debug_messages())
