ACTION_START = "start"
ACTION_ACTIVATE = "activate"
ACTION_MINIMIZE = "minimize"


def choose_launcher_action(hwnd: int, visible: bool, iconic: bool, cloaked: bool) -> str:
    if not hwnd:
        return ACTION_START
    if iconic or cloaked or not visible:
        return ACTION_ACTIVATE
    return ACTION_MINIMIZE
