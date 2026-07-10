from hotkey_registry import hotkey_parts

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

MODIFIER_FLAGS = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "windows": MOD_WIN,
}

KEY_CODES = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "escape": 0x1B,
    "space": 0x20,
    "page up": 0x21,
    "page down": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "num lock": 0x90,
    "scroll lock": 0x91,
}

for i in range(10):
    KEY_CODES[str(i)] = 0x30 + i

for i, ch in enumerate("abcdefghijklmnopqrstuvwxyz", start=0x41):
    KEY_CODES[ch] = i

for i in range(1, 25):
    KEY_CODES[f"f{i}"] = 0x70 + i - 1


def parse_native_hotkey(hotkey: str) -> tuple[int, int] | None:
    parts = hotkey_parts(hotkey)
    if not parts:
        return None

    modifiers = 0
    keys = []
    for part in parts:
        if part in MODIFIER_FLAGS:
            modifiers |= MODIFIER_FLAGS[part]
        else:
            keys.append(part)

    if len(keys) != 1:
        return None

    vk = KEY_CODES.get(keys[0])
    if vk is None:
        return None

    return modifiers | MOD_NOREPEAT, vk


def should_use_native_hotkey(hotkey: str) -> bool:
    parts = hotkey_parts(hotkey)
    if not parts:
        return False
    return parse_native_hotkey(hotkey) is not None
