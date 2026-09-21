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

COMPOSE=(docker compose -f docker-compose.yml)
# Default on Colima: host network so HA on LAN (10.10.x) and Ollama on Mac work.
if [[ "${FAMILYAI_COLIMA_LAN:-1}" == "1" ]]; then
  COMPOSE+=(-f docker-compose.colima.yml)
  echo "Using docker-compose.colima.yml (host network, LAN HA)."
  echo "Ollama on Mac: set OLLAMA_URL=http://host.lima.internal:11434 in .env"
fi

if grep -q '^OLLAMA_URL=http://127.0.0.1:11434' .env 2>/dev/null; then
  if [[ "${FAMILYAI_PATCH_OLLAMA:-1}" == "1" ]]; then
    if [[ "${FAMILYAI_COLIMA_LAN:-1}" == "1" ]]; then
      echo "Tip: in .env use OLLAMA_URL=http://host.lima.internal:11434 (Colima host network)."
    else
      echo "Tip: in .env use OLLAMA_URL=http://host.docker.internal:11434 for Docker bridge."
    fi
  fi
fi

export FAMILYAI_IMAGE="${FAMILYAI_IMAGE:-ghcr.io/sniffy1988/familyai-bot}"
export FAMILYAI_TAG="${FAMILYAI_TAG:-latest}"

if [[ "${FAMILYAI_PULL:-1}" == "1" ]]; then
  echo "Pulling ${FAMILYAI_IMAGE}:${FAMILYAI_TAG} (set FAMILYAI_PULL=0 to build locally)..."
  if "${COMPOSE[@]}" pull; then
    echo "Using image from registry."
  else
    echo "Pull failed — building locally..."
    "${COMPOSE[@]}" build
  fi
else
  "${COMPOSE[@]}" build
fi

"${COMPOSE[@]}" up -d

echo ""
echo "familyai is up."
echo "Logs:    docker compose -f docker-compose.yml -f docker-compose.colima.yml logs -f familyai"
echo "Stop:    docker compose -f docker-compose.yml -f docker-compose.colima.yml down"
echo "HA test: docker compose ... logs familyai 2>&1 | grep startup"
