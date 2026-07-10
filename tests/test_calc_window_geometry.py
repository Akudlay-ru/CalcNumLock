import unittest

from calc_window_geometry import (
    CALC_MIN_HEIGHT,
    CALC_MIN_WIDTH,
    QWIDGETSIZE_MAX,
    calc_size_limits,
)


class CalcWindowGeometryTests(unittest.TestCase):
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
