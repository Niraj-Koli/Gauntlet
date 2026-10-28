# 0001: OpenAI Agents SDK with LiteLLM, not LangGraph

**Status:** accepted

## Context

The original project used the OpenAI Agents SDK: each trader is an agent, and a researcher agent is attached to it as a tool. Each trader also had a hand-built client per provider. The rebuild had to keep the traders' behavior, add Claude and other providers as first-class models, and let each trader's model be chosen at runtime. LangGraph was the main alternative.

## Decision

Keep the OpenAI Agents SDK and route non-OpenAI models through its LiteLLM integration. Model ids are `provider/model` strings stored per trader (`llm.py` resolves them). OpenAI models use native structured output for the run summary; other providers return the same summary as JSON in text, which is validated against the same schema.

## Consequences

- **Small migration, same behavior:** the agent graph (trader, researcher as a tool, MCP servers) maps one to one onto the SDK, so the traders behave as they did, and the change was mostly deleting the per-provider clients.
- **Any LiteLLM model works:** one id format covers every provider, and cost estimates come from LiteLLM's price table.
- **No graph of states:** the SDK has no explicit state graph. Gauntlet doesn't need one, because a run is one agent loop with tools, but a future multi-step workflow with checkpoints would fit LangGraph better.
- **Two dependencies move together:** Gauntlet is tied to the SDK's and LiteLLM's release cycles, which can conflict. See [0008](0008-accepted-litellm-proxy-advisories.md).
