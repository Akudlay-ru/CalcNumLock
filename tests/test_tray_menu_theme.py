from pathlib import Path
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]
TRAY_SOURCE = APP_ROOT / "calc_numlock_tray.pyw"


class TrayMenuThemeTests(unittest.TestCase):
    def test_external_submenus_are_restyled_with_current_menu_theme(self):
        source = TRAY_SOURCE.read_text(encoding="utf-8")

        self.assertIn("def _apply_menu_theme_tree(", source)
        self.assertIn("self._apply_menu_theme_tree(tray_windows_menu)", source)
        self.assertIn("self._apply_menu_theme_tree(self.activity_menu)", source)

    def test_quick_auto_copy_uses_single_mode_popup_button(self):
        source = TRAY_SOURCE.read_text(encoding="utf-8")
        start = source.index("def _build_quick_auto_copy_mode_menu")
        end = source.index("def _refresh_quick_auto_copy_mode_menu", start)
        quick_menu_source = source[start:end]
        row_start = source.index("# --- Быстрые настройки автокопирования результата ---")
        row_end = source.index("if self._pro_soft_active():", row_start)
        row_source = source[row_start:row_end]

        self.assertIn("self.btn_quick_auto_copy.setFixedSize(MENU_QUICK_MODE_WIDTH, MENU_SQUARE_BUTTON_SIZE)", source)
        self.assertIn("self.btn_quick_auto_copy.setPopupMode(QToolButton.InstantPopup)", source)
        self.assertIn("QToolButton::menu-indicator { image: none; width: 0px; }", source)
        self.assertIn("self.quick_auto_copy_menu = self._build_quick_auto_copy_mode_menu(self.btn_quick_auto_copy)", source)
        self.assertIn("self.btn_quick_auto_copy.setMenu(self.quick_auto_copy_menu)", source)
        self.assertNotIn("▼", row_source)
        self.assertNotIn("self.btn_quick_auto_copy.clicked.connect(lambda _checked=False: self._toggle_auto_copy_on_enter())", source)
        self.assertNotIn("self.btn_quick_auto_copy_menu", row_source)
        self.assertNotIn("MENU_AUTOCOPY_ARROW_BUTTON_WIDTH", source)
        self.assertNotIn("self.btn_quick_auto_copy.setPopupMode(QToolButton.MenuButtonPopup)", source)
        self.assertNotIn("self.chk_quick_auto_copy", source)
        self.assertNotIn("setCheckable(True)", quick_menu_source)

    def test_quick_auto_copy_toggle_syncs_builtin_calculator_icon(self):
        source = TRAY_SOURCE.read_text(encoding="utf-8")
        start = source.index("def _toggle_auto_copy_on_enter")
        end = source.index("def _set_auto_copy_on_enter_from_quick", start)
        toggle_source = source[start:end]

        self.assertIn("self._builtin_calc_window.set_clipboard_mode(self.calc_clipboard_mode, notify=False)", toggle_source)

    def test_quick_auto_copy_menu_refresh_updates_visible_button_text(self):
        source = TRAY_SOURCE.read_text(encoding="utf-8")
        start = source.index("def _refresh_quick_auto_copy_mode_menu")
        end = source.index("def _set_auto_copy_mode_from_quick", start)
        refresh_source = source[start:end]

        self.assertIn("self.btn_quick_auto_copy.setText(self._quick_auto_copy_label())", refresh_source)
        self.assertIn("self.btn_quick_auto_copy.setToolTip(self._quick_auto_copy_tooltip())", refresh_source)

    def test_second_launch_can_wake_existing_calculator_without_message_box(self):
        source = TRAY_SOURCE.read_text(encoding="utf-8")

        self.assertIn("calc_second_launch_shows_calc", source)
        self.assertIn("WM_CALCNUMLOCK_SHOW_CALC", source)
        self.assertIn("_request_existing_instance_show_calc()", source)

        main_start = source.index("def main():")
        main_source = source[main_start:]
        self.assertIn("_second_launch_should_show_calc()", main_source)
        self.assertIn("_request_existing_instance_show_calc()", main_source)


if __name__ == "__main__":
    unittest.main()
