import unittest
from pathlib import Path

import numlock_state
from numlock_state import ensure_numlock_on


class FakeNumLock:
    def __init__(self, enabled=False, fail=False):
        self.enabled = enabled
        self.fail = fail
        self.events = []

    def is_enabled(self):
        self.events.append("read")
        return self.enabled

    def suspend_hotkey(self):
        self.events.append("suspend")
        return True

    def press_and_release(self):
        self.events.append("press")
        if self.fail:
            raise RuntimeError("input failed")
        self.enabled = True

    def resume_hotkey(self):
        self.events.append("resume")


class NumLockStateTests(unittest.TestCase):
    def test_restore_is_queued_until_after_native_hotkey_dispatch(self):
        scheduled = []
        restored = []

        try:
            numlock_state.schedule_numlock_restore(
                lambda delay, callback: scheduled.append((delay, callback)),
                lambda: restored.append(True),
                delay_ms=80,
            )
        except AttributeError as exc:
            self.fail(f"post-hotkey restore scheduling is unavailable: {exc}")

        self.assertEqual(restored, [])
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0], 80)

        scheduled[0][1]()
        self.assertEqual(restored, [True])

    def test_hotkey_resume_can_wait_until_injected_key_is_dispatched(self):
        lock = FakeNumLock(enabled=False)
        scheduled = []

        try:
            changed = ensure_numlock_on(
                enabled=True,
                is_enabled=lock.is_enabled,
                press_and_release=lock.press_and_release,
                suspend_hotkey=lock.suspend_hotkey,
                resume_hotkey=lock.resume_hotkey,
                resume_delay_ms=150,
                schedule_resume=lambda delay, callback: scheduled.append((delay, callback)),
            )
        except TypeError as exc:
            self.fail(f"deferred hotkey resume is unsupported: {exc}")

        self.assertTrue(changed)
        self.assertEqual(lock.events, ["read", "suspend", "press"])
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0], 150)

        scheduled[0][1]()
        self.assertEqual(lock.events, ["read", "suspend", "press", "resume"])

    def test_tray_watchdog_restores_numlock_every_poll(self):
        source = (Path(__file__).resolve().parents[1] / "calc_numlock_tray.pyw").read_text(encoding="utf-8")
        watchdog = source.split("def _poll_keyboard_recovery_watchdog", 1)[1].split("\n    def ", 1)[0]

        self.assertIn("NUMLOCK_STATE_WATCH_POLL_MS = 100", source)
        self.assertIn("self._restore_numlock()", watchdog)

    def test_disabled_policy_does_not_touch_numlock(self):
        lock = FakeNumLock(enabled=False)

        changed = ensure_numlock_on(
            enabled=False,
            is_enabled=lock.is_enabled,
            press_and_release=lock.press_and_release,
            suspend_hotkey=lock.suspend_hotkey,
            resume_hotkey=lock.resume_hotkey,
        )

        self.assertFalse(changed)
        self.assertEqual(lock.events, [])

    def test_enabled_numlock_is_left_unchanged(self):
        lock = FakeNumLock(enabled=True)

        changed = ensure_numlock_on(
            enabled=True,
            is_enabled=lock.is_enabled,
            press_and_release=lock.press_and_release,
            suspend_hotkey=lock.suspend_hotkey,
            resume_hotkey=lock.resume_hotkey,
        )

        self.assertFalse(changed)
        self.assertEqual(lock.events, ["read"])

    def test_numlock_hotkey_can_force_restore_when_gui_state_is_stale(self):
        lock = FakeNumLock(enabled=True)

        changed = ensure_numlock_on(
            enabled=True,
            is_enabled=lock.is_enabled,
            press_and_release=lock.press_and_release,
            suspend_hotkey=lock.suspend_hotkey,
            resume_hotkey=lock.resume_hotkey,
            force_toggle=True,
        )

        self.assertTrue(changed)
        self.assertEqual(lock.events, ["suspend", "press", "resume"])

    def test_disabled_numlock_is_restored_around_hotkey_registration(self):
        lock = FakeNumLock(enabled=False)

        changed = ensure_numlock_on(
            enabled=True,
            is_enabled=lock.is_enabled,
            press_and_release=lock.press_and_release,
            suspend_hotkey=lock.suspend_hotkey,
            resume_hotkey=lock.resume_hotkey,
        )

        self.assertTrue(changed)
        self.assertTrue(lock.enabled)
        self.assertEqual(lock.events, ["read", "suspend", "press", "resume"])

    def test_hotkey_is_restored_when_input_injection_fails(self):
        lock = FakeNumLock(enabled=False, fail=True)

        with self.assertRaisesRegex(RuntimeError, "input failed"):
            ensure_numlock_on(
                enabled=True,
                is_enabled=lock.is_enabled,
                press_and_release=lock.press_and_release,
                suspend_hotkey=lock.suspend_hotkey,
                resume_hotkey=lock.resume_hotkey,
            )

        self.assertEqual(lock.events, ["read", "suspend", "press", "resume"])


if __name__ == "__main__":
    unittest.main()
