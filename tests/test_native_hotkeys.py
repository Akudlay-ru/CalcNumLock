import unittest

from native_hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    parse_native_hotkey,
    should_use_native_hotkey,
)


class NativeHotkeyTests(unittest.TestCase):
    def test_parse_num_lock(self):
        self.assertEqual(parse_native_hotkey("num lock"), (MOD_NOREPEAT, 0x90))

    def test_parse_shift_num_lock(self):
        self.assertEqual(parse_native_hotkey("shift+num lock"), (MOD_SHIFT | MOD_NOREPEAT, 0x90))

    def test_parse_ctrl_alt_letter(self):
        self.assertEqual(parse_native_hotkey("control + alt + o"), (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x4F))

    def test_parse_function_key(self):
        self.assertEqual(parse_native_hotkey("ctrl+f12"), (MOD_CONTROL | MOD_NOREPEAT, 0x7B))

    def test_unknown_key_returns_none(self):
        self.assertIsNone(parse_native_hotkey("ctrl+непонятно"))

    def test_bare_num_lock_uses_native_hotkey(self):
        self.assertTrue(should_use_native_hotkey("num lock"))
        self.assertTrue(should_use_native_hotkey("shift+num lock"))


if __name__ == "__main__":
    unittest.main()
