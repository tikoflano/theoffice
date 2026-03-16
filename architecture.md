### System Architecture of `theoffice`

This document describes the end‑to‑end architecture of the app: how staff are modeled, how the Phaser office UI works, how user interactions flow through the backend, how LangGraph is used for different interaction types, and how the UI and graph stay in sync so the experience feels like a game rather than a raw tool.

---

## 1. Domain Model: Staff, Manager, HR, and Workers

### 1.1 Workers and special roles

- **Workers table (SQLite)**  
  Each staff member (agent) is a row in the `workers` table (managed by `app/db.py`):
  - `id`: unique identifier (`"michael"`, `"toby"`, or a UUID).
  - `name`: display name, shown in the UI (e.g. `"Michael Scott"`).
  - `role`: human‑facing role (e.g. `"Regional Manager"`, `"Data Engineer"`).
  - `system_prompt`: core behavioral instructions (what the worker does, domain expertise).
  - `personality_prompt`: optional style/persona.
  - `role_type`: `"manager"`, `"hr"`, or `"regular"`.
  - `active`: whether they’re currently employed.
  - `created_at`: for metadata, future features, and gamification.

- **Special workers**
  - **Manager (Michael)**
    - `id = "michael"`, `role_type = "manager"`.
    - Primary job: **decide how work should be delegated to other agents** and coordinate them.
    - Users can talk to Michael directly; other agents can also “ask Michael” to delegate work.
  - **HR Agent (Toby)**
    - `id = "toby"`, `role_type = "hr"`.
    - Handles hiring flows: interviews the user, proposes candidates, and inserts new rows into the workers table.

- **Regular workers**
  - `role_type = "regular"`.
  - Hired by the user (directly or via Toby).
  - Represent specialized staff (e.g. “Backend Engineer”, “Research Analyst”).

### 1.2 Conversation state vs. staff records

- **Staff records** (workers) are persisted in SQLite and survive restarts.
- **Conversation histories** are ephemeral, in‑memory structures:
  - Per worker direct chat (keyed by `"worker_id:session_id"`).
  - Per Michael session (keyed by `michael_session_id`).
  - Per Toby hire session.
  - For the new generalized `/chat` endpoint, a **chat session** is keyed by `session_id` and contains a list of messages (with metadata like sender/agent id and interaction type).

---

## 2. Frontend Architecture: Phaser Office + Panels

### 2.1 Office layout and avatars

- The main UI is a **Phaser 3 canvas** (`static/office.js`) rendered inside `index.html`.
- On load, the frontend:
  1. Calls `/workers/positions` to get all active non‑HR, non‑manager workers with an assigned “slot”.
  2. Draws:
     - An office grid and border.
     - **Michael’s desk** (fixed position).
     - **Toby’s desk** (fixed position).
     - A desk/character circle for each worker, with:
       - Color, initials, and tooltip (`name` + `role`).
       - Context menu entries (e.g. “Talk with Michael”, “Hire Staff”, “Talk to Alice”).

- The office canvas is **camera‑driven**:
  - You can pan with arrow keys or mouse drag.
  - When interesting interactions occur (e.g. a worker starts “thinking”), the camera can pan to that avatar.

### 2.2 Interaction points

Key interaction affordances in the UI:

- **Click Michael**
  - Context menu: “Talk with Michael”.
  - Opens the Michael chat panel (right‑side slide‑in).
- **Click a worker**
  - Context menu: “Talk to {Worker}”.
  - Opens the worker chat panel (direct 1:1).
- **Click Toby**
  - Context menu: “Hire Staff”.
  - Opens the hire panel and starts the Toby interview/candidate flow.

Each of these interactions ultimately becomes a **chat request** to the backend, specifying:

- The **participants** (Michael, one worker, or multiple).
- The **action / interaction type** (simple message, delegated task, meeting, etc.).
- The **session_id** that binds together related turns.

---

## 3. API: Single Flexible Chat Endpoint

### 3.1 Request shape

All chat‑like interactions converge on **one HTTP endpoint**, e.g. `POST /chat`:

```json
{
  "session_id": "uuid-for-this-conversation",
  "participants": ["michael", "worker-db", "worker-frontend"],
  "from": "user-123",
  "action": "message",
  "message": "I need help designing a database schema."
}
```

- **`session_id`**: Logical chat thread id. The backend uses this to:
  - Load and persist in‑memory history for this conversation.
- **`participants`**:
  - Minimal set of agents involved in this interaction.
  - Examples:
    - `["michael"]`: “Talk to Michael” (manager orchestrated).
    - `["worker-db"]`: direct worker 1:1 chat.
    - `["michael","worker-db","worker-frontend"]`: orchestrated group scenario with Michael as manager.
- **`from`**:
  - Who is speaking in this turn:
    - A human (e.g. `"user-123"`),
    - Michael (`"michael"`),
    - Or another agent (`"worker-db"`).
  - Enables **agent‑to‑agent interactions** (e.g. a worker asking Michael to delegate).
- **`action`**:
  - Declares the high‑level type of interaction, not the routing:
    - `"message"`: standard chat turn.
    - `"delegate"`: explicitly about task allocation.
    - `"meeting"`: multi‑agent, structured “meeting” interaction.
    - `"broadcast"`, `"standup"`, etc. can be added incrementally.
- **`message`**:
  - The natural language content for this turn.

### 3.2 Response shape

The backend returns a **multi‑turn bundle**:

```json
{
  "session_id": "uuid-for-this-conversation",
  "turns": [
    { "agent": "michael",     "content": "I'll coordinate this for you..." },
    { "agent": "worker-db",   "content": "Here is the proposed schema..." },
    { "agent": "worker-front","content": "I’ll suggest the API endpoints..." }
  ]
}
```

- Each turn is associated with an `agent` id and content.
- The frontend:
  - Renders speech bubbles for each agent over their avatars.
  - Updates chat panels (Michael or worker) based on which panel is open.
- For long or multi‑step flows, the server can stream **events** as they happen (see below), not just a single response.

---

## 4. Backend: FastAPI Request Handling

### 4.1 Endpoint responsibilities

The FastAPI route for `POST /chat` is intentionally thin:

1. **Validation** (Pydantic model)
   - Ensures `session_id`, `participants`, `from`, `action`, and `message` are present and well‑typed.
   - Validates that each `participant` corresponds to an existing (and active) worker in the DB.

2. **Context assembly**
   - Loads worker records for all `participants` using `get_worker(...)`.
   - Looks up or initializes in‑memory **chat history** for `session_id`.
   - Appends the new user/agent message into `history` with metadata (`from`, `action`, timestamp).

3. **Graph selection**
   - Chooses **which LangGraph graph to execute**, based on:
     - `action` (e.g. `"message"`, `"delegate"`, `"meeting"`),
     - `participants` (e.g. presence of `"michael"`, number of workers).

4. **Graph execution**
   - Calls the selected graph runner function (e.g. `run_direct_chat_graph`, `run_delegate_graph`, `run_meeting_graph`) in a **thread‑pool executor** so LLM calls don’t block the event loop.
   - Passes in a **typed state object** containing:
     - `history`,
     - `participants`,
     - `from`,
     - `workers` (id → DB row),
     - `action`,
     - any additional metadata.

5. **History update and response**
   - The graph returns a list of turns (`[{agent, content}, ...]`) plus any internal state updates.
   - The server:
     - Appends those AI turns to `history` (with `agent` metadata).
     - Converts them to the API’s `turns` array.
   - Sends back either:
     - A **single JSON response** with all turns, or
     - A stream of **events** if using SSE/WebSockets for richer animation.

---

## 5. LangGraph: Multiple Graphs for Different Interaction Types

### 5.1 Shared state structure

Each graph operates on a shared conceptual state, e.g.:

```python
class ChatState(TypedDict):
    history: list[BaseMessage]
    participants: list[str]
    from_id: str
    action: str
    workers: dict[str, WorkerRow]
    outputs: list[dict]
    pending_tasks: list[dict]
```

- Graphs can extend or ignore fields as needed.
- Shared **helper nodes** (e.g. “call one worker”) can be reused across graphs.

### 5.2 Example graphs

#### a) Direct Chat Graph (`action = "message"`, single participant)

- **Use case**: 1:1 chat with Michael or one worker.
- **Flow**:
  1. Single node: `direct_chat_node`.
  2. Builds a system prompt from:
     - `BASE_SYSTEM_PROMPT`,
     - Either Michael or worker’s `system_prompt` and `personality_prompt`.
  3. Invokes LLM once with `history + new message`.
  4. Appends a single turn to `outputs`.
- **Behavior**:
  - Simple, low‑latency, no fan‑out, no orchestration.

#### b) Delegated Task Graph (`action = "delegate"`, `participants` includes Michael)

- **Use case**: User asks Michael to “handle” something; Michael decides who should do what.
- **Flow (nodes)**:
  1. `michael_plan`:
     - LLM as Michael.
     - Reads `history`, worker roster for the participants (and possibly others), and the current request.
     - Produces:
       - A managerial reply to the user.
       - A list of **pending_tasks** specifying assignees and instructions.
  2. `fanout_workers` (if `pending_tasks` not empty):
     - For each task: call the designated worker with:
       - Their system/personality prompt.
       - Context describing Michael’s delegation and the user’s request.
     - Collects each worker’s result into `outputs`.
  3. `michael_summarize` (optional, if Michael is a participant):
     - Feeds worker outputs back into Michael.
     - LLM as Michael summarizes/composes a final manager‑style response.

- **Behavior**:
  - Michael is the **decision‑maker**; workers do the detailed work.
  - The user gets both:
    - A sense of Michael’s plan,
    - Results produced by the delegated agents.

#### c) Meeting / Multi‑Agent Graph (`action = "meeting"`)

- **Use case**: User calls a “meeting” with Michael and multiple workers.
- **Flow (nodes)**:
  1. `michael_open_meeting`:
     - Michael clarifies the agenda, sets expectations.
  2. `round_robin_workers`:
     - Each worker in `participants` (excluding Michael) is called in turn.
     - Each sees:
       - The meeting goal,
       - Prior contributions from other agents,
       - Relevant history.
     - Outputs are collected in `outputs`.
  3. `michael_wrap_up`:
     - Michael reads all workers’ contributions.
     - Summarizes the meeting, decisions, and next steps into a final message.

- **Behavior**:
  - Highly orchestrated pattern that remains separate from direct chat logic.
  - Easy to expand with standup/all‑hands/etc. variations later.

---

## 6. Eventing and Animation: Keeping Graph and UI in Sync

The app is intentionally **game‑like**, so the backend must respect the pacing and visibility of animations.

### 6.1 Event types

At **each meaningful step** in a graph, a node can emit structured events (via SSE or WebSockets), such as:

- `routed` / `delegated_to`:
  - “Michael assigns a task to worker‑db”.
  - UI can animate:
    - A line from Michael to the worker,
    - Worker avatar “thinking” dots starting.
- `working`:
  - Specific agent is currently “thinking”.
  - UI shows animated dots over that avatar.
- `reply`:
  - Agent has produced a message.
  - UI:
    - Shows a speech bubble over the avatar,
    - Updates chat panel history.
- `meeting_phase`:
  - Transitions in multi‑agent flows (`"opening"`, `"worker_round"`, `"wrap_up"`).
  - UI can animate avatars moving, gathering, or highlighting who’s speaking.

### 6.2 Synchronizing with animations

**Crucial requirement**:  
The graph execution needs to stop for the animation to complete, otherwise the sequence of animations might break. The design favors a smooth, game‑like experience over raw throughput.

To respect this:

- Each node that triggers an animation:
  1. **Emits an event** to the frontend describing the next animation to perform.
  2. **Waits for acks or a delay** before continuing:
     - Either:
       - The frontend sends back a short “animation_complete” signal (via a lightweight endpoint or WebSocket).
       - Or the node uses a conservative delay that roughly matches animation duration.
  3. Only **after** this synchronization does the graph move to the next step.

Implementation strategy:

- For SSE:
  - Server sends an event describing the animation.
  - Uses an `asyncio.sleep` or similar mechanism for pacing, or a companion endpoint for acks.
- For WebSockets:
  - Server sends `"start_animation": { ... }`.
  - Awaits a `"animation_done": { ... }` message from the client before continuing.

This ensures:

- The **visual narrative** matches the logical one (e.g. you see Michael “route” to a worker *before* the worker replies).
- Complex multi‑agent graphs still feel like a sequence of understandable actions, not a flood of instant text.

---

## 7. Extensibility and Future Features

The architecture is designed to be **extensible**:

- **New interaction types**:
  - Add a new `action` value and a corresponding graph (e.g. `standup_graph`, `all_hands_graph`).
  - Reuse shared nodes (`call_worker`, `call_michael`, `fanout_workers`, `michael_summarize`).
- **Richer office behaviors**:
  - Add agent‑specific flags (e.g. “out of office”, “on call”, “party mode”) in DB and pass them into graph state.
  - Modify prompts and routing decisions accordingly.
- **More advanced animation hooks**:
  - Attach richer metadata to events (duration, easing, camera target).
  - Use the same event/ack pattern to ensure graph steps and Phaser animations stay aligned.

Overall, the system becomes a **layered architecture**:

- **Data/model**: workers and conversations in SQLite + memory.
- **Backend/API**: FastAPI, a single flexible `/chat` endpoint, plus support endpoints for staff and HR.
- **Orchestration**: multiple LangGraph graphs, each tailored to an interaction pattern, sharing common nodes.
- **UI/experience**: Phaser office, panels, and animations driven by backend events, with synchronization so the game‑like experience always reflects the underlying agent graph.

