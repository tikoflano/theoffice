# Spec: Multi-agent AgentCore runtime

## Traceability

- Idea one-pager: [`docs/ideas/multi-agent-model-routing.md`](../ideas/multi-agent-model-routing.md)
- Host framework: `bedrock_agentcore.BedrockAgentCoreApp` — fixed routes `POST /invocations`, `GET /ping`, `WebSocket /ws`; **flexibility is the JSON body** only.

## Assumptions (correct if wrong)

1. **Registry v1 is static** — a file shipped with `theoffice-agents` (YAML), not a database or CRUD API in this phase.
2. **Models go through LiteLLM** — Strands uses a LiteLLM-backed model type so any [LiteLLM-supported](https://docs.litellm.ai/docs/providers) id (e.g. `ollama/llama3.2`, `groq/qwen/qwen3-32b`) can be configured; today’s `OllamaModel`-only construction is replaced or wrapped as part of implementation.
3. **Session behavior** — `session_id` from AgentCore (if present) does **not** pin the model: **model is resolved on every invocation** from env + agent + body. (Changing this later would be an explicit new spec.)
4. **No backward compatibility** — callers must send a registered `agent` id and a **top-level** `prompt` string; old “implicit single agent” payloads are not supported.
5. **Auth / abuse** — out of scope; no rate limits in this spec.

---

## Objective

Deliver an AgentCore-compatible HTTP runtime where:

- Operators define **multiple agents** in a **registry** (id, optional `default_model`, `system_prompt`, room for tools later).
- Each invocation **must** name an agent; the effective LiteLLM model is resolved in order: **`DEFAULT_LLM_MODEL` (env) → agent.default_model → body.model** (each step overrides the previous when non-empty).
- If the resolved model’s **provider prerequisites** (required env vars) are missing, the server returns **HTTP 501** with a **structured error** listing **missing variable names** — not a generic 500 from LiteLLM.
- Success can be demonstrated with a trivial `prompt` (e.g. “say hello”) using **Ollama** vs **Groq** via different agents and/or `model` override.

---

## Tech stack

| Layer | Choice |
|--------|--------|
| Runtime | Python 3.12, `bedrock-agentcore`, Starlette |
| Agent framework | Strands |
| LLM routing | LiteLLM (via Strands integration used in this package) |
| Config | YAML registry + `python-dotenv` for env |
| Monorepo tool | uv |

---

## HTTP API contract

### `POST /invocations`

**Request** — `Content-Type: application/json`

| Field | Type | Required | Description |
|--------|------|----------|-------------|
| `agent` | string | yes | Registry entry `id`. |
| `prompt` | string | yes | Non-empty user message. |
| `model` | string | no | LiteLLM model id; overrides agent `default_model` and `DEFAULT_LLM_MODEL` when set (non-empty after trim). |

**Success — HTTP 200** — `Content-Type: application/json`

| Field | Type | Description |
|--------|------|-------------|
| `response` | string | Assistant text (trimmed). |
| `stop_reason` | string | From Strands result. |
| `session_id` | string | Present when AgentCore provides a session id. |
| `agent` | string | Echo resolved agent id (aids debugging and logs). |
| `model` | string | **Resolved** effective LiteLLM model id (aids debugging; do not treat as secret). |

**Errors** — single envelope everywhere the handler controls the response:

```json
{
  "error": {
    "code": "SNAKE_UPPER_STRING",
    "message": "Human-readable summary.",
    "details": {}
  }
}
```

| HTTP | `code` | When |
|------|--------|------|
| 422 | `VALIDATION_ERROR` | Missing/empty `agent` or `prompt`, unknown `agent` id, or **no model after resolution** (nothing in env default, agent, or body). |
| 501 | `MODEL_NOT_CONFIGURED` | Model resolved, but one or more **required env vars** for its provider are unset or empty. `details` **must** include `resolved_model` (string) and `missing_environment_variables` (string array). |
| 500 | `INTERNAL_ERROR` | Unexpected failure after validation (message sanitized; no stack traces in body). |

**Notes**

- Invalid JSON: AgentCore returns **400** with its own shape; no requirement to normalize that in v1.
- Prefer raising `starlette.exceptions.HTTPException` or returning `JSONResponse` from the entrypoint where the library supports pass-through status codes (see `bedrock_agentcore` invocation handler).

---

## Registry format

**Path (proposed):** `packages/agents/src/theoffice_agents/agents.yaml` (or `config/agents.yaml` colocated with the package — pick one at implementation; document in README).

**Schema (YAML):**

```yaml
# Optional: global default when an agent omits default_model (still overridable by body.model)
# Process env DEFAULT_LLM_MODEL is the fallback when agent default_model is omitted; body.model overrides last.
agents:
  - id: local
    default_model: ollama/llama3.2
    system_prompt: You are a concise, helpful assistant.
  - id: cloud
    default_model: groq/qwen/qwen3-32b
    system_prompt: You are a concise, helpful assistant.
```

Rules:

- `id` — non-empty string, unique.
- `default_model` — optional; may be omitted if process env always supplies `DEFAULT_LLM_MODEL` **and** you accept that all such agents share that default until body overrides.
- `system_prompt` — required for v1 (empty string allowed only if we explicitly allow no system prompt — **default: required non-empty**).

**Loading:** Parse at startup; fail fast on duplicate ids or invalid YAML (process exit with clear stderr, non-zero exit).

---

## Model resolution algorithm

1. Let `m` be **unset**.
2. If `DEFAULT_LLM_MODEL` is set and non-empty after trim, `m = DEFAULT_LLM_MODEL`.
3. If registry agent has `default_model` set and non-empty, `m = agent.default_model`.
4. If body `model` is set and non-empty after trim, `m = body.model`.
5. If `m` is still unset → **422** `VALIDATION_ERROR` (e.g. message: cannot resolve model).
6. Infer **provider** from `m` using a **prefix map** (e.g. `ollama/…`, `groq/…`, `openai/…`). If unknown prefix → **422** or **501** with code `UNSUPPORTED_PROVIDER` (choose one; **recommend 422** with “unsupported provider for this deployment”).
7. Look up **required env var names** for that provider. If any required value is missing/empty → **501** `MODEL_NOT_CONFIGURED` with `missing_environment_variables`.
8. Obtain or construct a Strands/LiteLLM model client for `m` (implementation may **cache by `m`** on `app.state`).
9. Run Strands `Agent` with resolved `system_prompt` and model.

---

## Provider ↔ environment documentation

**Location:** `packages/agents/README.md` (or `docs/agents/configuration.md` — one place only).

Maintain a table aligned with code’s `provider → required_env_vars` map, for example:

| Provider prefix | Example model id | Required env (minimum) |
|-----------------|------------------|-------------------------|
| `ollama/` | `ollama/llama3.2` | `OLLAMA_API_BASE` (required for this runtime; LiteLLM default localhost is not assumed) |
| `groq/` | `groq/qwen/qwen3-32b` | `GROQ_API_KEY` |
| `openai/` | `openai/gpt-4o-mini` | `OPENAI_API_KEY` |

Implementation must not hardcode every LiteLLM provider on day one: **support a curated set** used in dev/prod; unknown prefix → explicit error as in resolution step 6.

---

## Design principles (OOP)

- Prefer **composable classes** with clear responsibilities over loose module-level functions. Functions are fine **inside** classes (private helpers) or as **thin factories** (`create_app`) that wire objects together.
- Favor **dependency injection** of registries, env readers, and model factories so tests can substitute fakes without patching globals.
- Keep **HTTP handlers thin**: parse → delegate to a small **application/service object** → map domain errors to the standard JSON envelope.

Illustrative types (names may vary at implementation):

| Responsibility | Class (conceptual) |
|----------------|--------------------|
| Load and query registry | `AgentRegistry` |
| Parse/validate JSON body | `InvocationRequest` (dataclass or Pydantic model) + `InvocationParser` |
| Resolve model id + provider env checks | `ModelResolution` result + `ModelResolver` |
| Build/cache Strands models | `LiteLLMModelFactory` (or `StrandsModelFactory`) |

---

## Project structure (delta)

```
packages/agents/src/theoffice_agents/
  agent_runtime.py      # AgentCore app factory; wires classes; entrypoint
  agents.yaml           # Registry (v1)
  registry.py           # AgentRegistry: load YAML, lookup by id, validate
  invocation.py         # InvocationRequest, InvocationParser (boundary validation)
  model_resolution.py   # ModelResolver, ModelResolution; provider env checks
  model_factory.py      # LiteLLMModelFactory: build/cache Strands models
  strands_setup.py      # Legacy or thin wrappers — evolve per LiteLLM adoption
```

Tests:

```
packages/agents/tests/
  test_registry.py
  test_model_resolution.py
  test_invocation_contract.py   # optional: ASGI client against app
```

---

## Code style

- Match existing package: type hints, `from __future__ import annotations`, thin HTTP handlers.
- **OOP over scattered functions:** encapsulate behavior in classes; compose them in `create_app` (or a dedicated `AgentRuntime` / `InvocationService` if the app factory grows).
- Public API is HTTP JSON — validate at the boundary via a **parser object** (or Pydantic model); inner layers receive **typed values** or small dataclasses, not raw `dict[str, Any]`.
- Log **resolved model** and **agent id** at info; never log secrets.

Example boundary validation (illustrative — prefer a class or Pydantic, not a lone function):

```python
@dataclass(frozen=True)
class InvocationRequest:
    agent_id: str
    prompt: str
    model_override: str | None


class InvocationParser:
    def parse(self, payload: dict[str, Any]) -> InvocationRequest:
        agent = payload.get("agent")
        prompt = payload.get("prompt")
        model_override = payload.get("model")
        if not isinstance(agent, str) or not agent.strip():
            raise ValidationError("agent is required")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValidationError("prompt is required")
        mo = model_override.strip() if isinstance(model_override, str) else None
        return InvocationRequest(agent.strip(), prompt.strip(), mo or None)
```

Map `ValidationError` (and resolver errors) to the standard `error` envelope in a single **error mapper** or small method on the service class.

---

## Commands

```bash
# Sync deps (repo root)
uv sync --python 3.12 --group dev

# Run AgentCore app
uv run --package theoffice-agents app

# Tests (add pytest to agents package when implemented)
uv run pytest packages/agents/tests -q
```

---

## Testing strategy

| Level | Scope |
|-------|--------|
| Unit | Registry load (duplicates, missing file), resolution order, provider env checks (mock `os.environ`). |
| Unit | Error codes: unknown agent → 422; missing `GROQ_API_KEY` when resolved model is `groq/…` → 501 with listed vars. |
| Integration | Optional: httpx ASGI against `create_app()` with env + registry fixture (may require network skip for real LLM; use mocked model factory if needed). |

Coverage: new modules should have tests for all branches in resolution and error mapping.

---

## Boundaries

- **Always:** Validate `agent` + `prompt` + resolved model env at the invocation boundary; return the agreed JSON error shape for 422/501.
- **Ask first:** Adding new first-class HTTP routes outside AgentCore’s fixed paths; changing `DEFAULT_LLM_MODEL` env name; expanding LiteLLM provider map beyond the curated table.
- **Never:** Log API keys or full third-party error bodies to clients; commit real secrets.

---

## Success criteria

1. `POST /invocations` with `{ "agent": "<id>", "prompt": "Say hello in one sentence." }` returns **200** and a non-empty `response` when that agent’s model is configured.
2. Two agents (or same agent with `model` override) can demonstrate **Ollama** vs **Groq** when env vars for both are set.
3. With `GROQ_API_KEY` unset and resolved model `groq/…`, response is **501** with `error.code === "MODEL_NOT_CONFIGURED"` and `missing_environment_variables` including `GROQ_API_KEY`.
4. Unknown `agent` → **422** with consistent `error` envelope.
5. README documents required env vars for each **supported** provider prefix.

---

## Open questions (remaining)

1. **Exact env name for process-wide default** — **`DEFAULT_LLM_MODEL`** (process fallback when agent omits `default_model` and body omits `model`).
2. **Ollama via LiteLLM** — confirm Strands + LiteLLM path for `ollama/...` matches local dev (`OLLAMA_API_BASE`); align `agents.yaml` examples with working vars.
3. **Streaming** — out of scope for this spec; if AgentCore entrypoint returns streaming later, resolution rules stay the same.

---

## Next steps (gated workflow)

1. Human review of this spec (Phase 1).
2. **Planning:** `planning-and-task-breakdown` skill → task list.
3. **Implement:** `incremental-implementation` + `test-driven-development` skills (see `.cursor/skills/`).
