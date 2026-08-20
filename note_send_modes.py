NOTE_SEND_MODE_OBSIDIAN = "obsidian_notes"
NOTE_SEND_MODE_MAIL_DRAFTS = "mail_drafts"
NOTE_SEND_MODE_TELEGRAM = "telegram"

_NOTE_SEND_MODE_OPTIONS = [
    ("В заметки", NOTE_SEND_MODE_OBSIDIAN),
    ("В Черновики", NOTE_SEND_MODE_MAIL_DRAFTS),
    ("В Телеграм", NOTE_SEND_MODE_TELEGRAM),
]


def note_send_mode_options() -> list[tuple[str, str]]:
    return list(_NOTE_SEND_MODE_OPTIONS)


def normalize_note_send_mode(value: str | None) -> str:
    mode = str(value or "").strip()
    valid = {option_value for _label, option_value in _NOTE_SEND_MODE_OPTIONS}
    return mode if mode in valid else NOTE_SEND_MODE_OBSIDIAN


def note_send_mode_label(value: str | None) -> str:
    mode = normalize_note_send_mode(value)
    for label, option_value in _NOTE_SEND_MODE_OPTIONS:
        if option_value == mode:
            return label
    return _NOTE_SEND_MODE_OPTIONS[0][0]
