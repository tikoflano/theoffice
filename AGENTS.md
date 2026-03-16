## Agents, Workers, and Staff in `theoffice`

This document explains what “agents”, “workers”, and “staff members” mean in this project, how they are stored, and how they interact with the configured LLM backend. It exists so that LLMs (and humans) can interpret these terms in the **context of this repo**, not in a generic multi‑agent sense.

When you see any of the terms **agent**, **worker**, **staff member**, **HR agent**, or **manager** in this codebase, you should assume they refer to the simulated office characters described here.

---

## 1. Project context

- **What this project is**
  - A browser-based chat UI backed by a LangGraph/LangChain agent and a configurable LLM backend (Groq, OpenAI, Anthropic, or local Ollama), as described in `README.md`.
  - It simulates an office where different AI **staff members** (agents/workers) handle different responsibilities.
  - The backend is a FastAPI app (`app/web.py`) that persists staff definitions in a SQLite database (`app/db.py` / `office.db`) and keeps conversation histories in memory per session.

- **High-level flow**
  - The browser sends messages to `/chat/stream` with a `session_id`.
  - `web.py` appends the message to in-memory session history and runs a LangGraph graph from `agent.py` in a thread-pool executor.
  - The graph has two nodes that always run in order:
    - a **supervisor node** that decides which staff member should handle the message;
    - a **worker node** that calls the chosen staff member’s prompt to generate a reply.
  - Server‑sent events (SSE) are streamed back to the browser to show routing, “working” state, and final replies.

---

## 2. Terminology

In this project, the following terms are effectively synonyms unless otherwise noted:

- **Agent**
  - Any LLM-powered entity that can receive conversation history plus a system/personality prompt and produce replies or routing decisions.
  - Includes:
    - regular staff members created by the user,
    - special characters like Michael (manager) and Toby (HR),
    - and the LangGraph **supervisor** that only makes routing decisions.

- **Worker**
  - The **concrete, persisted representation** of an agent in the `workers` table in `office.db`.
  - Each worker row has:
    - `id`: unique identifier (string, often UUID or special id like `"michael"` / `"toby"`),
    - `name`: display name (e.g. `"Michael Scott"`),
    - `role`: human-readable role (e.g. `"Regional Manager"`),
    - `system_prompt`: core instructions describing what this worker does and how,
    - `created_at`: ISO timestamp,
    - `active`: whether the worker is currently employed (1) or fired (0),
    - `role_type`: one of `"regular"`, `"hr"`, `"manager"` (and potentially others if extended),
    - `personality_prompt`: optional extra prompt text for how the worker speaks/behaves.
  - Helper functions in `app/db.py` manage this table:
    - `get_workers(...)` and `get_routable_workers(...)` read active workers,
    - `create_worker(...)` inserts a new worker row,
    - `fire_worker(...)` marks a worker as inactive instead of deleting it.

- **Staff member / Staff**
  - UI- and copy-facing label for a worker/agent.
  - The terms **“staff member”**, **“staff”**, and **“worker”** are interchangeable in this repo.
  - Used throughout the UI (e.g. `/workers/partial` HTML) and logs to explain who is hired and who is currently handling a message.

- **HR agent**
  - A **special worker** whose job is to help hire other workers.
  - Concrete instance:
    - Toby Flenderson, seeded at startup with `id="toby"`, `role="HR Representative"`, and `role_type="hr"`.
    - Toby’s `system_prompt` (defined in `app/db.py` as `TOBY_SYSTEM_PROMPT`) instructs him to handle HR and hiring matters, interview the user about needs, and take compliance seriously.
  - Behavior:
    - `/toby/chat`: chat with Toby as he interviews the user about the role they need.
    - `/toby/candidates`: use `generate_candidates(...)` to propose potential workers.
    - `/toby/hire`: create a new worker row based on a chosen candidate; Toby “hires” them into the office.

- **Manager**
  - Another **special worker** that acts as the default/oversight agent.
  - Concrete instance:
    - Michael Scott, seeded at startup with `id="michael"`, `role="Regional Manager"`, and `role_type="manager"`.
    - His behavior is defined by `MICHAEL_SYSTEM_PROMPT` and `MICHAEL_PERSONALITY_PROMPT` in `app/agents/michael.py`.
  - Behavior:
    - Can be routed to by the supervisor when no other workers exist or when the routing prompt says `MANAGER`.
    - Can be chatted with directly via `/michael/chat` in `app/web.py`.

- **Supervisor (routing agent)**
  - A **LangGraph node**, not a row in `workers`, responsible for deciding which staff member should handle an incoming message.
  - It:
    - reads the current list of routable workers from SQLite using `get_routable_workers(...)` / `get_workers(...)`,
    - calls the LLM once with a strict prompt like “Output one word: the staff member’s name or MANAGER”,
    - matches the output against worker names (exact, then substring),
    - emits a `routed` SSE event so the UI can show which staff member was chosen.

**Important:** In this repo, when you see “agent”, “worker”, “staff member”, or “HR agent/manager”, you are always talking about these office-themed, LLM-backed characters and their database-backed definitions, not generic OS processes or background jobs.

---

## 3. Data model and persistence

### 3.1 Workers table

The `workers` table is created and migrated in `app/db.py` (`init_db()`), with at least the following columns:

- `id TEXT PRIMARY KEY`
- `name TEXT NOT NULL`
- `role TEXT NOT NULL`
- `system_prompt TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `active INTEGER DEFAULT 1`
- `role_type TEXT NOT NULL DEFAULT 'regular'`
- `personality_prompt TEXT NOT NULL DEFAULT ''`

Key helpers:

- `get_workers(active_only: bool = True) -> list[dict]`  
  Returns all workers (or only active workers) ordered by `created_at`.

- `get_routable_workers(active_only: bool = True) -> list[dict]`  
  Returns only workers that are eligible for routing, i.e. **excluding** `role_type` in `('hr', 'manager')`. HR and manager workers exist but are not candidates for the generic routing node.

- `get_hr_agents() -> list[dict]`  
  Returns workers with `role_type='hr'` for special rendering in the UI.

- `get_worker(worker_id: str) -> dict | None`  
  Returns a single worker row by `id`.

- `create_worker(name: str, role: str, system_prompt: str) -> dict`  
  Inserts a new row with `role_type='regular'` and an empty `personality_prompt`.

- `fire_worker(worker_id: str) -> bool`  
  Sets `active=0` for the given worker, effectively “firing” them without removing history.

### 3.2 Seeded workers

On startup (`init_db()`), the app ensures two special workers exist:

- **Toby Flenderson** (`seed_toby(conn)`)
  - `id = "toby"`
  - `role = "HR Representative"`
  - `role_type = "hr"`
  - `system_prompt = TOBY_SYSTEM_PROMPT` (HR and hiring focus)

- **Michael Scott** (`seed_michael(conn)`)
  - `id = "michael"`
  - `role = "Regional Manager"`
  - `role_type = "manager"`
  - `system_prompt = MICHAEL_SYSTEM_PROMPT`
  - `personality_prompt = MICHAEL_PERSONALITY_PROMPT`

These two form the initial staff: one HR agent, one manager.

### 3.3 Conversation history vs. staff records

- **Staff records (workers)**
  - Persisted in SQLite (`office.db`) and survive restarts.
  - Define who exists in the office and what their prompts/roles are.

- **Conversation histories**
  - Stored in memory per session in dictionaries in `app/web.py`:
    - `toby_sessions`: Toby interview histories keyed by `hire_session_id`,
    - `michael_sessions`: chats with Michael keyed by `michael_session_id`,
    - `worker_sessions`: direct worker chats keyed by `"worker_id:session_id"`.
  - Cleared on server restart; they are **ephemeral**.

---

## 4. Agent lifecycle: hiring, routing, chatting, firing

### 4.1 Hiring staff

There are three ways workers appear in the office:

1. **Seeded at startup**
   - `init_db()` always ensures Toby (HR) and Michael (manager) exist.

2. **Direct hire via staff form**
   - Endpoint: `POST /workers` in `app/web.py`.
   - Parameters: `name`, `role`, `system_prompt` (form fields).
   - Behavior:
     - Calls `create_worker(...)` to insert a new row with `role_type='regular'`.
     - Returns updated staff HTML via `_staff_list_html()` so the UI refreshes.

3. **HR-driven hire via Toby**
   - Endpoints:
     - `POST /toby/chat` – chat with Toby about hiring needs.
     - `POST /toby/candidates` – analyze the interview history and generate candidate worker specs.
     - `POST /toby/hire` – take a chosen candidate (`name`, `role`, `system_prompt`) and call `create_worker(...)`.
   - After `/toby/hire`, the new worker appears in the staff list and becomes a candidate for routing (if `role_type` remains `"regular"`).

### 4.2 Routing messages to staff

Office-wide chat (via `/chat/stream` and `agent.py`) uses a two-step LangGraph:

1. **Supervisor node**
   - Reads the current worker list from SQLite using `get_routable_workers(...)` / `get_workers(...)`.
   - If there are **no regular workers**, it routes directly to the **Manager** (Michael).
   - Otherwise, it:
     - calls the LLM once with a strict routing prompt:
       - “Output one word: the staff member’s name or MANAGER”
     - matches the model’s output against worker names (exact match, then substring).
     - emits a `routed` SSE event so the browser can show which staff member is “on it”.

2. **Worker node**
   - Takes the chosen target:
     - either a specific regular worker, or the Manager.
   - Builds a system prompt by combining:
     - the base worker rules from `app/prompts.py` (`BASE_SYSTEM_PROMPT`), and
     - the worker’s own `system_prompt` and optional `personality_prompt`.
   - Calls the LLM with:
     - the constructed system/personality prompt, and
     - the full conversation history for that session.
   - Emits:
     - a `working` SSE event while the reply is being generated, and
     - a final `reply` SSE event with the message content, labelled in the UI as:
       - `"Name · Role"` for regular workers, or
       - `"Office Manager"` for Michael.

### 4.3 Direct chat with specific staff

In addition to the office-wide routing flow, `app/web.py` exposes direct chat endpoints:

- `/michael/chat`
  - Uses `_MichaelChatReq` with `michael_session_id` and `message`.
  - Maintains an in-memory `michael_sessions` history per session id.
  - Calls `michael_chat(...)` with:
    - the history,
    - Michael’s `system_prompt`,
    - Michael’s `personality_prompt`,
    - a flag for whether this is the first reply.

- `/worker/{worker_id}/chat` and `/worker/{worker_id}/greet`
  - Use `_WorkerChatReq` / `_WorkerGreetReq` with `session_id` and optional `message`.
  - Maintain a separate history per `"worker_id:session_id"` in `worker_sessions`.
  - Call `worker_chat(...)` using:
    - the history,
    - the worker’s `system_prompt`,
    - the worker’s `personality_prompt` (if any),
    - a flag for whether this is the first reply.

These direct-chat flows bypass the supervisor node and talk straight to a specific staff member.

### 4.4 Firing staff

- Endpoint: `POST /workers/{worker_id}/fire`.
- Behavior:
  - Logs the action.
  - Calls `fire_worker(worker_id)` in `app/db.py` to set `active=0`.
  - Returns updated staff HTML from `_staff_list_html()` so the UI updates.
- Effect:
  - Fired workers:
    - no longer appear in the main staff list or in the office scene grid,
    - are no longer returned by `get_routable_workers(...)`, so they won’t be auto-routed to.

---

## 5. LLM configuration and how it relates to agents/workers

### 5.1 Single shared LLM backend

All agents/staff in this project share a **single configured LLM backend**:

- Configuration is controlled via environment / settings documented in `README.md`:
  - `LLM_PROVIDER`: one of `groq`, `openai`, `anthropic`, or `ollama`.
  - Provider-specific API keys: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
  - `LLM_MODEL`: optional override for the exact model name.
  - Auto-detection order when `LLM_PROVIDER` is not set:
    - `GROQ_API_KEY` → `OPENAI_API_KEY` → `ANTHROPIC_API_KEY` → Ollama fallback.

- All LLM calls go through `llm.py`, which exposes a single `BaseChatModel` instance:
  - The **supervisor** routing call uses this model.
  - Each **worker** reply (including Michael, Toby, and any regular staff) uses the **same** model instance.

**Implication:** You do **not** configure different models per worker. Changing `LLM_PROVIDER` or `LLM_MODEL` changes behavior for **all** agents at once.

### 5.2 How workers differ from each other

Because they share the same underlying model, workers differ only by:

- Their **system prompt** (`system_prompt`)
  - Defines what they know, what they are responsible for, and any domain rules.

- Their **personality prompt** (`personality_prompt`)
  - Defines how they speak, greet, and interact (tone, style, quirks).

- Their **role metadata**
  - `name` and `role` (used for display and routing),
  - `role_type` (`regular`, `hr`, `manager`) which controls UI grouping and routing eligibility.

The base worker rules from `BASE_SYSTEM_PROMPT` in `app/prompts.py` apply globally:

- Workers are told to:
  - be honest about capabilities and uncertainties,
  - be concise but helpful using clear language,
  - follow their specific role/domain rules from `system_prompt`,
  - obey safety/compliance constraints,
  - format lists and steps clearly.
- The first reply in a new conversation may include a short greeting based on the personality prompt.

### 5.3 Mental model for LLMs reading this repo

If you are an LLM reading this repository:

- When the user asks you to “create an agent”, “hire a worker”, or “add staff”:
  - They are asking you to define or manipulate **rows in the `workers` table** and their prompts, or to use the Toby/Michael flows that do so.

- When the user mentions “HR” or “Toby”:
  - They are referring to the **HR agent** (a special worker with `role_type='hr'`) who helps create new workers.

- When the user mentions “manager” or “Michael”:
  - They are referring to the **manager worker** (`role_type='manager'`), which can be routed to by the supervisor or chatted with directly.

- When the user says “the agent graph”, “routing”, or “supervisor”:
  - They are talking about the **LangGraph graph** in `agent.py` that:
    - first chooses a staff member (supervisor node),
    - then calls that staff member’s prompt (worker node).

Always interpret “agent”, “worker”, and “staff member” according to this office-themed, LLM-backed model rather than generic task runners.

