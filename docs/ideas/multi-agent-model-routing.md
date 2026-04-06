# Multi-agent registry and model resolution

## Problem statement

How might we let **users define multiple agents** in a **registry**, each with its own **default LiteLLM model**, while applying a **global default from the environment** and an optional **per-invocation model override**—so a simple prompt (e.g. “say hello”) can run on **local Ollama** or **remote Groq**, as a base for **lower cost and specialized agents** later?

## Recommended direction

Use an **agent registry** as the source of truth. Each entry includes at least:

- **`id`** — required on every invocation (no backward compatibility with a single implicit agent).
- **`default_model`** — any model string **supported by LiteLLM** for this deployment.
- **Behavior** — e.g. `system_prompt` (and tools later, as needed).

**Resolution order** for the effective model (last non-empty wins):

1. **Environment** — global default (e.g. `DEFAULT_LLM_MODEL`) when the agent does not define a default.
2. **Agent definition** — `default_model` in the registry.
3. **Invocation** — optional override field (e.g. `model`) on the request body.

The handler resolves the model, builds or reuses a Strands / LiteLLM client for that id, and runs the agent.

**Misconfiguration and missing credentials:** Before calling LiteLLM, validate that **required environment variables** for the **resolved model’s provider** are set (non-empty). The project should **document** which variables are expected for which providers or model families. If validation fails, respond with **HTTP 501 Not Implemented** and a body that states the **requested model is not set up properly** and **lists the missing environment variable names**. This signals “this server cannot serve that model as configured,” not a generic client error.

**Scope note:** Abuse, quotas, auth, and spend caps are **out of scope for now**.

## Key assumptions to validate

- [ ] Provider can be inferred from the LiteLLM model id (or an explicit provider field if you add one) so env validation maps cleanly.
- [ ] A maintained **provider → required env vars** map stays aligned with project docs and LiteLLM provider requirements.
- [ ] Strands + LiteLLM behave correctly when constructing or caching clients per resolved model id.

## MVP scope

**In**

- Agent registry (static config first is fine: YAML/JSON or code).
- Required **`agent`** (registry id) on invocations; optional **`model`** override.
- Resolution order: env → agent `default_model` → invocation `model`.
- Startup or per-request validation of env vars for the resolved provider; **501** + explicit missing var names when not configured.
- Operator documentation listing required env vars per supported provider.
- Manual success test: same hello prompt with Ollama vs Groq (via agent defaults and/or body override).

**Out (for now)**

- End-user CRUD UI for agents.
- Rate limits, authentication, and billing safeguards.
- Automatic cost-based routing.
- Separate deployable per agent.

## Not doing (and why)

- **Backward compatibility** with a single unnamed agent — simplifies the API and mental model.
- **Policy / abuse prevention** — deferred; document that open override is intentional for this phase.
- **Opaque LiteLLM errors as the only signal** — replaced by explicit preflight checks and 501 with missing `ENV` names.

## Open questions

- Registry authoring: **file in repo** vs **API/DB** for the first shipped version?
- Should **sessions** pin the model for the session or allow it to change if the client sends a new override?
- Exact JSON field names (`agent`, `model`) and whether `model` is required when the agent has no `default_model` and env default is absent (error shape vs 501).
