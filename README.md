# theoffice

A browser-based chat UI backed by a LangGraph agent with a configurable LLM backend.

## Setup

```bash
pip install -r requirements.txt
```

## LLM Configuration

Set `LLM_PROVIDER` explicitly, or let it auto-detect from whichever API key is present.

| Provider | `LLM_PROVIDER` | Env var | Default model |
|---|---|---|---|
| Groq (recommended, free tier) | `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | `claude-haiku-4-5-20251001` |
| Ollama (local, no key needed) | `ollama` | — | `llama3.2` |

Override the model with `LLM_MODEL=<model-name>`.

**Auto-detect order:** `GROQ_API_KEY` → `OPENAI_API_KEY` → `ANTHROPIC_API_KEY` → Ollama fallback.

### Groq — free tier, recommended

1. Sign up at https://console.groq.com (no credit card needed)
2. Create an API key under "API Keys"
3. `export GROQ_API_KEY=gsk_...`

Free tier: 30 req/min, 14,400 req/day.

### OpenAI

1. Visit https://platform.openai.com/api-keys
2. Create a key and add credit ($5 lasts months at this scale)
3. `export OPENAI_API_KEY=sk-...`

### Anthropic

1. Visit https://console.anthropic.com
2. Create a key and add credit
3. `export ANTHROPIC_API_KEY=sk-ant-...`

### Ollama — free, runs locally

1. Install Ollama: https://ollama.com/download
2. Pull a model: `ollama pull llama3.2`
3. Start the service: `ollama serve`

No env vars needed — Ollama is the automatic fallback when no API key is set.

## How a message is processed

```
Browser
  │
  │  POST /chat/stream  (message + session_id)
  ▼
web.py  ─── appends HumanMessage to in-memory session history
  │         runs graph in a thread-pool executor
  │         streams SSE events back to browser as they arrive
  ▼
agent.py  ──  LangGraph graph  (two nodes, always run in order)
  │
  ├─► supervisor node
  │     Reads the current worker list from SQLite (db.py).
  │     If no workers are hired → routes to Manager, done.
  │     Otherwise calls the LLM once with a strict routing prompt:
  │       "Output one word: the staff member's name or MANAGER"
  │     Matches the response against worker names (exact, then substring).
  │     Emits a `routed` SSE event → browser shows the activity pill.
  │
  └─► worker node
        Builds a system prompt for whoever was selected
        (the worker's name/role/system_prompt, or the generic Manager prompt).
        Calls the LLM with the full conversation history.
        Emits a `working` SSE event, then the final `reply` SSE event.
        The reply is labelled "Name · Role" or "Office Manager" in the UI.
```

Both LLM calls go through `llm.py` → the same `BaseChatModel` instance,
so provider and model are configured once and apply to both steps.

Worker records (name, role, system prompt) are persisted in `office.db` (SQLite).
Conversation history is kept in memory per session and is lost on server restart.

## Start the server

```bash
uvicorn app.web:web --host 0.0.0.0 --port 8000 --reload
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

## CLI (one-shot)

```bash
python agent.py
```
