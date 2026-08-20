import unittest

from launcher_window_state import ACTION_ACTIVATE, ACTION_MINIMIZE, ACTION_START, choose_launcher_action


class LauncherWindowStateTests(unittest.TestCase):
    def test_missing_window_starts_launcher(self):
        self.assertEqual(choose_launcher_action(0, False, False, False), ACTION_START)

    def test_visible_window_minimizes_launcher(self):
        self.assertEqual(choose_launcher_action(123, True, False, False), ACTION_MINIMIZE)

    def test_minimized_window_activates_launcher(self):
        self.assertEqual(choose_launcher_action(123, True, True, False), ACTION_ACTIVATE)

    def test_hidden_or_cloaked_window_activates_launcher(self):
        self.assertEqual(choose_launcher_action(123, False, False, False), ACTION_ACTIVATE)
        self.assertEqual(choose_launcher_action(123, True, False, True), ACTION_ACTIVATE)


if __name__ == "__main__":
    unittest.main()
