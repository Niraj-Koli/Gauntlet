# Architecture decision records

Each record covers a decision that shaped Gauntlet: the context, what was chosen, and the consequences, including the costs.

| | Decision |
|---|---|
| [0001](0001-agents-sdk-and-litellm.md) | OpenAI Agents SDK with LiteLLM, not LangGraph |
| [0002](0002-mcp-servers-hosted-by-the-api.md) | The account and market MCP servers live in the API, bound to a trader by a signed per-run token |
| [0003](0003-supabase-with-the-api-as-the-only-writer.md) | Supabase for Postgres, Realtime and Auth, with the API as the only writer |
| [0004](0004-asyncio-scheduler-with-a-database-lease.md) | A plain asyncio scheduler with a leader lease and command queue in the database |
| [0005](0005-demo-mode.md) | A scripted demo model, so the whole app runs without API keys |
| [0006](0006-build-once-runtime-config.md) | Images built once and configured at runtime |
| [0007](0007-gitops-with-argo-cd.md) | GitOps with Argo CD, an image-tag commit per release, and Sealed Secrets |
| [0008](0008-accepted-litellm-proxy-advisories.md) | Accepting LiteLLM's proxy-server advisories while patched versions can't be installed |
