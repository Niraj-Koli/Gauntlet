# 0008: Accepting LiteLLM's proxy-server advisories while patched versions can't be installed

**Status:** accepted, expires 2027-01-31

## Context

The security scans (pip-audit and Trivy) report advisories against litellm 1.83.0, three of them critical. The fixes are in litellm 1.83.7 through 1.95.0. But every stable litellm release from 1.84 on, up to 1.106.6, requires `openai<3`, and the OpenAI Agents SDK that Gauntlet uses (0.24) requires `openai>=3`. The only release that satisfies both is a pre-release, 1.107.0rc2.

Every advisory is in LiteLLM's **proxy server**, the AI gateway LiteLLM can run as a service:
- `/prompts/test` (template injection);
- `/guardrails/test_custom_code`;
- the `/mcp-rest` test endpoints;
- `/user/update`;
- proxy API key checks (SQL injection);
- Host-header authentication;
- the proxy's MCP endpoint;
- `/sso/debug/callback` (reflected XSS);
- `/utils/transform_request` (local file read).

Gauntlet imports litellm only as a client library, through the Agents SDK's `LitellmModel` and `litellm.cost_per_token`. It never imports `litellm.proxy` or starts the proxy, so none of those endpoints exist in it.

## Decision

Stay on litellm 1.83.0. Record each advisory as an exception with its reason, in `.trivyignore.yaml` and in the pip-audit step of `security.yml`, and give them all an expiry date.

The alternatives were a pre-release in production, or downgrading the Agents SDK and openai, which would undo [0001](0001-agents-sdk-and-litellm.md)'s upgrade. Both carry more risk than code that never runs.

## Consequences

- **The scans still guard everything else:** any new advisory, in litellm or anywhere else, fails CI.
- **The exceptions expire:** on 2027-01-31 Trivy stops ignoring them, and this decision has to be made again.
- **The fix is waiting on litellm:** once a stable litellm supports openai 3, Dependabot proposes it. Upgrade, then delete the exceptions.
- **If the proxy is ever used, this stops holding:** if Gauntlet starts using LiteLLM's proxy, upgrade first.
