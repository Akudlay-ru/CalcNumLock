MODIFIER_ORDER = ("ctrl", "alt", "shift", "windows")

KEY_ALIASES = {
    "control": "ctrl",
    "control key": "ctrl",
    "ctrl": "ctrl",
    "menu": "alt",
    "option": "alt",
    "alt": "alt",
    "shift": "shift",
    "win": "windows",
    "windows": "windows",
    "windows key": "windows",
    "cmd": "windows",
    "numlock": "num lock",
    "num_lock": "num lock",
    "num lock": "num lock",
    "esc": "escape",
    "return": "enter",
}


def normalize_hotkey(value: str) -> str:
    parts = hotkey_parts(value)
    if not parts:
        return ""
    modifiers = [m for m in MODIFIER_ORDER if m in parts]
    keys = sorted(parts.difference(MODIFIER_ORDER))
    return "+".join(modifiers + keys)


def hotkey_parts(value: str) -> frozenset[str]:
    text = str(value or "").strip().lower()
    if not text:
        return frozenset()
    raw_parts = [p.strip() for p in text.replace("＋", "+").split("+")]
    parts = []
    for part in raw_parts:
        if not part:
            continue
        part = " ".join(part.replace("_", " ").split())
        parts.append(KEY_ALIASES.get(part, part))
    return frozenset(parts)


def hotkeys_conflict(left: str, right: str) -> bool:
    left_parts = hotkey_parts(left)
    right_parts = hotkey_parts(right)
    if not left_parts or not right_parts:
        return False
    return left_parts.issubset(right_parts) or right_parts.issubset(left_parts)


def find_hotkey_conflicts(entries):
    normalized = []
    for role, hotkey in entries:
        hk = normalize_hotkey(hotkey)
        if hk:
            normalized.append((str(role), hk))

    conflicts = []
    for i, (left_role, left_hk) in enumerate(normalized):
        for right_role, right_hk in normalized[i + 1:]:
            if hotkeys_conflict(left_hk, right_hk):
                conflicts.append((left_role, left_hk, right_role, right_hk))
    return conflicts


def has_hotkey_conflict(hotkey: str, entries) -> tuple[str, str] | None:
    hk = normalize_hotkey(hotkey)
    if not hk:
        return None
    for role, other_hotkey in entries:
        other = normalize_hotkey(other_hotkey)
        if other and hotkeys_conflict(hk, other):
            return str(role), other
    return None
