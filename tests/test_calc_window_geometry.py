import unittest

import calc_window_geometry
from calc_window_geometry import (
    CALC_MIN_HEIGHT,
    CALC_MIN_WIDTH,
    QWIDGETSIZE_MAX,
    calc_size_limits,
)


class FakeWindow:
    def __init__(self, minimized: bool):
        self.minimized = minimized
        self.visible = False
        self.events = []

    def isMinimized(self):
        return self.minimized

    def show(self):
        self.visible = True
        self.events.append("show")

    def showNormal(self):
        self.minimized = False
        self.visible = True
        self.events.append("showNormal")


class CalcWindowGeometryTests(unittest.TestCase):
    def test_minimized_calculator_is_restored_to_normal_window(self):
        restore_window = getattr(calc_window_geometry, "restore_window", None)
        self.assertIsNotNone(restore_window, "minimized-window restoration is unavailable")
        window = FakeWindow(minimized=True)

        restore_window(window)

        self.assertTrue(window.visible)
        self.assertFalse(window.minimized)
        self.assertEqual(window.events, ["showNormal"])

    def test_unlocked_calculator_has_minimum_size_and_unbounded_maximum(self):
        self.assertEqual(
            calc_size_limits(False),
            (CALC_MIN_WIDTH, CALC_MIN_HEIGHT, QWIDGETSIZE_MAX, QWIDGETSIZE_MAX),
        )

    def test_locked_calculator_has_fixed_minimum_size(self):
        self.assertEqual(
            calc_size_limits(True),
            (CALC_MIN_WIDTH, CALC_MIN_HEIGHT, CALC_MIN_WIDTH, CALC_MIN_HEIGHT),
        )


if __name__ == "__main__":
    unittest.main()
