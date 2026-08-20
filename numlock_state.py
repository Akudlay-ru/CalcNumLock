"""Small, testable NumLock state policy."""

from typing import Callable, Optional


def ensure_numlock_on(
    *,
    enabled: bool,
    is_enabled: Callable[[], bool],
    press_and_release: Callable[[], None],
    suspend_hotkey: Optional[Callable[[], bool]] = None,
    resume_hotkey: Optional[Callable[[], None]] = None,
) -> bool:
    """Turn NumLock on when policy allows it and restore the hotkey safely."""
    if not enabled or is_enabled():
        return False

    hotkey_suspended = False
    try:
        if suspend_hotkey is not None:
            hotkey_suspended = bool(suspend_hotkey())
        press_and_release()
        return True
    finally:
        if hotkey_suspended and resume_hotkey is not None:
            resume_hotkey()
