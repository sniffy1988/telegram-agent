from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CATALOG_PATH = ROOT_DIR / "deploy" / "ha_control_catalog.json"

# Never offer these via fuzzy HA search (routers, AdGuard, cameras, Delta Pro, service buttons).
_CONTROL_BLOCKLIST = re.compile(
    r"(adguard|ether\d|sfp\d|deltapro|chuangmi_ipc|cap_ax|hexs|l009uigs|"
    r"_backup|_restart|_shutdown|indicator_light|physical_control_locked|"
    r"do_not_disturb|dock_child|dock_status|time_watermark|motion_tracking|"
    r"wide_dynamic|glimmer_full|query_log|parental_control|safe_browsing|"
    r"safe_search|filtering|protection|alarm|beeper|ac_always|ac_enabled|"
    r"backup_reserve|dc_12v|x_boost|switch_status|camera control)",
    re.I,
)


def _normalize_alias_key(text: str) -> str:
    return " ".join(text.strip().lower().split())


@lru_cache(maxsize=4)
def _load_catalog(path_str: str) -> dict[str, Any]:
    path = Path(path_str)
    if not path.is_file():
        logger.warning("[ha_control] catalog missing: %s", path)
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[ha_control] catalog load failed: %s", exc)
        return {}


def catalog_allowlist(catalog_path: Path | None = None) -> frozenset[str]:
    path = catalog_path or DEFAULT_CATALOG_PATH
    raw = _load_catalog(str(path.resolve())).get("allowlist")
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(str(x).strip() for x in raw if str(x).strip())


def catalog_labels(catalog_path: Path | None = None) -> dict[str, str]:
    path = catalog_path or DEFAULT_CATALOG_PATH
    raw = _load_catalog(str(path.resolve())).get("labels")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def resolve_alias_targets(target: str, catalog_path: Path | None = None) -> list[str]:
    """Exact alias → entity_id(s). Empty if no alias hit."""
    path = catalog_path or DEFAULT_CATALOG_PATH
    aliases = _load_catalog(str(path.resolve())).get("aliases")
    if not isinstance(aliases, dict):
        return []
    key = _normalize_alias_key(target)
    val = aliases.get(key)
    if val is None:
        return []
    if isinstance(val, str):
        return [val.strip()] if val.strip() else []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    return []


def is_blocklisted_control_entity(entity_id: str, friendly_name: str = "") -> bool:
    blob = f"{entity_id} {friendly_name}"
    return bool(_CONTROL_BLOCKLIST.search(blob))


def filter_control_candidates(
    states: list[dict[str, Any]],
    *,
    allowed_domains: frozenset[str],
    catalog_path: Path | None = None,
    allowlist_override: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    allowlist = allowlist_override if allowlist_override is not None else catalog_allowlist(catalog_path)
    out: list[dict[str, Any]] = []
    for st in states:
        if not isinstance(st, dict):
            continue
        eid = str(st.get("entity_id") or "").strip()
        if not eid or entity_domain_simple(eid) not in allowed_domains:
            continue
        fname = str(st.get("friendly_name") or "")
        if is_blocklisted_control_entity(eid, fname):
            continue
        if allowlist and eid not in allowlist:
            continue
        out.append(st)
    return out


def entity_domain_simple(entity_id: str) -> str:
    if "." not in entity_id:
        return ""
    return entity_id.split(".", 1)[0]


def format_devices_help(catalog_path: Path | None = None) -> str:
    path = catalog_path or DEFAULT_CATALOG_PATH
    labels = catalog_labels(path)
    allow = sorted(catalog_allowlist(path))
    if not allow:
        return "Каталог устройств пуст. Задайте deploy/ha_control_catalog.json"
    lines = ["Управление (примеры фраз → entity):", ""]
    data = _load_catalog(str(path.resolve()))
    aliases = data.get("aliases") if isinstance(data.get("aliases"), dict) else {}
    shown: set[str] = set()
    for phrase, eid in sorted(aliases.items(), key=lambda x: x[0]):
        if isinstance(eid, list):
            continue
        eid_s = str(eid)
        if eid_s in shown:
            continue
        shown.add(eid_s)
        label = labels.get(eid_s, eid_s)
        lines.append(f"• «{phrase}» — {label}")
    lines.extend(["", "Или: включи switch.rozumnii_peremikach_2"])
    return "\n".join(lines)
