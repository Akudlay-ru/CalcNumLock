"""Small, testable NumLock state policy."""

from typing import Callable, Optional


def schedule_numlock_restore(
    schedule: Callable[[int, Callable[[], None]], None],
    restore: Callable[[], None],
    *,
    delay_ms: int = 80,
) -> None:
    """Queue restoration after the native hotkey message has returned."""
    schedule(max(0, int(delay_ms)), restore)


def ensure_numlock_on(
    *,
    enabled: bool,
    is_enabled: Callable[[], bool],
    press_and_release: Callable[[], None],
    suspend_hotkey: Optional[Callable[[], bool]] = None,
    resume_hotkey: Optional[Callable[[], None]] = None,
    resume_delay_ms: int = 0,
    schedule_resume: Optional[Callable[[int, Callable[[], None]], None]] = None,
    force_toggle: bool = False,
) -> bool:
    """Turn NumLock on when policy allows it and restore the hotkey safely."""
    if not enabled or (not force_toggle and is_enabled()):
        return False

    hotkey_suspended = False
    try:
        if suspend_hotkey is not None:
            hotkey_suspended = bool(suspend_hotkey())
        press_and_release()
        return True
    finally:
        if hotkey_suspended and resume_hotkey is not None:
            if resume_delay_ms > 0 and schedule_resume is not None:
                schedule_resume(resume_delay_ms, resume_hotkey)
            else:
                resume_hotkey()
