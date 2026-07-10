import unittest

import menu_action_row
from menu_action_row import (
    MENU_ACTION_CHECKBOX_WIDTH,
    MENU_ACTION_ICON_SIZE,
    MENU_ACTION_ROW_MARGINS,
    MENU_ACTION_ROW_SPACING,
    MENU_CONTROL_ROW_MARGINS,
    MENU_CONTROL_ROW_SPACING,
    MENU_AFFIX_FIELD_WIDTH,
    MENU_AUTOCOPY_LABEL_WIDTH,
    MENU_NOTE_BUTTON_WIDTH,
    MENU_NOTE_INPUT_WIDTH,
    MENU_QUICK_BLOCK_HEIGHT,
    MENU_QUICK_BLOCK_WIDTH,
    MENU_QUICK_FIELD_WIDTH,
    MENU_QUICK_MODE_WIDTH,
    MENU_RESET_BUTTON_WIDTH,
    MENU_SQUARE_BUTTON_SIZE,
    format_auto_copy_caption,
    format_action_caption,
    format_hotkey_caption,
    menu_action_row_prefix_width,
)


class MenuActionRowTests(unittest.TestCase):
    def test_formats_action_caption_with_hotkey_separator(self):
        self.assertEqual(format_action_caption("Obsidian", "ctrl+alt+o"), "Obsidian | Ctrl+Alt+O")

    def test_formats_numlock_hotkey_for_display(self):
        self.assertEqual(format_action_caption("Калькулятор", "num lock"), "Калькулятор | NumLock")

    def test_action_caption_without_hotkey_uses_title_only(self):
        self.assertEqual(format_action_caption("Telegram", ""), "Telegram")


    def test_menu_layout_constants_keep_rows_compact_and_aligned(self):
        self.assertLessEqual(menu_action_row_prefix_width(), 42)
        self.assertEqual(MENU_ACTION_CHECKBOX_WIDTH, 18)
        self.assertEqual(MENU_ACTION_ICON_SIZE, 18)
        self.assertEqual(MENU_ACTION_ROW_SPACING, 2)
        self.assertLess(MENU_AUTOCOPY_LABEL_WIDTH, MENU_NOTE_INPUT_WIDTH)
        self.assertEqual(MENU_AUTOCOPY_LABEL_WIDTH, 52)
        self.assertTrue(hasattr(menu_action_row, "MENU_AUTOCOPY_BUTTON_WIDTH"))
        self.assertEqual(menu_action_row.MENU_AUTOCOPY_BUTTON_WIDTH, 68)
        self.assertFalse(hasattr(menu_action_row, "MENU_AUTOCOPY_ARROW_BUTTON_WIDTH"))
        self.assertEqual(MENU_NOTE_INPUT_WIDTH, 105)
        self.assertEqual(MENU_CONTROL_ROW_SPACING, 6)
        self.assertEqual(MENU_QUICK_FIELD_WIDTH, 146)
        self.assertEqual(MENU_QUICK_MODE_WIDTH, menu_action_row.MENU_AUTOCOPY_BUTTON_WIDTH)
        self.assertEqual(MENU_SQUARE_BUTTON_SIZE, 32)
        self.assertEqual(MENU_NOTE_BUTTON_WIDTH, MENU_SQUARE_BUTTON_SIZE)
        self.assertEqual(MENU_RESET_BUTTON_WIDTH, MENU_SQUARE_BUTTON_SIZE)
        self.assertEqual(MENU_NOTE_BUTTON_WIDTH, MENU_RESET_BUTTON_WIDTH)
        expected_width = (
            MENU_QUICK_FIELD_WIDTH
            + MENU_QUICK_MODE_WIDTH
            + MENU_NOTE_BUTTON_WIDTH
            + (MENU_CONTROL_ROW_SPACING * 2)
            + MENU_CONTROL_ROW_MARGINS[0]
            + MENU_CONTROL_ROW_MARGINS[2]
        )
        expected_height = (
            (MENU_SQUARE_BUTTON_SIZE * 2)
            + MENU_CONTROL_ROW_SPACING
            + MENU_CONTROL_ROW_MARGINS[1]
            + MENU_CONTROL_ROW_MARGINS[3]
        )
        self.assertEqual(MENU_QUICK_BLOCK_WIDTH, expected_width)
        self.assertEqual(MENU_QUICK_BLOCK_HEIGHT, expected_height)

    def test_control_rows_share_action_row_left_edge(self):
        self.assertEqual(MENU_CONTROL_ROW_MARGINS[0], MENU_ACTION_ROW_MARGINS[0])
        self.assertEqual(MENU_CONTROL_ROW_SPACING, 6)

    def test_formats_auto_copy_caption_as_compact_symbols(self):
        self.assertEqual(format_auto_copy_caption("result"), "=→⧉")
        self.assertEqual(format_auto_copy_caption("text"), "=→Tx")
        self.assertEqual(format_auto_copy_caption("money_text"), "=→₽т")
        self.assertEqual(format_auto_copy_caption("off"), "=→○")

    def test_formats_auto_copy_menu_labels_for_popup(self):
        self.assertTrue(hasattr(menu_action_row, "format_auto_copy_menu_label"))
        self.assertEqual(menu_action_row.format_auto_copy_menu_label("off"), "○  Отключить")
        self.assertEqual(menu_action_row.format_auto_copy_menu_label("result"), "⧉  Копировать результат")
        self.assertEqual(menu_action_row.format_auto_copy_menu_label("text"), "Tx  Число → текст")
        self.assertEqual(menu_action_row.format_auto_copy_menu_label("money_text"), "₽т  Сумма ₽ текстом")

    def test_auto_copy_tooltip_explains_compact_symbols(self):
        self.assertTrue(hasattr(menu_action_row, "auto_copy_mode_tooltip"))
        tooltip = menu_action_row.auto_copy_mode_tooltip("money_text")
        self.assertIn("= — после Enter или =", tooltip)
        self.assertIn("→ — отправить в буфер обмена", tooltip)
        self.assertIn("₽т — сумма ₽ текстом", tooltip)

    def test_hotkey_caption_keeps_unknown_words_readable(self):
        self.assertEqual(format_hotkey_caption("shift+num lock"), "Shift+NumLock")


if __name__ == "__main__":
    unittest.main()
