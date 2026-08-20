CALC_MIN_WIDTH = 320
CALC_MIN_HEIGHT = 500
QWIDGETSIZE_MAX = 16777215


def restore_window(window) -> None:
    if window.isMinimized():
        window.showNormal()
    else:
        window.show()


def calc_size_limits(locked: bool) -> tuple[int, int, int, int]:
    if locked:
        return CALC_MIN_WIDTH, CALC_MIN_HEIGHT, CALC_MIN_WIDTH, CALC_MIN_HEIGHT
    return CALC_MIN_WIDTH, CALC_MIN_HEIGHT, QWIDGETSIZE_MAX, QWIDGETSIZE_MAX
