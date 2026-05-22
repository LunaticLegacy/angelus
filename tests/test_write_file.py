import os
import asyncio

from llmfetcher import LLMFetcher, LLMBackendConfig, create_obscura_tools, create_shell_tools, Tool, Agent

from typing import List

def get_fetcher() -> LLMFetcher:
    """Read LLM backend config from environment."""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    
    if not api_key:
        print("=" * 60)
        print("❌ Error: DEEPSEEK_API_KEY environment variable is not set!")
        print("=" * 60)
        print("\nPlease set your DeepSeek API key:")
        print("\nOption 1: Set environment variable")
        print("  export DEEPSEEK_API_KEY='sk-your-api-key-here'")
        print("\nOption 2: Set in code (not recommended for production)")
        print("  os.environ['DEEPSEEK_API_KEY'] = 'sk-...'")
        print("\nGet your API key from: https://platform.deepseek.com/")
        print("=" * 60)
        raise RuntimeError(
            "No LLM backend configured. Please set DEEPSEEK_API_KEY environment variable."
        )
    
    print(f"🔑 Using API Key: {api_key[:8]}...")
    print(f"📡 API URL: https://api.deepseek.com/anthropic")
    print(f"🤖 Model: deepseek-chat")
    print(f"⚙️  Provider: anthropic")
    print()
    
    # ✅ 使用新的 LLMBackendConfig 方式，明确指定 provider
    backend = LLMBackendConfig(
        name="deepseek",
        provider="anthropic",  # ← DeepSeek 兼容 Anthropic 格式
        model="deepseek-chat",  # ← 改用 deepseek-chat（更稳定）
        api_key=api_key,
        api_url="https://api.deepseek.com/anthropic",
        timeout=120.0
    )
    return LLMFetcher(backends=[backend])

async def main():
    fetcher: LLMFetcher = get_fetcher()
    
    obscura_tool: List[Tool] = create_obscura_tools()
    file_io_tool: List[Tool] = create_shell_tools()
    total_tools: List[Tool] = obscura_tool + file_io_tool
    
    print(f"📦 Registered {len(total_tools)} tools:")
    for tool in total_tools:
        print(f"   - {tool.name}: {tool.description[:50]}...")
    print()
    
    agent1: Agent = Agent(
        fetcher,
        "You are a programmer. Use tools to write file to $(pwd)/workspace",
        total_tools,
        provider="anthropic"  # ← 与 backend provider 保持一致
    )

    call_msg: str = await agent1.round_call("Write a Python demo.", verbose_info=True, stream=False, max_turns=10)
    
    print("=" * 20 + " Finished demo" + "=" * 20)
    print(f"Result:\n{call_msg}")

    return

if __name__ == "__main__":
    asyncio.run(main())
