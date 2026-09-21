from __future__ import annotations

import json
from pathlib import Path

from ha_control_catalog import (
    filter_control_candidates,
    resolve_alias_targets,
)


def test_resolve_nochik_alias(tmp_path: Path) -> None:
    cat = tmp_path / "c.json"
    cat.write_text(
        json.dumps({"aliases": {"ночник": "switch.rozumnii_peremikach_2"}}),
        encoding="utf-8",
    )
    assert resolve_alias_targets("ночник", cat) == ["switch.rozumnii_peremikach_2"]


def test_filter_blocks_adguard() -> None:
    states = [
        {
            "entity_id": "switch.adguard_home_filtering",
            "friendly_name": "AdGuard Home Filtering",
        },
        {
            "entity_id": "switch.rozumnii_peremikach_2",
            "friendly_name": "Розумний перемикач 2",
        },
    ]
    out = filter_control_candidates(
        states,
        allowed_domains=frozenset({"switch"}),
        catalog_path=Path("/nonexistent"),
    )
    assert len(out) == 1
    assert out[0]["entity_id"] == "switch.rozumnii_peremikach_2"


def test_allowlist_restricts() -> None:
    states = [
        {"entity_id": "switch.a", "friendly_name": "A"},
        {"entity_id": "switch.b", "friendly_name": "B"},
    ]
    cat = Path(__file__).resolve().parent.parent / "deploy" / "ha_control_catalog.json"
    out = filter_control_candidates(
        states,
        allowed_domains=frozenset({"switch"}),
        catalog_path=cat,
        allowlist_override=frozenset({"switch.a"}),
    )
    assert [s["entity_id"] for s in out] == ["switch.a"]
