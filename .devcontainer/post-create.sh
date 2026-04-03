#!/usr/bin/env bash
set -euo pipefail

# postCreateCommand runs as `remoteUser` (vscode). `su vscode` from that user prompts for a
# password. If the lifecycle ever runs as root, use sudo instead of su.
run_cmd() {
  if [[ "$(id -u)" -eq 0 ]]; then
    sudo -u vscode -H bash -lc "$1"
  else
    bash -lc "$1"
  fi
}

run_cmd 'curl -LsSf https://astral.sh/uv/install.sh | sh'
run_cmd 'export PATH="/home/vscode/.local/bin:${PATH}" && cd /workspaces/theoffice && uv sync --python 3.12 --group dev'
run_cmd 'export PATH="/home/vscode/.local/bin:${PATH}" && cd /workspaces/theoffice/packages/web && pnpm install'
