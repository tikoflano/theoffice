# theoffice-agents

This package hosts **Strands** agents behind **Amazon Bedrock AgentCore**: a Starlette HTTP runtime with **`POST /invocations`** and **`GET /ping`**. Resolved model ids use **`ollama/…`** with Strands’ native **`OllamaModel`** (HTTP API via **`OLLAMA_API_BASE`**). Other prefixes use Strands **`LiteLLMModel`** and any provider [supported by LiteLLM](https://docs.litellm.ai/docs/providers) when the right environment variables are set.

## Behavior

- **Agent registry** — Operators define agents in packaged [`agents.yaml`](src/theoffice_agents/agents.yaml) (or override the path with `AGENTS_REGISTRY_PATH`). Each entry has `id`, `system_prompt`, and optional **`default_model`** (logical model id, e.g. `ollama/llama3.2` or `groq/...`).
- **Invocation body** — Clients send JSON with required **`agent`** (registry id) and **`prompt`**, and optional **`model`** to override the resolved model for that call only.
- **Model resolution order** — Effective model id string is, in order: non-empty **`DEFAULT_LLM_MODEL`** env → agent’s **`default_model`** → body **`model`**. Each step overwrites the previous (so **`model` in the body wins** when set).
- **Provider preflight** — Before invoking the model client, the runtime checks a **curated** set of provider prefixes. If required API keys (or equivalent) are missing, it returns **HTTP 501** with a structured error listing **missing environment variable names** (see below).

## Prerequisites

- Python **3.12** and [uv](https://docs.astral.sh/uv/) (monorepo root; see the repository [README](../../README.md)).

From the repository root:

```bash
uv sync --python 3.12 --group dev
```

## Configuration

Copy [`.env.example`](.env.example) to `.env` in this directory or at the repository root (`load_dotenv` searches upward).

| Variable | Purpose |
|----------|---------|
| `AGENTS_REGISTRY_PATH` | Optional. Path to a YAML registry file; default is packaged `agents.yaml`. |
| `DEFAULT_LLM_MODEL` | Optional. Fallback LiteLLM model id when the agent has no `default_model` and the request omits `model` (e.g. `ollama/llama3.2`). |
| `LLM_LITELLM_CLIENT_ARGS_JSON` | Optional. JSON object merged into LiteLLM client calls. |
| `AGENT_HOST` / `AGENT_PORT` | HTTP bind (default port **8080**). |
| `LOG_LEVEL` | Logging verbosity. |

### Provider environment (curated)

These must be set (non-empty) when the **resolved** model id uses the matching prefix:

| Prefix | Example model id | Required environment variables |
|--------|------------------|--------------------------------|
| `ollama/` | `ollama/llama3.2` | **`OLLAMA_API_BASE`** (non-empty), e.g. `http://ollama:11434` in Docker Compose / Dev Containers or `http://127.0.0.1:11434` on the host. |
| `groq/` | `groq/qwen/qwen3-32b` (see [Groq models](https://console.groq.com/docs/models)) | `GROQ_API_KEY` |
| `openai/` | `openai/gpt-4o-mini` | `OPENAI_API_KEY` |
| `anthropic/` | `anthropic/claude-3-5-sonnet-20241022` | `ANTHROPIC_API_KEY` |

Other LiteLLM providers are not preflight-validated here; using them returns **422** with `reason: UNSUPPORTED_PROVIDER` until support is added in code.

## Run

From the **repository root**:

```bash
uv run --package theoffice-agents app
```

## Tests

From the repository root (after `uv sync --python 3.12 --group dev`):

```bash
uv run pytest packages/agents/tests -q
```

### Cursor: invocation smoke test

The repo defines a **Cursor agent** (instructions + script) under [`.cursor/agents/`](../../.cursor/agents/): invoke **`theoffice-agents-invocation-tester`** (see `theoffice-agents-invocation-tester.mdc`) or run:

```bash
.cursor/agents/test-invocations.sh
```

## HTTP API

### `POST /invocations`

**Request** (JSON):

| Field | Required | Description |
|--------|----------|-------------|
| `agent` | yes | Registry agent `id`. |
| `prompt` | yes | User message. |
| `model` | no | LiteLLM model id override for this request. |

**Success (200)** — JSON includes `response`, `stop_reason`, `agent`, `model` (resolved id), and `session_id` when AgentCore provides one.

**Errors** — JSON body:

```json
{
  "error": {
    "code": "VALIDATION_ERROR | MODEL_NOT_CONFIGURED | INTERNAL_ERROR",
    "message": "...",
    "details": {}
  }
}
```

- **422** — `VALIDATION_ERROR` (missing fields, unknown agent, unresolved model, unsupported provider prefix).
- **501** — `MODEL_NOT_CONFIGURED`; `details` includes `resolved_model` and `missing_environment_variables`.
- **502** — `UPSTREAM_UNAVAILABLE` when the LLM HTTP client cannot connect (e.g. Ollama not running or wrong base URL). `details.provider_error` has a short message; check server logs for the full traceback.

### `curl` examples

**Ping**

```bash
curl -s http://127.0.0.1:8080/ping | jq
```

**Invocation** (registry agent `local`, local Ollama)

```bash
curl -s -X POST http://127.0.0.1:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"agent": "local", "prompt": "Say hello in one sentence."}' | jq
```

**Invocation** with per-request model override (requires `GROQ_API_KEY` if using Groq)

```bash
curl -s -X POST http://127.0.0.1:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"agent": "local", "prompt": "Say hello.", "model": "groq/qwen/qwen3-32b"}' | jq
```

From the repository root you can poll ping with Poethepoet: `uv run poe ping` (`PING_URL` overrides the default URL).

For Ollama in Docker Compose and ports, see the main repository [README](../../README.md).
