from __future__ import annotations

import re

# Longer phrases first (turn on before turn).
_CONTROL_VERBS: tuple[tuple[str, str], ...] = (
    ("turn on", "turn_on"),
    ("turn off", "turn_off"),
    ("return to base", "return_to_base"),
    ("включи", "turn_on"),
    ("увімкни", "turn_on"),
    ("выключи", "turn_off"),
    ("вимкни", "turn_off"),
    ("переключи", "toggle"),
    ("toggle", "toggle"),
    ("запусти", "start"),
    ("start", "start"),
    ("останови", "stop"),
    ("stop", "stop"),
    ("pause", "pause"),
)

_VERB_PATTERN = "|".join(re.escape(v) for v, _ in _CONTROL_VERBS)
_CONTROL_INTENT_RE = re.compile(
    rf"^\s*(?P<verb>{_VERB_PATTERN})\s+(?P<target>.+?)\s*$",
    re.I,
)


def parse_ha_control_intent(text: str) -> tuple[str, str] | None:
    """Return (ha_action, target_name_or_entity_id) or None."""
    t = text.strip()
    if not t or len(t) > 120:
        return None
    m = _CONTROL_INTENT_RE.match(t)
    if not m:
        return None
    verb_raw = m.group("verb").lower()
    target = m.group("target").strip().strip("?.!")
    if not target:
        return None
    for phrase, action in _CONTROL_VERBS:
        if verb_raw == phrase.lower():
            return action, target
    return None
