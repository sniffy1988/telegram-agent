# familyai (telegram-agent)

Private Telegram assistant: Ollama, per-chat memory, Home Assistant (read-only by default; optional confirmed control), web/image search.

## Docker on Mac (Colima)

Images are built on every push to `main` via GitHub Actions (`docker compose`) and pushed to `ghcr.io/sniffy1988/familyai-bot:latest` (multi-arch: amd64 + arm64).

### Только образ (без клонирования репозитория)

На Mac mini с Colima и HA в LAN (`10.10.x`) нужен **host network** — иначе контейнер не достучится до Home Assistant.

```bash
mkdir -p ~/familyai/data && cd ~/familyai

curl -fsSLO https://raw.githubusercontent.com/sniffy1988/telegram-agent/main/docker-compose.pull.yml
mv docker-compose.pull.yml docker-compose.yml

# .env: TELEGRAM_BOT_TOKEN, HOME_ASSISTANT_TOKEN, при необходимости HOME_ASSISTANT_URL
nano .env

docker compose pull
docker compose up -d
docker compose logs -f familyai
```

Минимальный шаблон переменных: [`deploy/.env.example.minimal`](deploy/.env.example.minimal).

В `.env` для Colima: `OLLAMA_URL=http://host.lima.internal:11434`.

Обновление: `docker compose pull && docker compose up -d`.

Эквивалент без compose:

```bash
docker pull ghcr.io/sniffy1988/familyai-bot:latest
docker rm -f familyai-bot 2>/dev/null; mkdir -p ~/familyai/data
docker run -d --name familyai-bot --network host --env-file ~/familyai/.env \
  -e MEMORY_PATH=/app/data/memory.json \
  -e OLLAMA_URL=http://host.lima.internal:11434 \
  -v ~/familyai/data:/app/data --restart unless-stopped \
  ghcr.io/sniffy1988/familyai-bot:latest
```

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

### Что спросить в Telegram (Home Assistant)

Ответы по погоде, курсу, пыльце и т.д. формируются **напрямую из HA** (без выдумок модели).

| Тема | Примеры |
|------|---------|
| Погода / улица | «какая температура», «яка погода» |
| Комнаты | «а в комнатах?», «температура в доме» |
| Воздух | «pm2.5», «влажность», «качество воздуха» |
| Амброзия / пыльца | «амброзия», «ragweed», «пыльца silam» |
| Курс | «курс доллара», «cartel», «євро» |
| АЗС / топливо | «дизель/соляра», «ДП», «socar», «цена на азс», «бензин 95», «wog» |
| Всё read-only | «все сущности в HA», `sensor.cartel_usd_buy` |
| Уточнение | после вопроса о погоде: «а сейчас?» (контекст чата) |

### Управление устройствами (опционально)

По умолчанию бот **только читает** HA. Чтобы включить свет/выключатели/увлажнитель/пылесос:

1. Задайте **`TELEGRAM_ALLOWED_CHAT_IDS`** (команда `/chatid`).
2. В `.env`: **`HA_CONTROL_ENABLED=1`** (при необходимости **`HA_CONTROL_DOMAINS=...`**).
3. Перезапустите контейнер.

Фразы вроде «выключи switch.rozumnii_peremikach_2» или «включи свет на кухне» — модель сначала может вызвать `ha_query`, затем `ha_control`. Перед выполнением в Telegram появятся кнопки **Да** / **Нет**; без «Да» команда в HA не уходит.

Команды: `/chatid` — ваш `chat_id` для `TELEGRAM_ALLOWED_CHAT_IDS`; `/clear`, `/memory`.

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
