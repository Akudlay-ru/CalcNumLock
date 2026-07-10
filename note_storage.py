from pathlib import Path

NOTE_FMT_MD = "md"
NOTE_FMT_TXT = "txt"
NOTE_FMT_RTF = "rtf"


def rtf_escape(text: str) -> str:
    out = []
    for ch in text:
        if ch in ("\\", "{", "}"):
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\line ")
        elif ord(ch) < 128:
            out.append(ch)
        else:
            code = ord(ch)
            if code > 32767:
                code -= 65536
            out.append(f"\\u{code}?")
    return "".join(out)


def write_note_entry(
    *,
    path: Path,
    text: str,
    notes_format: str,
    separator: str,
    newline_before: bool,
    timestamp: str,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    line_content = f"{timestamp}{separator}{text}"
    existing = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    between = "\n" if newline_before and existing else ""

    if notes_format == NOTE_FMT_MD:
        path.write_text(f"- {line_content}\n{between}{existing}", encoding="utf-8")
        return

    if notes_format == NOTE_FMT_TXT:
        path.write_text(f"{line_content}\n{between}{existing}", encoding="utf-8")
        return

    if notes_format == NOTE_FMT_RTF:
        entry = rtf_escape(line_content) + "\\line\n"
        if existing:
            idx = existing.find("\\f0\\fs22\n")
            if idx >= 0:
                insert_at = idx + len("\\f0\\fs22\n")
                prefix = existing[:insert_at]
                suffix = existing[insert_at:]
                path.write_text(prefix + entry + ("\\line\n" if newline_before and suffix.strip("}") else "") + suffix, encoding="utf-8")
                return
            idx = existing.rfind("}")
            if idx > 0:
                path.write_text(existing[:idx] + entry + existing[idx:], encoding="utf-8")
                return
            path.write_text(entry + existing, encoding="utf-8")
            return

        header = (
            "{\\rtf1\\ansi\\ansicpg1251\\deff0"
            "{\\fonttbl{\\f0\\fnil\\fcharset204 Segoe UI;}}"
            "\\f0\\fs22\n"
        )
        path.write_text(header + entry + "}", encoding="utf-8")
        return

    raise ValueError(f"Unsupported notes format: {notes_format!r}")
