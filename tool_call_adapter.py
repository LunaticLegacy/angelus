"""Tool call normalization and adaptation utilities.

This module provides adapters to parse tool calls from different LLM providers
and convert them to a unified internal format.

Supported providers:
- OpenAI (native tool_calls)
- Anthropic (ToolUseBlock)
- Custom JSON (legacy format parsed from content)
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum


class ToolCallSource(str, Enum):
    """Source provider of the tool call."""
    OPENAI_NATIVE = "openai_native"
    ANTHROPIC = "anthropic"
    CUSTOM_JSON = "custom_json"


@dataclass
class NormalizedToolCall:
    """Unified representation of a tool call across all providers."""
    
    # Core information
    tool_name: str
    arguments: Dict[str, Any]
    
    # Tracking
    call_id: Optional[str] = None
    source: ToolCallSource = ToolCallSource.CUSTOM_JSON
    
    def to_execution_format(self) -> Dict[str, Any]:
        """Convert to format expected by ToolRegistry.execute()."""
        return {
            "tool": self.tool_name,
            "arguments": self.arguments,
        }


_XML_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL,
)


def _parse_tool_call_payload(payload: str) -> Optional[NormalizedToolCall]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    name = parsed.get("name")
    if not name:
        return None

    arguments = parsed.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}

    return NormalizedToolCall(
        tool_name=str(name),
        arguments=arguments if isinstance(arguments, dict) else {},
        source=ToolCallSource.CUSTOM_JSON,
    )


def _iter_json_object_spans(text: str):
    start: Optional[int] = None
    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(text):
        if start is None:
            if char == "{":
                start = index
                depth = 1
                in_string = False
                escape = False
            continue

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                yield start, index + 1
                start = None


def parse_xml_tool_calls(text: str) -> List[NormalizedToolCall]:
    """Extract Qwen-style tool calls from raw text.

    Supports both the documented ``<tool_call>...</tool_call>`` wrapper and
    bare JSON objects emitted by some ONNX Runtime / Qwen generations.
    """
    calls: List[NormalizedToolCall] = []
    for match in _XML_TOOL_CALL_RE.finditer(text):
        call = _parse_tool_call_payload(match.group(1))
        if call is not None:
            calls.append(call)

    # Some backends emit bare JSON tool calls without the XML wrapper, often
    # embedded inside explanatory text or code fences.
    seen_payloads: set[str] = set()
    for start, end in _iter_json_object_spans(text):
        candidate = text[start:end].strip()
        if candidate in seen_payloads:
            continue
        seen_payloads.add(candidate)
        call = _parse_tool_call_payload(candidate)
        if call is not None:
            calls.append(call)

    return calls


def strip_xml_tool_calls(text: str) -> str:
    """Remove Qwen-style tool-call payloads from raw text."""
    without_xml = _XML_TOOL_CALL_RE.sub("", text)
    spans: list[tuple[int, int]] = []
    for start, end in _iter_json_object_spans(without_xml):
        candidate = without_xml[start:end].strip()
        if _parse_tool_call_payload(candidate) is not None:
            spans.append((start, end))

    if not spans:
        return without_xml.strip()

    chars = list(without_xml)
    for start, end in reversed(spans):
        for index in range(start, end):
            chars[index] = ""
    return "".join(chars).strip()


def normalize_tool_calls(
    response: Any,
    source: ToolCallSource = ToolCallSource.CUSTOM_JSON,
    fallback_parser=None,
) -> List[NormalizedToolCall]:
    """
    Normalize tool calls from various LLM providers.
    
    Args:
        response: Raw LLM response object
        source: Which provider format to expect
        fallback_parser: Optional fallback parser function for custom JSON
        
    Returns:
        List of normalized tool calls
    """
    unified_calls = getattr(response, "tool_calls", None)
    if unified_calls:
        calls: List[NormalizedToolCall] = []
        for tool_call in unified_calls:
            name = getattr(tool_call, "name", "")
            if not name:
                continue
            arguments = getattr(tool_call, "arguments", {}) or {}
            calls.append(
                NormalizedToolCall(
                    tool_name=str(name),
                    arguments=arguments if isinstance(arguments, dict) else {},
                    call_id=getattr(tool_call, "call_id", None),
                    source=source,
                )
            )
        return calls

    if source == ToolCallSource.OPENAI_NATIVE:
        return _from_openai(response)
    elif source == ToolCallSource.ANTHROPIC:
        return _from_anthropic(response)
    elif source == ToolCallSource.CUSTOM_JSON:
        return _from_custom_json(response, fallback_parser)
    else:
        raise ValueError(f"Unsupported source: {source}")


def _from_openai(response: Any) -> List[NormalizedToolCall]:
    """Parse OpenAI native tool_calls format.
    
    Expected structure:
    {
        "choices": [{
            "message": {
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "type": "function",
                        "function": {
                            "name": "search",
                            "arguments": '{"query": "AI"}'
                        }
                    }
                ]
            }
        }]
    }
    """
    try:
        message = response.choices[0].message
        if not hasattr(message, 'tool_calls') or not message.tool_calls:
            return []
        
        calls = []
        for tc in message.tool_calls:
            try:
                # OpenAI returns arguments as JSON string
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, AttributeError):
                args = {}
            
            calls.append(NormalizedToolCall(
                tool_name=tc.function.name,
                arguments=args if isinstance(args, dict) else {},
                call_id=tc.id,
                source=ToolCallSource.OPENAI_NATIVE
            ))
        return calls
    except Exception as e:
        print(f"Warning: Failed to parse OpenAI tool calls: {e}")
        return []


def _from_anthropic(response: Any) -> List[NormalizedToolCall]:
    """Parse Anthropic Claude ToolUseBlock format.
    
    Expected structure:
    {
        "content": [
            TextBlock(type='text', text='...'),
            ToolUseBlock(
                id='toolu_abc',
                name='search',
                input={'query': 'AI'}  # Already a dict!
            )
        ]
    }
    """
    try:
        if not hasattr(response, 'content'):
            return []
        
        calls = []
        for block in response.content:
            if hasattr(block, 'type') and block.type == "tool_use":
                # Anthropic returns input as direct dict (no JSON parsing needed)
                calls.append(NormalizedToolCall(
                    tool_name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                    call_id=block.id,
                    source=ToolCallSource.ANTHROPIC
                ))
        return calls
    except Exception as e:
        print(f"Warning: Failed to parse Anthropic tool calls: {e}")
        return []


def _from_custom_json(
    response: Any,
    fallback_parser=None
) -> List[NormalizedToolCall]:
    """Parse custom JSON format from content string.
    
    This is the legacy format where tool calls are embedded in the message content.
    
    Args:
        response: LLM response object
        fallback_parser: Optional custom parser function. If None, returns empty list.
    """
    try:
        # Extract content from response
        if hasattr(response, 'choices'):
            content = response.choices[0].message.content or ""
        else:
            content = str(response)
        
        if not content:
            return []
        
        # Use fallback parser if provided
        if fallback_parser:
            parsed = fallback_parser(content)
        else:
            # Import here to avoid circular dependency
            # This should be Agent._parse_json_tool_calls
            return []
        
        calls = []
        for item in parsed:
            calls.append(NormalizedToolCall(
                tool_name=item["tool"],
                arguments=item.get("arguments", {}),
                source=ToolCallSource.CUSTOM_JSON
            ))
        return calls
    except Exception as e:
        print(f"Warning: Failed to parse custom JSON tool calls: {e}")
        return []
