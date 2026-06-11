import json
import re
import time
from dataclasses import asdict
from typing import Optional, List, Dict, Any

from .llm_fetcher import LLMFetcher

from .llm_types import (
    AgentState, 
    AgentStateTurnEvent,
    AgentStateUpdate,
)

from .prompt import (
    AGENT_STATE_MACHINE_SYSTEM_PROMPT
)

class AgentStateMachine:
    """
    Maintain AgentState through a dedicated LLM-backed state subagent.
    Wait, I need the semantic for this.
    """

    def __init__(self, llm_handler: LLMFetcher, state: Optional[AgentState] = None) -> None:
        self.llm_handler = llm_handler
        self.state = state or AgentState()

    async def update_from_turn(
        self,
        event: AgentStateTurnEvent,
        *,
        temperature: float = 0.0,
    ) -> AgentState:
        """Ask the state subagent to update the durable AgentState.

        The serialized prompt payload strips raw tool results and only forwards
        tool names/arguments plus compressed tool-result facts.
        """
        if not self.state.task and event.user_goal.strip():
            self.state.task = event.user_goal.strip()

        update = await self._ask_state_subagent(event, temperature=temperature)
        if update is None:
            update = self._fallback_update(event)
        self.apply(update)
        return self.state

    def render(self) -> str:
        """Return the prompt-facing state text."""
        return str(self.state)

    async def _ask_state_subagent(
        self,
        event: AgentStateTurnEvent,
        *,
        temperature: float,
    ) -> Optional[AgentStateUpdate]:
        payload = {
            "current_state": asdict(self.state),
            "event": {
                "user_goal": event.user_goal,
                "turn": event.turn,
                "assistant_message": event.assistant_message,
                "tool_records": [
                    {
                        "name": record.name,
                        "arguments": record.arguments,
                    }
                    for record in event.tool_records
                ],
                "tool_result_facts": [
                    {
                        "tool_name": fact.tool_name,
                        "summary": fact.summary,
                        "facts": list(fact.facts),
                        "status": fact.status,
                        "tool_call_id": fact.tool_call_id,
                        "tags": list(fact.tags),
                    }
                    for fact in event.tool_result_facts
                ],
                "stop_requested": event.stop_requested,
            },
        }
        try:
            output = await self.llm_handler.fetch(
                msg=json.dumps(payload, ensure_ascii=False, indent=2),
                system_prompt=AGENT_STATE_MACHINE_SYSTEM_PROMPT,
                temperature=temperature,
                max_tokens=2048,
                tools=None,
            )
        except Exception:
            return None
        return self._parse_update(output.text)

    def _parse_update(self, text: str) -> Optional[AgentStateUpdate]:
        payload = self._load_json_object(text)
        if not isinstance(payload, dict):
            return None
        if isinstance(payload.get("state_update"), dict):
            payload = payload["state_update"]
        if isinstance(payload.get("state_updates"), dict):
            payload = payload["state_updates"]

        update = AgentStateUpdate(
            phase=self._string(payload.get("phase")),
            summary=self._string(payload.get("summary")),
            facts=self._string_list(payload.get("facts") or payload.get("key_facts")),
            hypotheses=self._string_list(payload.get("hypotheses")),
            artifacts=self._string_map(payload.get("artifacts")),
            credentials=self._credential_list(payload.get("credentials")),
            known_routes=self._string_map(payload.get("known_routes")),
            failed_actions=self._string_list(payload.get("failed_actions") or payload.get("failed_attempts")),
            do_not_repeat=self._string_list(payload.get("do_not_repeat")),
            next_actions=self._string_list(payload.get("next_actions")),
            transition=self._string(payload.get("transition")),
        )
        if not any(asdict(update).values()):
            return None
        return update

    def _load_json_object(self, text: str) -> Optional[object]:
        candidates = [str(text or "").strip()]
        candidates.extend(
            block.strip()
            for block in re.findall(r"```(?:json)?\s*(.*?)```", str(text or ""), flags=re.DOTALL | re.IGNORECASE)
            if block.strip()
        )
        for candidate in candidates:
            if not candidate:
                continue
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    def _fallback_update(self, event: AgentStateTurnEvent) -> AgentStateUpdate:
        failed_actions: List[str] = []
        facts: List[str] = []
        for tool_fact in event.tool_result_facts:
            if tool_fact.summary:
                facts.append(f"Tool {tool_fact.tool_name} fact: {tool_fact.summary}")
            facts.extend(
                f"Tool {tool_fact.tool_name} fact: {fact}"
                for fact in tool_fact.facts
                if fact
            )
            if tool_fact.status.lower() == "error":
                failed_actions.append(
                    f"{tool_fact.tool_name}({tool_fact.tool_call_id or ''}) -> {tool_fact.summary or 'error'}"
                )

        phase = "tool_execution" if event.tool_records else "answering"
        next_actions = [f"Review results from: {', '.join(record.name for record in event.tool_records)}"] if event.tool_records else []
        return AgentStateUpdate(
            phase=phase,
            summary=self._compact(event.assistant_message, limit=360),
            facts=facts,
            failed_actions=failed_actions,
            do_not_repeat=failed_actions,
            next_actions=next_actions,
            transition="deterministic fallback after state subagent produced no valid patch",
        )

    def apply(self, update: AgentStateUpdate) -> None:
        """Merge a state patch into the current snapshot."""
        previous_phase = self.state.phase
        if update.phase:
            self.state.phase = update.phase
        if update.summary:
            self.state.summary = update.summary

        self._extend_unique("facts", update.facts, limit=32)
        self._extend_unique("hypotheses", update.hypotheses, limit=16)
        self._extend_unique("failed_actions", update.failed_actions, limit=16)
        self._extend_unique("do_not_repeat", update.do_not_repeat, limit=16)
        self._extend_unique("next_actions", update.next_actions, limit=16)

        self.state.artifacts.update(update.artifacts)
        self.state.known_routes.update(update.known_routes)
        for credential in update.credentials:
            if credential not in self.state.credentials:
                self.state.credentials.append(credential)
        self.state.credentials = self.state.credentials[-16:]

        self.state.revision += 1
        self.state.updated_at = time.time()
        transition = update.transition or f"{previous_phase} -> {self.state.phase}"
        self.state.transitions.append({
            "revision": str(self.state.revision),
            "from": previous_phase,
            "to": self.state.phase,
            "summary": transition,
        })
        self.state.transitions = self.state.transitions[-24:]

    def _extend_unique(self, field_name: str, values: List[str], *, limit: int) -> None:
        target = getattr(self.state, field_name)
        for value in values:
            normalized = self._compact(value, limit=600)
            if normalized and normalized not in target:
                target.append(normalized)
        setattr(self.state, field_name, target[-limit:])

    def _compact(self, value: Any, *, limit: int = 240) -> str:
        normalized = " ".join(str(value or "").split())
        if len(normalized) > limit:
            return f"{normalized[:limit - 3]}..."
        return normalized

    def _string(self, value: Any) -> str:
        return self._compact(value, limit=1000)

    def _string_list(self, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        result: List[str] = []
        for item in value:
            if isinstance(item, str):
                result.append(self._compact(item, limit=600))
            elif isinstance(item, dict):
                result.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
        return [item for item in result if item]

    def _string_map(self, value: Any) -> Dict[str, str]:
        if isinstance(value, dict):
            return {
                str(key): self._compact(val, limit=1000)
                for key, val in value.items()
                if str(key).strip()
            }
        if isinstance(value, list):
            mapped: Dict[str, str] = {}
            for index, item in enumerate(value, start=1):
                if isinstance(item, dict):
                    key = str(item.get("path") or item.get("name") or item.get("id") or f"item_{index}")
                    mapped[key] = json.dumps(item, ensure_ascii=False, sort_keys=True)
            return mapped
        return {}

    def _credential_list(self, value: Any) -> List[Dict[str, str]]:
        if not isinstance(value, list):
            return []
        credentials: List[Dict[str, str]] = []
        for item in value:
            if isinstance(item, dict):
                normalized = {
                    str(key): self._compact(val, limit=1000)
                    for key, val in item.items()
                    if str(key).strip()
                }
                if normalized:
                    credentials.append(normalized)
        return credentials
