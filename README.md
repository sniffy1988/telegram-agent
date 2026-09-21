# familyai (telegram-agent)

Private Telegram assistant: Ollama, per-chat memory, read-only Home Assistant, web/image search.

## Docker on Mac (Colima)

Images are built on every push to `main` via GitHub Actions (`docker compose`) and pushed to `ghcr.io/sniffy1988/familyai-bot:latest` (multi-arch: amd64 + arm64).

1. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN`.
2. **Colima (recommended on Mac mini):** `./deploy/colima.sh` uses **host network** so the bot can reach **Home Assistant on LAN** (`10.10.30.x`) and Ollama on the Mac (`OLLAMA_URL=http://host.lima.internal:11434` in `.env`).
3. Plain Docker bridge only: `OLLAMA_URL=http://host.docker.internal:11434` — HA on another LAN IP may **not** work from the container.
4. Pull public image (no login usually needed): `docker compose pull`. For private GHCR packages, run `docker login ghcr.io`.
5. Run:

```bash
./deploy/colima.sh
```

`colima.sh` pulls `latest` by default (`FAMILYAI_PULL=1`). Local build: `FAMILYAI_PULL=0 ./deploy/colima.sh`.

Manual:

```bash
mkdir -p data
docker compose pull   # or: docker compose build
docker compose up -d
docker compose logs -f familyai
```

CI uses `docker compose -f docker-compose.yml -f docker-compose.ci.yml build --push`.

Persistent memory is stored in `./data/memory.json`.

### Logs (investigation)

```bash
docker compose logs -f familyai
```

Set **`LOG_LEVEL=DEBUG`** in `.env` and restart for more detail (tool routing, HA entity matches, Ollama timing). Tokens are never logged.

Useful lines:

- `[startup]` — Ollama URL, model, HA URL, whether HA token is set
- `[agent] routed tools` — which tools run for the message
- `[ha]` — Home Assistant HTTP and matched entities
- `[tool]` — `ok=` / `error=` per tool
- `[ollama]` — queue wait and generation time

### Home Assistant unreachable from Docker

If the bot says it cannot connect to HA but the Mac browser opens `http://10.10.30.18:8123`:

```bash
# Colima with host network (default in deploy/colima.sh)
FAMILYAI_COLIMA_LAN=1 ./deploy/colima.sh
```

In `.env`:

```env
HOME_ASSISTANT_URL=http://10.10.30.18:8123
HOME_ASSISTANT_TOKEN=...
OLLAMA_URL=http://host.lima.internal:11434
LOG_LEVEL=DEBUG
```

Check startup probes in logs: `[startup] Home Assistant reachable HTTP 200`.

Manual test from the container:

```bash
docker compose -f docker-compose.yml -f docker-compose.colima.yml exec familyai \
  python -c "import os,httpx; u=os.environ['HOME_ASSISTANT_URL'].rstrip('/')+'/api/'; \
  r=httpx.get(u,headers={'Authorization':'Bearer '+os.environ['HOME_ASSISTANT_TOKEN']},timeout=8); print(r.status_code)"
```

Bridge-only fallback: `colima stop && colima start --network-address` (then try bridge compose again).

## Native (no Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

## Tests

```bash
pytest
```
