import tempfile
import unittest
from pathlib import Path

from note_storage import write_note_entry


class NoteStorageTests(unittest.TestCase):
    def test_markdown_note_is_written_to_top_of_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("- 2026-07-04 10:00 - old\n", encoding="utf-8")

            write_note_entry(
                path=path,
                text="new",
                notes_format="md",
                separator=" - ",
                newline_before=True,
                timestamp="2026-07-04 11:00",
            )

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "- 2026-07-04 11:00 - new\n\n- 2026-07-04 10:00 - old\n",
            )

    def test_text_note_is_written_to_top_of_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.txt"
            path.write_text("2026-07-04 10:00 - old\n", encoding="utf-8")

            write_note_entry(
                path=path,
                text="new",
                notes_format="txt",
                separator=" - ",
                newline_before=False,
                timestamp="2026-07-04 11:00",
            )

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "2026-07-04 11:00 - new\n2026-07-04 10:00 - old\n",
            )


if __name__ == "__main__":
    unittest.main()
