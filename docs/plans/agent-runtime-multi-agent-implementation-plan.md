# Implementation Plan: Multi-agent AgentCore runtime

## Overview

Implement the multi-agent registry, LiteLLM-backed model resolution (env → agent → invocation body), structured **422** / **501** / **500** JSON errors, and a thin AgentCore entrypoint that delegates to a composable **invocation service**, as specified in [`docs/specs/agent-runtime-multi-agent.md`](../specs/agent-runtime-multi-agent.md). Replace the current single-agent, Ollama-only path in `agent_runtime.py` with the new contract (**required** `agent` + `prompt`; no legacy prompt shapes).

## Architecture decisions

- **OOP composition:** `AgentRegistry`, `InvocationParser`, `ModelResolver`, `LiteLLMModelFactory` (or equivalent names), and `InvocationService` (name TBD) wired in `create_app` / lifespan with injectable dependencies for tests.
- **YAML registry** shipped under `packages/agents/src/theoffice_agents/agents.yaml`; process **exits non-zero** on duplicate ids or invalid YAML at startup.
- **Curated provider map** in code (prefix → required env var names); unknown prefix → **422** `VALIDATION_ERROR` with code detail `UNSUPPORTED_PROVIDER` or nested in `details` per final envelope choice (stay consistent with spec).
- **501** only for **MODEL_NOT_CONFIGURED** (resolved model known, env incomplete); **422** for unknown agent, bad body, unresolved model chain, unsupported provider.
- **LiteLLM via Strands:** confirm the exact Strands model class and extras (`strands-agents[...]`, `litellm`) in Task 5 before locking factory code; align with existing `bedrock-agentcore[strands-agents]`.

## Dependency graph

```
pytest + PyYAML (+ optional dev extras)
        │
        ▼
AgentRegistry (YAML → typed definitions)
        │
        ├──► ModelResolver (resolution order + provider env check)
        │         │
        │         ▼
        │    LiteLLMModelFactory (build/cache; depends on resolved id)
        │
InvocationParser (JSON → InvocationRequest)
        │
        ▼
InvocationService (orchestration + error envelope mapping)
        │
        ▼
agent_runtime.py (BedrockAgentCoreApp, lifespan, entrypoint)
        │
        ▼
README + .env.example (operator table)
        │
        ▼
Optional: ASGI integration tests (httpx + mocks)
```

**Vertical slice:** After **InvocationService** + **agent_runtime** are wired, the product is runnable end-to-end; earlier tasks stay testable in isolation.

---

## Task list

### Phase 1: Foundation

#### Task 1: Test and config dependencies for `theoffice-agents`

**Description:** Add `pytest` (and any shared dev deps policy the monorepo uses) so `packages/agents/tests/` can run. Add **PyYAML** as a **runtime** dependency for registry loading. Optionally add `pytest-cov` only if the repo standardizes on it elsewhere.

**Acceptance criteria:**

- [ ] `uv run pytest packages/agents/tests -q` runs (zero tests is OK for this task).
- [ ] `import yaml` works in package code after `uv sync`.

**Verification:**

- [ ] `uv sync --python 3.12 --group dev` from repo root succeeds.
- [ ] `uv run pytest packages/agents/tests -q` exits 0.

**Dependencies:** None

**Files likely touched:**

- `packages/agents/pyproject.toml`
- Possibly root `pyproject.toml` / workspace dev group if you centralize pytest there

**Estimated scope:** Small (1 file)

---

#### Task 2: `AgentRegistry` and `agents.yaml`

**Description:** Implement `AgentRegistry` to load the YAML schema from the spec (list of agents with `id`, optional `default_model`, required `system_prompt`). Validate uniqueness of `id` and fail fast with a clear exception message suitable for startup logging / stderr. Expose `get(agent_id) -> AgentDefinition | None` or raise a domain error.

**Acceptance criteria:**

- [ ] Valid `agents.yaml` loads; duplicate `id` causes load failure.
- [ ] Malformed YAML or missing required fields causes load failure with actionable messages.
- [ ] Unit tests cover happy path, duplicate id, and missing file path behavior (if configurable).

**Verification:**

- [ ] `uv run pytest packages/agents/tests/test_registry.py -q` passes.

**Dependencies:** Task 1

**Files likely touched:**

- `packages/agents/src/theoffice_agents/registry.py`
- `packages/agents/src/theoffice_agents/agents.yaml`
- `packages/agents/tests/test_registry.py`

**Estimated scope:** Medium (3 files)

---

#### Task 3: `InvocationParser` and `InvocationRequest`

**Description:** Implement frozen dataclass `InvocationRequest` and class `InvocationParser.parse(payload: dict) -> InvocationRequest` per spec. Raise small domain exceptions (e.g. `InvocationValidationError`) for missing/empty `agent` or `prompt`, or wrong types—**do not** return HTTP responses here.

**Acceptance criteria:**

- [ ] Valid body parses; optional `model` trimmed; empty string treated as absent.
- [ ] Invalid bodies raise domain exceptions with stable `code` or message attributes for the mapper layer.

**Verification:**

- [ ] `uv run pytest packages/agents/tests/test_invocation.py -q` passes.

**Dependencies:** Task 1

**Files likely touched:**

- `packages/agents/src/theoffice_agents/invocation.py`
- `packages/agents/tests/test_invocation.py`

**Estimated scope:** Small (2 files)

---

### Checkpoint: Foundation (after Tasks 1–3)

- [ ] All new tests pass.
- [ ] No change yet to live `/invocations` behavior (acceptable if Tasks 2–3 are pure new modules).

---

### Phase 2: Resolution and model factory

#### Task 4: `ModelResolver` (resolution order + provider env)

**Description:** Implement `ModelResolver` (or equivalent) that takes process default from configurable env snapshot (constructor injection), `AgentDefinition`, and `InvocationRequest.model_override`, and produces a `ModelResolution` result with final LiteLLM model id string. Implement curated **prefix → required env var names**; implement missing-env detection returning structured data for **501** (not HTTP). Unknown prefix → domain error for **422**. Unset model after full chain → domain error for **422**.

**Acceptance criteria:**

- [ ] Order matches spec: `DEFAULT_LLM_MODEL` → agent `default_model` → body `model` (each non-empty step updates `m`).
- [ ] `groq/...` with missing `GROQ_API_KEY` yields “not configured” outcome with list `["GROQ_API_KEY"]`.
- [ ] Unknown prefix yields unsupported-provider outcome.

**Verification:**

- [ ] `uv run pytest packages/agents/tests/test_model_resolution.py -q` passes with patched/mocked `os.environ` or injected env dict.

**Dependencies:** Task 2 (for `AgentDefinition` shape)

**Files likely touched:**

- `packages/agents/src/theoffice_agents/model_resolution.py`
- `packages/agents/tests/test_model_resolution.py`

**Estimated scope:** Medium (2–3 files)

---

#### Task 5: `LiteLLMModelFactory` (Strands + cache)

**Description:** Implement a factory that builds Strands-compatible model instances for a resolved LiteLLM model id, with an **LRU or dict cache** keyed by model id on `app.state` (or on the factory instance stored in state). Spike: confirm dependencies and constructor for `LiteLLMModel` (or the correct Strands class) and document any new optional dependency in `pyproject.toml`.

**Acceptance criteria:**

- [ ] Same model id reused does not leak unbounded memory (bounded cache or explicit policy in code comments + spec alignment).
- [ ] Factory is unit-testable with a **mock** Strands model if real calls require network.

**Verification:**

- [ ] `uv run pytest packages/agents/tests/test_model_factory.py -q` passes (may use mocks).
- [ ] Manual one-liner or REPL optional: construct factory and build model for `ollama/...` in dev (document in task notes if skipped in CI).

**Dependencies:** Task 4

**Files likely touched:**

- `packages/agents/src/theoffice_agents/model_factory.py`
- `packages/agents/pyproject.toml` (if extra deps)
- `packages/agents/tests/test_model_factory.py`
- `packages/agents/src/theoffice_agents/strands_setup.py` (deprecate or narrow to factory internals)

**Estimated scope:** Medium (3–4 files)

---

### Checkpoint: Core logic (after Tasks 4–5)

- [ ] Resolution and env checks fully covered by unit tests.
- [ ] Factory proven for at least one local model id in dev (optional but recommended before Task 7).

---

### Phase 3: HTTP integration

#### Task 6: `InvocationService` + JSON error envelope

**Description:** Implement a service class that accepts parser, registry, resolver, factory; method `run(payload, context) -> dict` for success, or raises / returns `JSONResponse` for errors—**pick one style** and use it consistently. Map domain errors to the spec envelope: **422** `VALIDATION_ERROR`, **501** `MODEL_NOT_CONFIGURED` with `details.resolved_model` and `details.missing_environment_variables`, **500** `INTERNAL_ERROR`. Success dict includes `response`, `stop_reason`, optional `session_id`, `agent`, `model`.

**Acceptance criteria:**

- [ ] Unknown agent id → **422** with standard `error` object.
- [ ] Missing Groq key when model is `groq/...` → **501** with listed env vars.
- [ ] Successful path calls Strands `Agent` with correct `system_prompt` and resolved model (integration may mock `Agent` in unit test).

**Verification:**

- [ ] `uv run pytest packages/agents/tests/test_invocation_service.py -q` passes.

**Dependencies:** Tasks 3, 4, 5 (Task 2 implicit via registry)

**Files likely touched:**

- `packages/agents/src/theoffice_agents/invocation_service.py` (name adjustable)
- `packages/agents/tests/test_invocation_service.py`

**Estimated scope:** Medium (2–3 files)

---

#### Task 7: Wire `agent_runtime.py` and lifespan

**Description:** Load `AgentRegistry` in lifespan (or before app creation); construct resolver with env; construct factory; construct `InvocationService`. Replace current entrypoint implementation: require new JSON shape; remove legacy `_extract_prompt` multi-key behavior. Return Starlette `JSONResponse` for 422/501 so AgentCore passes status through. Log agent id and resolved model at info.

**Acceptance criteria:**

- [ ] `uv run --package theoffice-agents app` starts with valid `agents.yaml` and env.
- [ ] `curl` hello example from `packages/agents/README.md` works for at least one agent when Ollama/LiteLLM is configured.
- [ ] Invalid agent returns **422**; misconfigured Groq returns **501** per spec.

**Verification:**

- [ ] Manual: `curl` **POST** `/invocations` with `{ "agent": "...", "prompt": "..." }`.
- [ ] `uv run pytest packages/agents/tests -q` full suite passes.

**Dependencies:** Task 6

**Files likely touched:**

- `packages/agents/src/theoffice_agents/agent_runtime.py`
- `packages/agents/README.md` (minimal pointer if Task 8 does full doc)

**Estimated scope:** Medium (1–2 files)

---

### Checkpoint: End-to-end (after Tasks 6–7)

- [ ] Spec success criteria 1, 3, 4 exercised manually or via tests.
- [ ] README curl examples updated or flagged obsolete until Task 8 completes.

---

### Phase 4: Documentation and optional integration test

#### Task 8: README and `.env.example` operator table

**Description:** Document required env vars per **supported** provider prefix; document `agents.yaml`; document new invocation JSON; remove or update old “single agent / multi-key prompt” documentation. Align `.env.example` with `DEFAULT_LLM_MODEL` and provider keys.

**Acceptance criteria:**

- [ ] Spec success criterion 5 satisfied (README table matches code’s curated map).
- [ ] Example `agents.yaml` snippet matches shipped file.

**Verification:**

- [ ] Human skim: new developer can configure Ollama + Groq without reading source.

**Dependencies:** Task 7

**Files likely touched:**

- `packages/agents/README.md`
- `packages/agents/.env.example`

**Estimated scope:** Small (2 files)

---

#### Task 9 (optional): ASGI integration test

**Description:** Use `httpx.AsyncClient(app=..., lifespan=...)` or Starlette test client to **POST** `/invocations` with mocked `InvocationService` or mocked model layer so CI does not need Ollama. Assert status codes and JSON shape.

**Acceptance criteria:**

- [ ] At least one test hits real AgentCore routing for `/invocations`.
- [ ] CI remains deterministic (no network).

**Verification:**

- [ ] `uv run pytest packages/agents/tests/test_invocation_contract.py -q` passes.

**Dependencies:** Task 7

**Files likely touched:**

- `packages/agents/tests/test_invocation_contract.py`

**Estimated scope:** Small–Medium (1 file)

---

### Checkpoint: Complete

- [ ] All spec success criteria met.
- [ ] Full `uv run pytest packages/agents/tests -q` green.
- [ ] Ready for code review (`code-review-and-quality` skill).

---

## Parallelization

| Parallel track A | Parallel track B |
|------------------|------------------|
| Task 2 (Registry) | Task 3 (InvocationParser) after Task 1 |
| Task 8 (draft README sections) late, after Task 7 contract is stable | Task 9 once Task 7 done |

**Sequential critical path:** 1 → (2 ∥ 3) → 4 → 5 → 6 → 7 → 8.

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Strands LiteLLM API differs from assumption | High | Task 5 spike first; adjust spec in small follow-up if class names differ |
| LiteLLM Ollama env vars differ from README | Medium | Cross-check LiteLLM docs in Task 4/5; update table in Task 8 |
| AgentCore wraps non-200 responses oddly | Low | Already supports `JSONResponse` pass-through; verify in Task 7 |
| Caching models causes stale credentials | Low | Document cache clear / process restart; optional cache key includes env hash later |

---

## Open questions (carry into implementation)

1. Final name for process default env: **`DEFAULT_LLM_MODEL`** (resolve in Task 4/8).
2. Exact Strands import path for LiteLLM-backed model (Task 5).
3. Whether `UNSUPPORTED_PROVIDER` lives in `error.code` or inside `error.details`—**pick one** in Task 6 and document in README.

---

## Verification (plan quality checklist)

- [x] Every task has acceptance criteria
- [x] Every task has verification steps
- [x] Dependencies explicit
- [x] No task exceeds ~5 files without further split (Task 5 borderline—split factory vs deps if needed)
- [x] Checkpoints between phases
- [ ] Human review and approval before implementation (**required** per skill)
