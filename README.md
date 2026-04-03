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
uv sync --python 3.12
```

Run the BFF:

```bash
uv run --package theoffice-bff theoffice-bff
```

Run the CLI:

```bash
uv run --package theoffice-cli theoffice version
```

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

After the container builds, `post-create.sh` runs `uv sync` and `pnpm install` in `packages/web`.

Node, pnpm (via Corepack), and the AWS CLI are installed through **`devcontainer.json` features** when you use **Dev Containers: Reopen in Container**. A plain `docker compose build` of only the `Dockerfile` does not apply those features; use the editor command so the full image is built correctly.

### Environment

- **`OLLAMA_HOST`**: Inside the **app** container, use `http://ollama:11434` (default in `devcontainer.json`). On the host OS, use `http://localhost:11434` if you need to reach Ollama from outside Docker.
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

Adjust the model name to match what you configure in Strands (`OllamaModel`).
