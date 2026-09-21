from __future__ import annotations

import json
from pathlib import Path

from memory import MemoryStore, empty_customer_record, extract_from_message


def test_save_load_clear_per_customer(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    store = MemoryStore(path)
    store.get_customer(1)["user"]["name"] = "Anton"
    store.save()

    store2 = MemoryStore(path)
    assert store2.get_customer(1)["user"]["name"] == "Anton"
    store2.get_customer(2)["user"]["name"] = "Other"
    store2.save()

    store2.clear_customer(1)
    assert "1" not in store2._data or store2.get_customer(1) == empty_customer_record()
    loaded = json.loads(path.read_text())
    assert "2" in loaded


def test_extract_name_and_injection(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "m.json")
    record = store.get_customer(99)
    assert extract_from_message("My name is Anton.", record)
    store.save()
    inj = store.format_injection(99)
    assert "Anton" in inj


def test_corrupt_memory_backup(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    path.write_text("{not json", encoding="utf-8")
    store = MemoryStore(path)
    assert store._data == {}
    backups = list(tmp_path.glob("memory.json.bak.*"))
    assert len(backups) == 1


def test_clear_removes_name(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "m.json")
    record = store.get_customer(5)
    extract_from_message("My name is Anton.", record)
    store.save()
    store.clear_customer(5)
    store2 = MemoryStore(tmp_path / "m.json")
    assert store2.format_injection(5) == ""
