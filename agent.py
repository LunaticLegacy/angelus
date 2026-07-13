from .llm_fetcher import LLMBackendConfig, LLMFetcher, LLMBackendHandler
from .llm_types import Tool, LLMOutput
from .tool_handler import ToolHandler
from .context_handlers import ContextHandlerLinear, ContextHandler


class Agent:
    def __init__(
        self,
        llm_fetcher: LLMFetcher,
        *,
        system_prompt: str,
    ):
        self.llm_fetcher = llm_fetcher
        self.system_prompt = system_prompt
        self.tool_handler: ToolHandler = ToolHandler()
        self.context_handler: ContextHandler = ContextHandlerLinear()

    def add_tool(
        self,
        tool: Tool,
    ) -> bool:
        return self.tool_handler.add_tool(tool=tool)

    def _build_prompt(self) -> str:
        return self.system_prompt + "\n" \
            + self.tool_handler.get_all_tool_description()

    def run(
        self,
        message: str,
        max_rounds: int = 30,
        temperature: float = 0.4,
        max_tokens: int = 32768,
    ):

        prompt: str = self._build_prompt()

        for round in range(1, 1 + max_rounds):
            result: LLMOutput = self.llm_fetcher.fetch(
                msg=message,
                system_prompt=prompt,
                temperature=temperature,
                context=self.context_handler,
                max_tokens=max_tokens,
                tools=self.tool_handler.get_all_tools(),
            )

