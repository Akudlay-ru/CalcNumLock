from pathlib import Path


MAIL_ALIASES_FILE_NAME = "mail_aliases.txt"

DEFAULT_NOTE_RECIPIENTS = [
    {"label": "Алексеев А.", "email": "", "checked": True},
    {"label": "Барма Д.", "email": "", "checked": True},
    {"label": "Егоров В.", "email": "", "checked": False},
]


def normalize_note_recipients(raw_recipients) -> list[dict[str, object]]:
    recipients: list[dict[str, object]] = []
    for item in raw_recipients or []:
        checked = False
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("name") or "").strip()
            email = str(item.get("email") or item.get("address") or "").strip()
            checked = bool(item.get("checked", item.get("selected", False)))
        else:
            label = str(item or "").strip()
            email = ""
        if not label:
            continue
        recipients.append({"label": label, "email": email, "checked": checked})
    return recipients


def selected_recipient_labels(recipients) -> list[str]:
    return [
        str(item.get("label") or "").strip()
        for item in normalize_note_recipients(recipients)
        if item.get("checked") and str(item.get("label") or "").strip()
    ]


def _is_default_enabled(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "yes", "y", "true", "on", "v", "да", "д", "+"}


def _parse_recipient_line(line: str) -> dict[str, object] | None:
    raw = str(line or "").strip()
    if not raw or raw.startswith("#"):
        return None
    parts = [part.strip() for part in raw.split("|")]
    if len(parts) >= 3:
        return {
            "label": parts[1],
            "email": parts[2],
            "checked": _is_default_enabled(parts[0]),
        }
    if len(parts) == 2:
        return {"label": parts[0], "email": parts[1], "checked": False}
    return {"label": raw, "email": "", "checked": False}


def load_note_recipients(path: Path | str) -> list[dict[str, object]]:
    file_path = Path(path)
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return normalize_note_recipients(DEFAULT_NOTE_RECIPIENTS)
    except Exception:
        return normalize_note_recipients(DEFAULT_NOTE_RECIPIENTS)

    recipients = []
    for line in lines:
        parsed = _parse_recipient_line(line)
        if parsed is not None:
            recipients.append(parsed)
    return normalize_note_recipients(recipients) or normalize_note_recipients(DEFAULT_NOTE_RECIPIENTS)
