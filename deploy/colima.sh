#!/usr/bin/env bash
# Run familyai in Docker via Colima (Mac).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found. Install Docker CLI and Colima." >&2
  exit 1
fi

if command -v colima >/dev/null 2>&1; then
  if ! colima status 2>/dev/null | grep -qi "running"; then
    echo "Starting Colima..."
    colima start
  fi
else
  echo "Colima not in PATH; assuming Docker is already available." >&2
fi

mkdir -p data

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — set TELEGRAM_BOT_TOKEN before use."
fi

# Default for container: Ollama on the Mac host (not 127.0.0.1 inside the container).
if grep -q '^OLLAMA_URL=http://127.0.0.1:11434' .env 2>/dev/null; then
  if [[ "${FAMILYAI_PATCH_OLLAMA:-1}" == "1" ]]; then
    echo "Tip: in .env use OLLAMA_URL=http://host.docker.internal:11434 for Docker."
  fi
fi

docker compose build
docker compose up -d

echo ""
echo "familyai is up. Logs: docker compose logs -f familyai"
echo "Stop:    docker compose down"
