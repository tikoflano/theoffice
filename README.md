# theoffice

Python monorepo (uv) for Strands Agents, Amazon Bedrock AgentCore, a FastAPI BFF, a Typer CLI, and a React UI (pnpm). Local LLMs use [Ollama](https://ollama.com/) via a Docker Compose sidecar in development.

## Layout

| Path | Role |
|------|------|
| `packages/agents` | Strands, AgentCore, Ollama-capable agent code |
| `packages/shared` | Shared Pydantic schemas and types |
| `packages/bff` | Backend-for-frontend (FastAPI) |
| `packages/cli` | Typer CLI (`theoffice`) |
| `packages/web` | React + Vite (pnpm, not part of the uv workspace) |

## Prerequisites

- Python **3.12** (see `.python-version` for [uv](https://docs.astral.sh/uv/))
- Optional: [Docker](https://docs.docker.com/get-docker/) for the Dev Container and Ollama

## Python (host)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd /path/to/theoffice
uv sync --python 3.12 --group dev
```

Run the BFF:

```bash
uv run --package theoffice-bff theoffice-bff
```

Run the CLI:

```bash
uv run --package theoffice-cli theoffice version
```

### Custom commands (shell tasks)

[uv](https://docs.astral.sh/uv/) does not define arbitrary shell commands in `pyproject.toml` (only Python entry points via `[project.scripts]`). This repo uses [Poethepoet](https://poethepoet.natn.io/) as a dev dependency so you can name and run shell snippets with `uv run`.

1. Ensure the dev group is installed (`uv sync --python 3.12 --group dev`, as above).
2. List tasks: `uv run poe --help`
3. Run a task: `uv run poe <task-name>` (for example `uv run poe ping` polls `/ping` with `curl` and `jq`; override the URL with `PING_URL`).

To add a task, edit the root `pyproject.toml` table `[tool.poe.tasks]`. Use a string for a simple command, or `{ shell = "..." }` when you need pipes, loops, or other shell features:

```toml
[tool.poe.tasks]
my-task = "pytest packages/bff/tests"
watch-logs = { shell = "tail -f /tmp/app.log" }
```

See the [Poethepoet task reference](https://poethepoet.natn.io/tasks/) for sequences, arguments, `cwd`, and environment options.

## Web UI (host)

Requires Node **20+** (Vite 5). Use pnpm via Corepack:

```bash
corepack enable && corepack prepare pnpm@9.15.9 --activate
cd packages/web
pnpm install
pnpm dev
```

`packages/web` defaults to calling the BFF through the Vite dev proxy at `/api` (see `vite.config.ts`). Start the BFF on port **8000** or set `VITE_API_URL` (see `packages/web/.env.example`).

## Dev Container

1. Open this repository in VS Code or Cursor.
2. **Dev Containers: Reopen in Container** (Docker must be running).
3. The Compose stack includes:
   - **app**: Python 3.12, uv, Node (LTS), pnpm, AWS CLI; workspace at `/workspaces/theoffice`
   - **ollama**: Ollama on port **11434** (with a persistent volume)

After the container builds, `post-create.sh` runs `uv sync --group dev` and `pnpm install` in `packages/web`.

Node, pnpm (via Corepack), and the AWS CLI are installed through **`devcontainer.json` features** when you use **Dev Containers: Reopen in Container**. A plain `docker compose build` of only the `Dockerfile` does not apply those features; use the editor command so the full image is built correctly.

### Environment

- **`OLLAMA_API_BASE`**: Base URL for the Ollama HTTP API. Inside the **app** container, `http://ollama:11434` is set in `devcontainer.json` / Compose. On the host OS, use `http://localhost:11434` (or the published port) when tools run outside Docker.
- **AWS**: Configure credentials for Bedrock/AgentCore (for example `aws configure sso` or environment variables). Nothing is baked into the image.

### Ports (forwarded)

- **8000** — BFF (`uv run --package theoffice-bff theoffice-bff`)
- **5173** — Vite (`pnpm dev` in `packages/web`)
- **11434** — Ollama API

## Ollama models

With the Compose stack running, pull a model inside the Ollama container, for example:

```bash
docker compose -f .devcontainer/docker-compose.yml exec ollama ollama pull llama3.2
```

Adjust the model name to match your agent registry / `DEFAULT_LLM_MODEL` (e.g. `ollama/llama3.2`).
