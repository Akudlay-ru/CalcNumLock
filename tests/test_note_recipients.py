import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from note_recipients import (
    DEFAULT_NOTE_RECIPIENTS,
    load_note_recipients,
    normalize_note_recipients,
    selected_recipient_labels,
)


class NoteRecipientsTests(unittest.TestCase):
    def test_default_recipients_match_quick_send_menu(self):
        self.assertEqual(
            [item["label"] for item in DEFAULT_NOTE_RECIPIENTS],
            ["Алексеев А.", "Барма Д.", "Егоров В."],
        )
        self.assertEqual(
            [item["email"] for item in DEFAULT_NOTE_RECIPIENTS],
            ["", "", ""],
        )
        self.assertEqual(
            selected_recipient_labels(DEFAULT_NOTE_RECIPIENTS),
            ["Алексеев А.", "Барма Д."],
        )

    def test_normalize_recipients_accepts_dicts_and_plain_names(self):
        recipients = normalize_note_recipients(
            [
                {"label": "  Иванов И.  ", "email": " ivanov@example.com ", "checked": False},
                "Петров П.",
                {"name": "Сидоров С.", "address": "sidorov@example.com", "selected": True},
                "",
                {"label": ""},
            ]
        )

        self.assertEqual(
            recipients,
            [
                {"label": "Иванов И.", "email": "ivanov@example.com", "checked": False},
                {"label": "Петров П.", "email": "", "checked": False},
                {"label": "Сидоров С.", "email": "sidorov@example.com", "checked": True},
            ],
        )

    def test_load_recipients_from_text_file_with_default_flag_alias_and_email(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "mail_aliases.txt"
            path.write_text(
                "# default|alias|email\n"
                "1|Алексеев А.|alekseev@example.com\n"
                "да|Барма Д.|barma@example.com\n"
                "0|Егоров В.|egorov@example.com\n"
                "пустая строка без разделителей\n",
                encoding="utf-8",
            )

            recipients = load_note_recipients(path)

        self.assertEqual(
            recipients,
            [
                {"label": "Алексеев А.", "email": "alekseev@example.com", "checked": True},
                {"label": "Барма Д.", "email": "barma@example.com", "checked": True},
                {"label": "Егоров В.", "email": "egorov@example.com", "checked": False},
                {"label": "пустая строка без разделителей", "email": "", "checked": False},
            ],
        )


if __name__ == "__main__":
    unittest.main()
