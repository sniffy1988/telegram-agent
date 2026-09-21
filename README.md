# familyai (telegram-agent)

Private Telegram assistant: Ollama, per-chat memory, read-only Home Assistant, web/image search.

## Docker on Mac (Colima)

1. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN`.
2. For Docker, set `OLLAMA_URL=http://host.docker.internal:11434` (Ollama on the Mac host).
3. Run:

```bash
./deploy/colima.sh
```

Manual:

```bash
mkdir -p data
docker compose build
docker compose up -d
docker compose logs -f familyai
```

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
