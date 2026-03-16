### TODO – Architecture Migration to Unified `/chat`

#### Phase 1: Baseline + Cleanup
- [ ] Audit current behavior of `/michael/chat`, `/worker/{id}/chat`, `/worker/{id}/greet`, and Toby endpoints; document how `office.js` calls them.
- [ ] Identify and classify legacy routing / LangGraph code (e.g. old supervisor, `/chat/stream`) as keep, adapt, or delete.
- [ ] Align `README.md`, `AGENTS.md`, and `architecture.md` so they consistently describe the current (interim) state and clearly mark future behavior.

#### Phase 2: Data & Session Layer Prep
- [ ] Introduce a generic chat session store (e.g. `chat_sessions: dict[session_id, list[BaseMessage]]`) separate from existing Michael/worker/Toby dicts.
- [ ] Define an internal message schema (e.g. `from_id`, `agent_id`, `action`, timestamp) and ensure it’s attached to history entries.
- [ ] Add helpers to translate between old per-endpoint histories and the new generic session representation (for transition/backwards-compat).

#### Phase 3: Core `/chat` API
- [ ] Define `ChatRequest` and `ChatResponse` Pydantic models.
- [ ] Implement `POST /chat` in `app/web.py`:
  - [ ] Validate participants and action.
  - [ ] Load/initialize session history.
  - [ ] Append the incoming message with metadata.
- [ ] Wire `/chat` to a stubbed graph runner that returns mock/static turns to validate the API shape end-to-end.

#### Phase 4: LangGraph Infrastructure
- [ ] Create a new module (e.g. `app/agent/graphs.py`) for LangGraph-based orchestration, separate from any legacy routing code.
- [ ] Define shared `ChatState` (history, participants, from_id, action, workers, outputs, pending_tasks).
- [ ] Implement a small graph runner wrapper (e.g. `run_graph(action: str, state: ChatState) -> ChatState`).
- [ ] Implement shared helper nodes:
  - [ ] `call_michael` for a single Michael turn.
  - [ ] `call_worker` for a single worker turn.
  - [ ] Utilities to append `outputs` and to hook into event emission.

#### Phase 5: Direct Chat Graph
- [ ] Implement `direct_chat_graph` (condition: `action == "message"` and a single participant).
- [ ] Route matching `/chat` requests to `direct_chat_graph` and return its outputs.
- [ ] Refactor `/michael/chat` and `/worker/{id}/chat` to internally delegate to `/chat` / `direct_chat_graph` for backwards compatibility.

#### Phase 6: Delegated Task Graph
- [ ] Implement `delegate_graph` (condition: `action == "delegate"` and `participants` includes `"michael"`):
  - [ ] `michael_plan` node to produce manager reply + `pending_tasks`.
  - [ ] `fanout_workers` node to execute delegated tasks.
  - [ ] Optional `michael_summarize` node for final manager-style synthesis.
- [ ] Route `action == "delegate"` requests to `delegate_graph`.
- [ ] Update Michael’s system prompt to emphasize delegation/orchestration responsibilities in this mode.

#### Phase 7: Meeting / Multi-Agent Graph
- [ ] Implement `meeting_graph` (condition: `action == "meeting"` and `participants` includes `"michael"` plus ≥1 worker):
  - [ ] `michael_open_meeting` node (set agenda).
  - [ ] `round_robin_workers` node (each worker contributes in turn).
  - [ ] `michael_wrap_up` node (decisions + next steps).
- [ ] Route `action == "meeting"` requests to `meeting_graph`.
- [ ] Add minimal UI affordance to start a meeting with selected participants.

#### Phase 8: Eventing & Animation Sync
- [ ] Decide and implement transport for step-wise events (SSE vs WebSockets).
- [ ] Define a standard event schema (e.g. `routed`, `delegated_to`, `working`, `reply`, `meeting_phase`, `error`).
- [ ] Emit events from key graph nodes (`call_michael`, `call_worker`, `michael_plan`, `fanout_workers`, `round_robin_workers`, etc.).
- [ ] Implement animation synchronization:
  - [ ] Add a lightweight ack protocol (e.g. `animation_done`) or conservative delays.
  - [ ] Ensure graphs await these sync points before advancing to the next node.

#### Phase 9: Frontend Refactor to `/chat`
- [ ] Update Michael panel to call `/chat` with `participants: ["michael"]`, `action: "message"`, and handle multi-turn responses.
- [ ] Update worker panels to call `/chat` instead of `/worker/{id}/chat` and `/worker/{id}/greet`.
- [ ] Integrate backend events into `office.js`:
  - [ ] Start/stop “thinking” dots based on `working` events.
  - [ ] Draw delegation/routing lines for `routed` / `delegated_to`.
  - [ ] Pan camera to active speakers.
  - [ ] Show speech bubbles in the correct sequence based on `reply` events.

#### Phase 10: Decommission Legacy Paths
- [ ] Mark legacy chat endpoints (`/michael/chat`, `/worker/{id}/chat`, etc.) as deprecated once `/chat` is stable.
- [ ] Remove or archive any remaining supervisor-based or `/chat/stream` routing code.
- [ ] Clean up documentation references to the old supervisor node and office-wide stream.
- [ ] Add validation to discourage or block introduction of new one-off chat endpoints that bypass `/chat`.

#### Phase 11: Testing, Observability, and Hardening
- [ ] Add unit tests for `direct_chat_graph`, `delegate_graph`, and `meeting_graph` with mocked LLM calls.
- [ ] Add integration tests for `/chat` covering:
  - [ ] Direct Michael chat.
  - [ ] Direct worker chat.
  - [ ] Delegated flows.
  - [ ] Meeting flows with multiple participants.
- [ ] Add structured logging around graph execution (graph name, node name, participants, action, session_id).
- [ ] Define and implement clear error-handling behavior and corresponding UI states for failures (LLM, graph, or validation errors).

