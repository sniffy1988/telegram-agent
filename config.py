from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_MEMORY_PATH = ROOT_DIR / "memory.json"
DEFAULT_HA_CONTROL_CATALOG = ROOT_DIR / "deploy" / "ha_control_catalog.json"


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    telegram_allowed_chat_ids: frozenset[int]
    ollama_url: str
    ollama_model: str
    ollama_timeout: float
    max_history_messages: int
    memory_path: Path
    home_assistant_url: str
    home_assistant_token: str
    max_search_results: int
    max_images: int
    ha_all_entities_limit: int
    ha_topic_match_limit: int
    ha_tool_json_max_chars: int
    ha_control_enabled: bool
    ha_control_domains: frozenset[str]
    ha_control_catalog_path: Path


def _parse_chat_ids(raw: str) -> frozenset[int]:
    if not raw.strip():
        return frozenset()
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return frozenset(ids)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _domains_env(name: str, default: frozenset[str]) -> frozenset[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required in .env")

    memory_raw = os.getenv("MEMORY_PATH", str(DEFAULT_MEMORY_PATH)).strip()
    memory_path = Path(memory_raw)
    if not memory_path.is_absolute():
        memory_path = ROOT_DIR / memory_path

    return Settings(
        telegram_bot_token=token,
        telegram_allowed_chat_ids=_parse_chat_ids(
            os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
        ),
        ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").strip()
        or "http://127.0.0.1:11434",
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3.5:4b-mlx").strip()
        or "qwen3.5:4b-mlx",
        ollama_timeout=_float_env("OLLAMA_TIMEOUT", 180.0),
        max_history_messages=_int_env("MAX_HISTORY_MESSAGES", 6),
        memory_path=memory_path,
        home_assistant_url=os.getenv(
            "HOME_ASSISTANT_URL", "http://10.10.30.18:8123"
        ).strip()
        or "http://10.10.30.18:8123",
        home_assistant_token=os.getenv("HOME_ASSISTANT_TOKEN", "").strip(),
        max_search_results=_int_env("MAX_SEARCH_RESULTS", 5),
        max_images=_int_env("MAX_IMAGES", 3),
        ha_all_entities_limit=_int_env("HA_ALL_ENTITIES_LIMIT", 500),
        ha_topic_match_limit=_int_env("HA_TOPIC_MATCH_LIMIT", 25),
        ha_tool_json_max_chars=_int_env("HA_TOOL_JSON_MAX_CHARS", 14000),
        ha_control_enabled=_bool_env("HA_CONTROL_ENABLED", False),
        ha_control_domains=_domains_env(
            "HA_CONTROL_DOMAINS",
            frozenset(
                {"light", "switch", "fan", "humidifier", "vacuum", "input_boolean"}
            ),
        ),
        ha_control_catalog_path=_catalog_path_env(),
    )


def _catalog_path_env() -> Path:
    raw = os.getenv("HA_CONTROL_CATALOG_PATH", "").strip()
    if not raw:
        return DEFAULT_HA_CONTROL_CATALOG
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path
