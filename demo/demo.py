import os
import sys

# Walk up from this file until we find the package root (has __init__.py),
# then add its parent to sys.path so `from llmfetcher.xxx` works.
_pkg_root = os.path.dirname(os.path.abspath(__file__))
for _ in range(10):
    if os.path.isfile(os.path.join(_pkg_root, '__init__.py')):
        break
    _pkg_root = os.path.dirname(_pkg_root)
_parent = os.path.dirname(_pkg_root)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from llmfetcher.llm_fetcher import LLMBackendConfig, LLMFetcher
from llmfetcher.agent import Agent
from llmfetcher.tools.shell_tools import create_shell_tools

DEMO_PROMPT = f"""
Your workspace is at: `/home/luna/Documents/code/llmfetcher/workspace`. Only use shell inside it.
"""
    
def main():

    config: LLMBackendConfig = LLMBackendConfig(
        name="",
        provider="openai",
        model="deepseek-v4-flash",
        api_key="sk-cf1c28e442544eecbc9003c92cacab31",
        api_url="https://api.deepseek.com",
        timeout=120.0,
        max_retries=0
    )

    fetcher: LLMFetcher = LLMFetcher([config])
    agent: Agent = Agent(
        llm_fetcher=fetcher,
        system_prompt=DEMO_PROMPT,
        )
    agent.add_tools(create_shell_tools(sandbox_cwd="/home/luna/Documents/code/llmfetcher/workspace"))

    agent.run(
        "Now fetch the internet and find the information about LunaticLegacy.",
        verbose=True
    )

if __name__ == "__main__":
    main()