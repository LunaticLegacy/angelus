#!/usr/bin/env python3
"""Test DeepSeek API with simple tool."""

import os
import asyncio
from llmfetcher import LLMFetcher, LLMBackendConfig, Agent, Tool

async def test_simple_tool():
    """Test with a simple tool."""
    
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ DEEPSEEK_API_KEY not set!")
        return
    
    # Define a simple tool
    async def get_time(**kwargs) -> str:
        """Get current time."""
        import datetime
        return f"Current time: {datetime.datetime.now()}"
    
    time_tool = Tool(
        name="get_time",
        description="Get the current date and time",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        handler=get_time
    )
    
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
    
    # Create agent with tool
    agent = Agent(
        llm_handler=fetcher,
        system_prompt="You have access to tools. Use them when needed.",
        provider="anthropic"
    )
    
    agent.add_tool(time_tool)
    
    print("✅ Backend configured")
    print("✅ Tool registered")
    print()
    print("📤 Testing tool call...")
    
    try:
        result = await agent.round_call(
            msg="What time is it?",
            verbose_info=True,
            max_turns=3
        )
        
        print()
        print("=" * 60)
        print("✅ SUCCESS!")
        print("=" * 60)
        print(result)
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}")
        print(f"Message: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_simple_tool())
