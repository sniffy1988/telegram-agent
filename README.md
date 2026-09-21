# familyai (telegram-agent)

Private Telegram assistant: Ollama, per-chat memory, read-only Home Assistant, web/image search.

## Docker on Mac (Colima)

Images are built on every push to `main` via GitHub Actions (`docker compose`) and pushed to `ghcr.io/sniffy1988/familyai-bot:latest` (multi-arch: amd64 + arm64).

1. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN`.
2. For Docker, set `OLLAMA_URL=http://host.docker.internal:11434` (Ollama on the Mac host).
3. Pull public image (no login usually needed): `docker compose pull`. For private GHCR packages, run `docker login ghcr.io`.
4. Run:

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
