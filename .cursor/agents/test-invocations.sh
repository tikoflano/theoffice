#!/usr/bin/env bash
# Smoke-test theoffice-agents AgentCore HTTP server: free port, start app, POST /invocations, assert outcome.
# OLLAMA_API_BASE defaults to http://ollama:11434 (Docker Compose / Dev Container service name).
# Override in packages/agents/.env or the environment (e.g. http://localhost:11434 on the host OS).
# Usage (from repo root or any cwd):
#   .cursor/agents/test-invocations.sh
#   .cursor/agents/test-invocations.sh local "Say hello in one sentence."
#   AGENT_PORT=8080 EXPECT_NON_EMPTY_RESPONSE=1 .cursor/agents/test-invocations.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

AGENT_PORT="${AGENT_PORT:-8080}"
BASE_URL="${BASE_URL:-http://127.0.0.1:${AGENT_PORT}}"
PING_URL="${PING_URL:-$BASE_URL/ping}"
INVOCATIONS_URL="${INVOCATIONS_URL:-$BASE_URL/invocations}"
STARTUP_TIMEOUT_SEC="${STARTUP_TIMEOUT_SEC:-45}"
EXPECT_NON_EMPTY_RESPONSE="${EXPECT_NON_EMPTY_RESPONSE:-1}"

AGENT_ID="${1:-local}"
PROMPT_TEXT="${2:-Say hello in one sentence.}"

# Escape prompt for JSON string (minimal: backslash, quotes, newlines)
json_escape() {
  python3 -c 'import json,sys; s=json.dumps(sys.stdin.read()); print(s[1:-1], end="")' <<<"$1"
}

PROMPT_ESC="$(json_escape "$PROMPT_TEXT")"
POST_BODY="{\"agent\": \"${AGENT_ID}\", \"prompt\": \"${PROMPT_ESC}\"}"

free_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
  fi
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti ":${port}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill ${pids} 2>/dev/null || true
    fi
  fi
  sleep 1
}

if [[ -f "$REPO_ROOT/packages/agents/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/packages/agents/.env"
  set +a
fi

# Ollama HTTP API (for ollama/… models). Prefer Compose hostname, not 127.0.0.1, in this workspace.
OLLAMA_API_BASE="${OLLAMA_API_BASE:-http://ollama:11434}"
export OLLAMA_API_BASE

echo "==> Free port ${AGENT_PORT} (if in use)"
free_port "$AGENT_PORT"

echo "==> Starting theoffice-agents (uv run --package theoffice-agents app)"
uv run --package theoffice-agents app &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "==> Waiting for GET ${PING_URL}"
deadline=$((SECONDS + STARTUP_TIMEOUT_SEC))
while (( SECONDS < deadline )); do
  if curl -sf "$PING_URL" >/dev/null; then
    echo "    Ping OK"
    break
  fi
  sleep 0.5
done
if ! curl -sf "$PING_URL" >/dev/null; then
  echo "ERROR: Server did not become healthy within ${STARTUP_TIMEOUT_SEC}s" >&2
  exit 1
fi

echo "==> POST ${INVOCATIONS_URL}"
RESP="$(curl -sS -X POST "$INVOCATIONS_URL" \
  -H "Content-Type: application/json" \
  -d "$POST_BODY")" || true

echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "$RESP"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 required for JSON checks" >&2
  exit 1
fi

CHECK=$(printf '%s' "$RESP" | python3 -c "
import json, sys
raw = sys.stdin.read()
expect_non_empty = int(sys.argv[1])
try:
    data = json.loads(raw)
except json.JSONDecodeError as e:
    print('INVALID_JSON:' + str(e))
    raise SystemExit(0)
if 'error' in data:
    err = data['error']
    code = err.get('code', '?')
    msg = err.get('message', '')
    print('API_ERROR:' + str(code) + ':' + str(msg))
    raise SystemExit(0)
resp = data.get('response')
if resp is None:
    print('MISSING_RESPONSE_FIELD')
    raise SystemExit(0)
if not isinstance(resp, str):
    print('BAD_RESPONSE_TYPE')
    raise SystemExit(0)
if expect_non_empty and len(resp.strip()) == 0:
    print('EMPTY_RESPONSE')
    raise SystemExit(0)
print('OK')
" "$EXPECT_NON_EMPTY_RESPONSE")

case "$CHECK" in
  OK)
    echo "==> RESULT: PASS"
    exit 0
    ;;
  INVALID_JSON:*)
    echo "==> RESULT: FAIL — ${CHECK#INVALID_JSON:}" >&2
    exit 1
    ;;
  API_ERROR:*)
    echo "==> RESULT: FAIL — ${CHECK#API_ERROR:}" >&2
    exit 1
    ;;
  MISSING_RESPONSE_FIELD|BAD_RESPONSE_TYPE|EMPTY_RESPONSE)
    echo "==> RESULT: FAIL — $CHECK" >&2
    exit 1
    ;;
  *)
    echo "==> RESULT: FAIL — $CHECK" >&2
    exit 1
    ;;
esac
