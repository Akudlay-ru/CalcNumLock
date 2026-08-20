import unittest

from note_send_modes import (
    NOTE_SEND_MODE_OBSIDIAN,
    note_send_mode_label,
    note_send_mode_options,
    normalize_note_send_mode,
)


class NoteSendModesTests(unittest.TestCase):
    def test_default_mode_is_obsidian_notes(self):
        self.assertEqual(normalize_note_send_mode(""), NOTE_SEND_MODE_OBSIDIAN)
        self.assertEqual(normalize_note_send_mode("unknown"), NOTE_SEND_MODE_OBSIDIAN)

    def test_mode_options_are_ordered_for_selector(self):
        self.assertEqual(
            note_send_mode_options(),
            [
                ("В заметки", "obsidian_notes"),
                ("В Черновики", "mail_drafts"),
                ("В Телеграм", "telegram"),
            ],
        )

    def test_mode_label_returns_selector_caption(self):
        self.assertEqual(note_send_mode_label("obsidian_notes"), "В заметки")
        self.assertEqual(note_send_mode_label("mail_drafts"), "В Черновики")
        self.assertEqual(note_send_mode_label("telegram"), "В Телеграм")
        self.assertEqual(note_send_mode_label("bad"), "В заметки")


if __name__ == "__main__":
    unittest.main()
