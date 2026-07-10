MENU_ACTION_ROW_MARGINS = (2, 2, 2, 2)
MENU_ACTION_ROW_SPACING = 2
MENU_ACTION_CHECKBOX_WIDTH = 18
MENU_ACTION_ICON_SIZE = 18
MENU_CONTROL_ROW_MARGINS = (2, 2, 2, 2)
MENU_CONTROL_ROW_SPACING = 6
MENU_NOTE_INPUT_WIDTH = 105
MENU_AUTOCOPY_LABEL_WIDTH = 52
MENU_AUTOCOPY_BUTTON_WIDTH = 68
MENU_AFFIX_FIELD_WIDTH = 70
MENU_SQUARE_BUTTON_SIZE = 32
MENU_NOTE_BUTTON_WIDTH = MENU_SQUARE_BUTTON_SIZE
MENU_RESET_BUTTON_WIDTH = MENU_SQUARE_BUTTON_SIZE
MENU_QUICK_MODE_WIDTH = MENU_AUTOCOPY_BUTTON_WIDTH
MENU_QUICK_FIELD_WIDTH = (MENU_AFFIX_FIELD_WIDTH * 2) + MENU_CONTROL_ROW_SPACING
MENU_QUICK_BLOCK_WIDTH = (
    MENU_QUICK_FIELD_WIDTH
    + MENU_QUICK_MODE_WIDTH
    + MENU_NOTE_BUTTON_WIDTH
    + (MENU_CONTROL_ROW_SPACING * 2)
    + MENU_CONTROL_ROW_MARGINS[0]
    + MENU_CONTROL_ROW_MARGINS[2]
)
MENU_QUICK_BLOCK_HEIGHT = (
    (MENU_SQUARE_BUTTON_SIZE * 2)
    + MENU_CONTROL_ROW_SPACING
    + MENU_CONTROL_ROW_MARGINS[1]
    + MENU_CONTROL_ROW_MARGINS[3]
)


HOTKEY_NAME_MAP = {
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "win": "Win",
    "windows": "Win",
    "num lock": "NumLock",
    "numlock": "NumLock",
}


AUTO_COPY_MODE_DETAILS = {
    "off": (
        "○",
        "Отключить",
        "Автокопирование выключено.",
        "автокопирование выключено",
    ),
    "result": (
        "⧉",
        "Копировать результат",
        "После Enter или = результат калькулятора попадёт в буфер обмена.",
        "результат в буфер",
    ),
    "text": (
        "Tx",
        "Число → текст",
        "После Enter или = число будет скопировано текстом.",
        "число текстом",
    ),
    "money_text": (
        "₽т",
        "Сумма ₽ текстом",
        "После Enter или = сумма будет скопирована прописью с рублями и копейками.",
        "сумма ₽ текстом",
    ),
}


def auto_copy_mode_details(mode: str) -> tuple[str, str, str, str]:
    clean_mode = str(mode or "").strip().lower()
    return AUTO_COPY_MODE_DETAILS.get(clean_mode, AUTO_COPY_MODE_DETAILS["result"])


def format_hotkey_caption(hotkey: str) -> str:
    parts = [part.strip().lower() for part in str(hotkey or "").split("+") if part.strip()]
    if not parts:
        return ""
    return "+".join(HOTKEY_NAME_MAP.get(part, part.upper() if len(part) == 1 else part.title()) for part in parts)


def format_action_caption(title: str, hotkey: str) -> str:
    clean_title = str(title or "").strip()
    clean_hotkey = format_hotkey_caption(hotkey)
    if clean_title and clean_hotkey:
        return f"{clean_title} | {clean_hotkey}"
    return clean_title or clean_hotkey


def format_auto_copy_caption(mode: str) -> str:
    clean_mode = str(mode or "").strip().lower()
    if clean_mode == "off":
        return "=→○"
    if clean_mode == "text":
        return "=→Tx"
    if clean_mode == "money_text":
        return "=→₽т"
    return "=→⧉"


def format_auto_copy_menu_label(mode: str) -> str:
    icon, label, _description, _symbol_meaning = auto_copy_mode_details(mode)
    return f"{icon}  {label}"


def auto_copy_mode_tooltip(mode: str) -> str:
    icon, label, description, symbol_meaning = auto_copy_mode_details(mode)
    return "\n".join(
        (
            f"{format_auto_copy_caption(mode)} — {label}",
            "= — после Enter или =",
            "→ — отправить в буфер обмена",
            f"{icon} — {symbol_meaning}",
            description,
        )
    )



def menu_action_row_prefix_width() -> int:
    left, _top, _right, _bottom = MENU_ACTION_ROW_MARGINS
    return left + MENU_ACTION_CHECKBOX_WIDTH + MENU_ACTION_ROW_SPACING + MENU_ACTION_ICON_SIZE + MENU_ACTION_ROW_SPACING
