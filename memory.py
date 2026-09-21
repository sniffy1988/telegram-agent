from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SECRET_PATTERNS = re.compile(
    r"(password|passwd|api[_-]?key|secret|token|private[_-]?key|"
    r"ssh|wireguard|bearer\s+[a-z0-9._-]+)",
    re.IGNORECASE,
)

VLAN_PATTERN = re.compile(
    r"vlan\s*(\d+)\s*(?:is|=|:|-)\s*(.+?)(?:\.|$)",
    re.IGNORECASE,
)
IP_PATTERN = re.compile(
    r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"
)


def empty_customer_record() -> dict[str, Any]:
    return {
        "user": {},
        "preferences": {},
        "household": {},
        "devices": {},
        "notes": [],
    }


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._data = {}
            return
        try:
            raw = self.path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("root must be object")
            self._data = {
                str(k): self._normalize_record(v)
                for k, v in parsed.items()
                if isinstance(v, dict)
            }
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.error("Corrupt memory file %s: %s", self.path, exc)
            self._backup_corrupt()
            self._data = {}

    def _backup_corrupt(self) -> None:
        if not self.path.exists():
            return
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = self.path.with_name(f"{self.path.name}.bak.{ts}")
        try:
            shutil.copy2(self.path, backup)
            logger.info("Backed up corrupt memory to %s", backup.name)
        except OSError as exc:
            logger.warning("Could not backup memory file: %s", exc)

    def _normalize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        base = empty_customer_record()
        for key in base:
            if key in record and isinstance(record[key], (dict, list)):
                base[key] = record[key]
        if not isinstance(base["notes"], list):
            base["notes"] = []
        return base

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def get_customer(self, chat_id: int) -> dict[str, Any]:
        key = str(chat_id)
        if key not in self._data:
            self._data[key] = empty_customer_record()
        return self._data[key]

    def clear_customer(self, chat_id: int) -> None:
        key = str(chat_id)
        if key in self._data:
            del self._data[key]
            self.save()

    def format_summary(self, chat_id: int) -> str:
        record = self.get_customer(chat_id)
        lines: list[str] = []
        user = record.get("user") or {}
        if user.get("name"):
            lines.append(f"Name: {user['name']}")
        if user.get("country"):
            lines.append(f"Country: {user['country']}")
        household = record.get("household") or {}
        if household.get("home_assistant"):
            lines.append(f"Home Assistant: {household['home_assistant']}")
        vlans = household.get("vlans") or {}
        if isinstance(vlans, dict):
            for vid, label in sorted(vlans.items(), key=lambda x: str(x[0])):
                lines.append(f"VLAN {vid}: {label}")
        prefs = record.get("preferences") or {}
        for pk, pv in prefs.items():
            lines.append(f"Preference {pk}: {pv}")
        notes = record.get("notes") or []
        if isinstance(notes, list):
            for note in notes[:10]:
                if isinstance(note, str) and note.strip():
                    lines.append(f"Note: {note.strip()}")
        if not lines:
            return "Nothing stored in long-term memory."
        return "Stored memory:\n" + "\n".join(f"- {line}" for line in lines)

    def format_injection(self, chat_id: int) -> str:
        record = self.get_customer(chat_id)
        lines: list[str] = []
        user = record.get("user") or {}
        if user.get("name"):
            lines.append(f"Name: {user['name']}")
        if user.get("country"):
            lines.append(f"Country: {user['country']}")
        household = record.get("household") or {}
        if household.get("home_assistant"):
            lines.append(f"Home Assistant: {household['home_assistant']}")
        vlans = household.get("vlans") or {}
        if isinstance(vlans, dict):
            for vid, label in sorted(vlans.items(), key=lambda x: str(x[0])):
                lines.append(f"VLAN {vid}: {label}")
        notes = record.get("notes") or []
        if isinstance(notes, list):
            for note in notes[:5]:
                if isinstance(note, str) and note.strip():
                    lines.append(note.strip()[:200])
        if not lines:
            return ""
        return "Known user information:\n" + "\n".join(f"- {line}" for line in lines)


def _looks_like_secret(text: str) -> bool:
    return bool(SECRET_PATTERNS.search(text))


def extract_from_message(text: str, record: dict[str, Any]) -> bool:
    """Deterministic extraction. Returns True if record was modified."""
    if not text.strip() or _looks_like_secret(text):
        return False
    lower = text.lower().strip()
    changed = False
    user = record.setdefault("user", {})
    household = record.setdefault("household", {})
    if "vlans" not in household or not isinstance(household["vlans"], dict):
        household["vlans"] = {}

    name_patterns = [
        r"my name is\s+(.+?)(?:\.|$)",
        r"мене звати\s+(.+?)(?:\.|$)",
        r"моє ім['\u2019]я\s+(.+?)(?:\.|$)",
    ]
    for pat in name_patterns:
        m = re.search(pat, lower, re.IGNORECASE)
        if m:
            name = text[m.start(1) : m.end(1)].strip().strip('"')
            if name and len(name) < 80:
                user["name"] = name
                changed = True
            break

    country_patterns = [
        r"i(?:'m| am) from\s+(.+?)(?:\.|$)",
        r"i live in\s+(.+?)(?:\.|$)",
        r"я з\s+(.+?)(?:\.|$)",
    ]
    for pat in country_patterns:
        m = re.search(pat, lower, re.IGNORECASE)
        if m:
            country = text[m.start(1) : m.end(1)].strip()
            if country and len(country) < 80:
                user["country"] = country
                changed = True
            break

    ha_patterns = [
        r"my home assistant is(?: at)?\s+(.+?)(?:\.|$)",
        r"home assistant is at\s+(.+?)(?:\.|$)",
    ]
    for pat in ha_patterns:
        m = re.search(pat, lower, re.IGNORECASE)
        if m:
            val = text[m.start(1) : m.end(1)].strip()
            if val and not _looks_like_secret(val):
                household["home_assistant"] = val[:200]
                changed = True
            break

    remember_markers = (
        "remember that",
        "save this",
        "keep this in mind",
        "запам'ятай",
        "запамятай",
        "збережи",
    )
    if any(m in lower for m in remember_markers):
        for ip in IP_PATTERN.findall(text):
            if "home assistant" in lower or "ha " in lower:
                household["home_assistant"] = ip
                changed = True
        for vm in VLAN_PATTERN.finditer(text):
            household["vlans"][vm.group(1)] = vm.group(2).strip()[:120]
            changed = True
        if not VLAN_PATTERN.search(text) and not IP_PATTERN.search(text):
            note = text.strip()[:300]
            if note and not _looks_like_secret(note):
                notes = record.setdefault("notes", [])
                if isinstance(notes, list) and note not in notes:
                    notes.append(note)
                    if len(notes) > 20:
                        del notes[:-20]
                    changed = True

    for vm in VLAN_PATTERN.finditer(text):
        if "vlan" in lower or "network" in lower or "мереж" in lower:
            household["vlans"][vm.group(1)] = vm.group(2).strip()[:120]
            changed = True

    if "my network is" in lower:
        for vm in VLAN_PATTERN.finditer(text):
            household["vlans"][vm.group(1)] = vm.group(2).strip()[:120]
            changed = True

    return changed
