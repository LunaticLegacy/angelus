#!/usr/bin/env python3
"""Test DeepSeek API connection with Anthropic SDK."""

import os
import asyncio

async def test_deepseek_connection():
    """Test basic connection to DeepSeek's Anthropic-compatible API."""
    
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ DEEPSEEK_API_KEY not set!")
        return False
    
    print(f"🔑 API Key: {api_key[:8]}...")
    print(f"📡 Testing connection to DeepSeek Anthropic-compatible API...")
    print()
    
    try:
        import anthropic
        
        # Create client pointing to DeepSeek's Anthropic-compatible endpoint
        client = anthropic.Anthropic(
            api_key=api_key,
            base_url="https://api.deepseek.com/anthropic"
        )
        
        print("✅ Anthropic SDK initialized")
        print("📤 Sending test request...")
        print()
        
        # Send a simple test message
        response = client.messages.create(
            model="deepseek-chat",
            max_tokens=100,
            messages=[
                {"role": "user", "content": "Say hello!"}
            ]
        )
        
        print("✅ Response received!")
        print(f"Response: {response.content[0].text}")
        print()
        print("🎉 DeepSeek API is working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}")
        print(f"Message: {e}")
        print()
        print("💡 Troubleshooting:")
        print("   1. Check if your API key is valid and has credits")
        print("   2. Verify the API URL is correct")
        print("   3. Check if your IP is allowed")
        print("   4. Visit https://platform.deepseek.com/ for more info")
        return False

if __name__ == "__main__":
    asyncio.run(test_deepseek_connection())