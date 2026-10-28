"""A scripted stand-in for an LLM, so agent runs can be tested without API keys."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from agents import Model, ModelResponse, Usage
from agents.items import TResponseStreamEvent
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class ScriptedModel(Model):
    """Replies with the scripted steps in order: a ToolCall, or a str as the final answer.

    Records the instructions, input and tool names of every request it receives.
    """

    steps: list[ToolCall | str]
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def get_response(self, system_instructions, input, model_settings, tools, *args, **kwargs):
        self.requests.append(
            {"instructions": system_instructions, "input": input, "tools": [t.name for t in tools]}
        )
        step = self.steps.pop(0)
        n = len(self.requests)
        if isinstance(step, ToolCall):
            item: Any = ResponseFunctionToolCall(
                id=f"fc_{n}",
                call_id=f"call_{n}",
                name=step.name,
                arguments=json.dumps(step.arguments),
                type="function_call",
                status="completed",
            )
        else:
            item = ResponseOutputMessage(
                id=f"msg_{n}",
                type="message",
                role="assistant",
                status="completed",
                content=[ResponseOutputText(type="output_text", text=step, annotations=[])],
            )
        return ModelResponse(output=[item], usage=Usage(), response_id=None)

    def stream_response(self, *args, **kwargs) -> AsyncIterator[TResponseStreamEvent]:
        raise NotImplementedError
