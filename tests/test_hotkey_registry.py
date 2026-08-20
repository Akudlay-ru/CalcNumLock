import unittest

from hotkey_registry import (
    find_hotkey_conflicts,
    hotkeys_conflict,
    normalize_hotkey,
)


class HotkeyRegistryTests(unittest.TestCase):
    def test_normalize_hotkey_sorts_modifiers_and_aliases_numlock(self):
        self.assertEqual(normalize_hotkey(" NumLock + Shift "), "shift+num lock")
        self.assertEqual(normalize_hotkey("control + ALT + N"), "ctrl+alt+n")

    def test_subset_hotkeys_conflict(self):
        self.assertTrue(hotkeys_conflict("num lock", "shift+num lock"))
        self.assertTrue(hotkeys_conflict("shift+num lock", "num lock"))

    def test_same_modifier_different_key_does_not_conflict(self):
        self.assertFalse(hotkeys_conflict("ctrl+alt+n", "ctrl+alt+m"))

    def test_find_conflicts_reports_roles(self):
        conflicts = find_hotkey_conflicts([
            ("calc toggle", "shift+num lock"),
            ("calc pause", "num lock"),
            ("note popup", "ctrl+alt+n"),
            ("launcher: notes", "Ctrl + Alt + N"),
        ])

        self.assertIn(("calc toggle", "shift+num lock", "calc pause", "num lock"), conflicts)
        self.assertIn(("note popup", "ctrl+alt+n", "launcher: notes", "ctrl+alt+n"), conflicts)


if __name__ == "__main__":
    unittest.main()
