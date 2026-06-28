#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
styles.py — централизованные QSS-стили для CalcNumLock.

Стиль приведён к визуальной логике Win11 Calculator:
  • единая палитра light/dark;
  • Segoe UI Variable / Segoe UI;
  • мягкие hover/pressed-состояния;
  • скругления 4/8 px;
  • единые стили для QMenu, QLineEdit, QToolButton, QSlider;
  • совместимость со старыми импортами из calc_numlock_tray.pyw и pro_secure.py.

Версия: 7.9-theme-choice
"""
from __future__ import annotations

import sys
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Палитра
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Palette:
    name: str

    window_bg: str
    surface_bg: str
    titlebar_bg: str

    text_primary: str
    text_secondary: str
    text_disabled: str

    digit_bg: str
    digit_hover: str
    digit_pressed: str
    digit_text: str

    operator_bg: str
    operator_hover: str
    operator_pressed: str
    operator_text: str

    function_bg: str
    function_hover: str
    function_pressed: str
    function_text: str

    equals_bg: str
    equals_hover: str
    equals_pressed: str
    equals_text: str

    chip_bg: str
    chip_hover: str
    chip_pressed: str
    chip_text: str

    border: str
    separator: str

    accent: str


DARK_PALETTE = Palette(
    name="dark",

    window_bg="#202020",
    surface_bg="#2B2B2B",
    titlebar_bg="#202020",

    text_primary="#FFFFFF",
    text_secondary="#A6A6A6",
    text_disabled="#5F5F5F",

    digit_bg="#3B3B3B",
    digit_hover="#454545",
    digit_pressed="#333333",
    digit_text="#FFFFFF",

    operator_bg="#323232",
    operator_hover="#3C3C3C",
    operator_pressed="#2A2A2A",
    operator_text="#FFFFFF",

    function_bg="#323232",
    function_hover="#3C3C3C",
    function_pressed="#2A2A2A",
    function_text="#FFFFFF",

    equals_bg="#4CC2FF",
    equals_hover="#5DC9FF",
    equals_pressed="#3FB7F5",
    equals_text="#000000",

    chip_bg="transparent",
    chip_hover="#3B3B3B",
    chip_pressed="#2D2D2D",
    chip_text="#FFFFFF",

    border="#2B2B2B",
    separator="#2D2D2D",

    accent="#4CC2FF",
)


LIGHT_PALETTE = Palette(
    name="light",

    window_bg="#F3F3F3",
    surface_bg="#FAFAFA",
    titlebar_bg="#F3F3F3",

    text_primary="#1A1A1A",
    text_secondary="#5F5F5F",
    text_disabled="#A0A0A0",

    digit_bg="#FBFBFB",
    digit_hover="#F4F4F4",
    digit_pressed="#EAEAEA",
    digit_text="#1A1A1A",

    operator_bg="#F0F0F0",
    operator_hover="#E8E8E8",
    operator_pressed="#DEDEDE",
    operator_text="#1A1A1A",

    function_bg="#F0F0F0",
    function_hover="#E8E8E8",
    function_pressed="#DEDEDE",
    function_text="#1A1A1A",

    equals_bg="#0067C0",
    equals_hover="#1971D8",
    equals_pressed="#005CAB",
    equals_text="#FFFFFF",

    chip_bg="transparent",
    chip_hover="#EAEAEA",
    chip_pressed="#DCDCDC",
    chip_text="#1A1A1A",

    border="#E3E3E3",
    separator="#E5E5E5",

    accent="#0067C0",
)


RADIUS_BUTTON = 4
RADIUS_CARD = 8
FONT_TEXT = '"Segoe UI Variable Text", "Segoe UI", sans-serif'
FONT_DISPLAY = '"Segoe UI Variable Display", "Segoe UI", sans-serif'


def is_windows_dark_mode() -> bool:
    """True, если в Windows включена тёмная тема приложений."""
    if not sys.platform.startswith("win"):
        return True
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return value == 0
    except Exception:
        return True


THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_MODES = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK)

_theme_mode = THEME_SYSTEM


def normalize_theme_mode(value: str | None) -> str:
    mode = str(value or THEME_SYSTEM).strip().lower()
    return mode if mode in THEME_MODES else THEME_SYSTEM


def active_palette(theme_mode: str | None = None) -> Palette:
    mode = normalize_theme_mode(theme_mode if theme_mode is not None else _theme_mode)
    if mode == THEME_LIGHT:
        return LIGHT_PALETTE
    if mode == THEME_DARK:
        return DARK_PALETTE
    return DARK_PALETTE if is_windows_dark_mode() else LIGHT_PALETTE


P = active_palette(THEME_SYSTEM)


# ---------------------------------------------------------------------------
# Генераторы QSS
# ---------------------------------------------------------------------------
def build_dialog_qss(p: Palette) -> str:
    return f"""
QDialog {{
    background-color: {p.window_bg};
    color: {p.text_primary};
    font-family: {FONT_TEXT};
    font-size: 13px;
}}
QLabel {{
    color: {p.text_primary};
    background: transparent;
}}
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background-color: {p.operator_bg};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_BUTTON}px;
    padding: 4px 7px;
    selection-background-color: {p.accent};
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {p.text_secondary};
}}
QPlainTextEdit[role="note-popup-input"] {{
    border: 1px solid {p.border};
}}
QPlainTextEdit[role="note-popup-input"]:focus {{
    border: 1px solid {p.text_secondary};
}}
QPushButton {{
    background-color: {p.operator_bg};
    color: {p.operator_text};
    border: 1px solid {p.border};
    border-radius: {RADIUS_BUTTON}px;
    padding: 5px 16px;
    min-height: 26px;
    outline: none;
}}
QPushButton:hover {{
    background-color: {p.operator_hover};
}}
QPushButton:pressed {{
    background-color: {p.operator_pressed};
}}
QPushButton:default {{
    background-color: {p.equals_bg};
    color: {p.equals_text};
    border: 1px solid {p.equals_bg};
}}
QPushButton:default:hover {{
    background-color: {p.equals_hover};
}}
QPushButton:default:pressed {{
    background-color: {p.equals_pressed};
}}
QTableWidget {{
    background-color: {p.surface_bg};
    color: {p.text_primary};
    gridline-color: {p.separator};
    border: 1px solid {p.border};
    selection-background-color: {p.accent};
}}
QHeaderView::section {{
    background-color: {p.operator_bg};
    color: {p.text_primary};
    border: 1px solid {p.border};
    padding: 4px 6px;
}}
QRadioButton, QCheckBox {{
    color: {p.text_primary};
    background: transparent;
}}
"""


def build_settings_qss(p: Palette) -> str:
    return f"""
QDialog {{
    background-color: {p.window_bg};
    color: {p.text_primary};
    font-family: {FONT_TEXT};
    font-size: 13px;
}}
QTabWidget::pane {{
    background-color: {p.window_bg};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_CARD}px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: {p.operator_bg};
    color: {p.text_secondary};
    padding: 6px 14px;
    border: 1px solid {p.border};
    border-bottom: none;
    border-top-left-radius: {RADIUS_BUTTON}px;
    border-top-right-radius: {RADIUS_BUTTON}px;
    min-height: 22px;
}}
QTabBar::tab:hover {{
    background-color: {p.operator_hover};
    color: {p.text_primary};
}}
QTabBar::tab:selected {{
    background-color: {p.window_bg};
    color: {p.text_primary};
}}
QTabWidget > QWidget {{
    background-color: {p.window_bg};
    color: {p.text_primary};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background-color: {p.window_bg};
}}
QLabel, QCheckBox, QRadioButton {{
    color: {p.text_primary};
    background: transparent;
}}
QGroupBox {{
    color: {p.text_primary};
    background: transparent;
    border: 1px solid {p.border};
    border-radius: {RADIUS_CARD}px;
    margin-top: 10px;
    padding: 9px 7px 7px 7px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: {p.text_secondary};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background-color: {p.operator_bg};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_BUTTON}px;
    padding: 4px 7px;
    selection-background-color: {p.accent};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {p.accent};
}}
QPushButton {{
    background-color: {p.operator_bg};
    color: {p.operator_text};
    border: 1px solid {p.border};
    border-radius: {RADIUS_BUTTON}px;
    padding: 5px 14px;
    min-height: 26px;
    outline: none;
}}
QPushButton:hover {{
    background-color: {p.operator_hover};
}}
QPushButton:pressed {{
    background-color: {p.operator_pressed};
}}
QPushButton:default {{
    background-color: {p.equals_bg};
    color: {p.equals_text};
    border: 1px solid {p.equals_bg};
}}
QPushButton:default:hover {{
    background-color: {p.equals_hover};
}}
QPushButton:default:pressed {{
    background-color: {p.equals_pressed};
}}
QTableWidget, QTableView {{
    background-color: {p.surface_bg};
    alternate-background-color: {p.operator_bg};
    color: {p.text_primary};
    gridline-color: {p.separator};
    border: 1px solid {p.border};
    selection-background-color: {p.accent};
    selection-color: {p.equals_text};
}}
QTableWidget::item, QTableView::item {{
    background-color: {p.surface_bg};
    color: {p.text_primary};
    padding: 3px 5px;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {p.accent};
    color: {p.equals_text};
}}
QTableCornerButton::section {{
    background-color: {p.operator_bg};
    border: 1px solid {p.border};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 4px 2px 4px 0;
}}
QScrollBar::handle:vertical {{
    background-color: {p.text_disabled};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {p.text_secondary};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0 4px 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background-color: {p.text_disabled};
    border-radius: 3px;
    min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {p.text_secondary};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
"""


def build_menu_qss(p: Palette) -> str:
    return f"""
QMenu {{
    background-color: {p.surface_bg};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_CARD}px;
    padding: 4px;
    font-family: {FONT_TEXT};
    font-size: 13px;
}}
QMenu::item {{
    background: transparent;
    color: {p.text_primary};
    padding: 6px 16px;
    min-height: 18px;
    border-radius: {RADIUS_BUTTON}px;
}}
QMenu::item:selected {{
    background-color: {p.digit_hover};
}}
QMenu::item:disabled {{
    color: {p.text_disabled};
}}
QMenu::separator {{
    height: 1px;
    background-color: {p.separator};
    margin: 4px 8px;
}}
QMenu::indicator {{
    width: 16px;
    height: 16px;
}}
QMenu::right-arrow {{
    width: 9px;
    height: 9px;
}}
"""


def build_slider_qss(p: Palette) -> str:
    return f"""
QSlider {{
    background: transparent;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background-color: {p.separator};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 13px;
    height: 13px;
    margin: -5px 0;
    background-color: {p.accent};
    border: none;
    border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{
    background-color: {p.equals_hover};
}}
QSlider::sub-page:horizontal {{
    background-color: {p.accent};
    border-radius: 2px;
}}
"""


def build_note_input_qss(p: Palette) -> str:
    return f"""
QLineEdit {{
    background-color: {p.operator_bg};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_BUTTON}px;
    padding: 3px 7px;
    min-height: 24px;
    selection-background-color: {p.accent};
}}
QLineEdit:hover {{
    background-color: {p.operator_hover};
}}
QLineEdit:focus {{
    border: 1px solid {p.accent};
    background-color: {p.operator_bg};
}}
QLineEdit:disabled {{
    color: {p.text_disabled};
    background-color: {p.operator_pressed};
}}
"""


def build_toolbutton_qss(p: Palette) -> str:
    return f"""
QToolButton {{
    background-color: {p.operator_bg};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_BUTTON}px;
    padding: 2px 7px;
    min-width: 26px;
    min-height: 24px;
    font-family: {FONT_TEXT};
    font-size: 13px;
    outline: none;
}}
QToolButton:hover {{
    background-color: {p.operator_hover};
}}
QToolButton:pressed {{
    background-color: {p.operator_pressed};
}}
QToolButton:disabled {{
    color: {p.text_disabled};
}}
"""


def build_reset_button_qss(p: Palette) -> str:
    return f"""
QPushButton {{
    background-color: {p.operator_bg};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_BUTTON}px;
    padding: 0;
    min-width: 24px;
    min-height: 24px;
    font-family: {FONT_TEXT};
    font-size: 13px;
    font-weight: 600;
    outline: none;
}}
QPushButton:hover {{
    background-color: {p.operator_hover};
    color: {p.text_primary};
}}
QPushButton:pressed {{
    background-color: {p.operator_pressed};
}}
"""


def build_menu_checkbox_qss(p: Palette) -> str:
    return f"""
QCheckBox {{
    color: {p.text_primary};
    background: transparent;
    font-family: {FONT_TEXT};
    font-size: 13px;
    spacing: 6px;
}}
QCheckBox:hover {{
    color: {p.text_primary};
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
}}
QCheckBox:disabled {{
    color: {p.text_disabled};
}}
"""


def build_section_header_qss(p: Palette) -> str:
    return f"""
QWidget {{
    background-color: {p.operator_bg};
    border: none;
    border-radius: {RADIUS_BUTTON}px;
}}
"""


def build_section_header_label_qss(p: Palette) -> str:
    return (
        f"color:{p.text_secondary}; "
        "font-weight:600; font-size:11px; background:transparent;"
    )



# ---------------------------------------------------------------------------
# QSS встроенного стандартного калькулятора CalcNumLock 9.0
# ---------------------------------------------------------------------------
def build_standard_calc_qss(p: Palette) -> str:
    return f"""
QMainWindow, QDialog, QWidget#WCRoot {{
    background-color: {p.window_bg};
    color: {p.text_primary};
    font-family: {FONT_TEXT};
    font-size: 18px;
}}
QFrame[role="navbar"] {{ background: transparent; border: none; }}
QPushButton[btnRole="history"] {{
    background-color: {p.operator_bg}; color: {p.text_secondary};
    border: 1px solid {p.border}; border-radius: {RADIUS_BUTTON}px;
    font-family: {FONT_TEXT}; font-size: 17px; font-weight: 480;
    text-align: right; padding: 0 10px; min-height: 32px;
}}
QPushButton[btnRole="history"]:hover {{ background-color: {p.operator_hover}; color: {p.text_primary}; }}
QPushButton[btnRole="history"]:pressed {{ background-color: {p.operator_pressed}; }}
QMenu {{
    background-color: {p.surface_bg}; color: {p.text_primary};
    border: 1px solid {p.border}; border-radius: {RADIUS_CARD}px; padding: 4px;
    font-family: {FONT_TEXT}; font-size: 13px;
}}
QMenu::item {{ background: transparent; padding: 6px 16px; border-radius: {RADIUS_BUTTON}px; }}
QMenu::item:selected {{ background-color: {p.digit_hover}; }}
QMenu::item:disabled {{ color: {p.text_secondary}; }}
QMenu::separator {{ height: 1px; background-color: {p.separator}; margin: 4px 8px; }}
QFrame[role="history-popup"] {{
    background-color: {p.surface_bg};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_CARD}px;
}}
QPlainTextEdit[role="history-list"] {{
    background-color: {p.surface_bg};
    color: {p.text_primary};
    border: none;
    selection-background-color: {p.accent};
    selection-color: {p.equals_text};
    font-family: {FONT_TEXT};
    font-size: 13px;
    padding: 6px 8px;
}}
QPlainTextEdit[role="history-list"]:focus {{
    border: none;
    outline: none;
}}
QLabel[labelRole="expression"] {{
    color: {p.text_secondary}; font-family: {FONT_TEXT}; font-size: 18px; padding: 0 12px;
}}
QLabel[labelRole="display"] {{
    color: {p.text_primary}; font-family: {FONT_DISPLAY}; font-size: 73px;
    font-weight: 360; padding: 0 14px 12px 0;
}}
QFrame[role="separator"] {{
    background-color: {p.separator}; border: none; max-height: 1px; min-height: 1px;
}}
QPushButton {{
    border: none; border-radius: {RADIUS_BUTTON}px; font-family: {FONT_TEXT};
    font-weight: 480; padding: 0; min-height: 36px; outline: none;
}}
QPushButton:focus {{ outline: none; border: none; }}
QPushButton[btnRole="digit"] {{
    background-color: {p.digit_bg}; color: {p.digit_text}; font-size: 26px; border: 1px solid {p.border};
}}
QPushButton[btnRole="digit"]:hover {{ background-color: {p.digit_hover}; }}
QPushButton[btnRole="digit"]:pressed {{ background-color: {p.digit_pressed}; }}
QPushButton[btnRole="operator"] {{
    background-color: {p.operator_bg}; color: {p.operator_text}; font-size: 22px; border: 1px solid {p.border};
}}
QPushButton[btnRole="operator"]:hover {{ background-color: {p.operator_hover}; }}
QPushButton[btnRole="operator"]:pressed {{ background-color: {p.operator_pressed}; }}
QPushButton[btnRole="function"] {{
    background-color: {p.function_bg}; color: {p.function_text}; font-size: 18px; border: 1px solid {p.border};
}}
QPushButton[btnRole="function"]:hover {{ background-color: {p.function_hover}; }}
QPushButton[btnRole="function"]:pressed {{ background-color: {p.function_pressed}; }}
QPushButton[btnRole="equals"] {{
    background-color: {p.equals_bg}; color: {p.equals_text}; font-size: 26px;
    font-weight: 720; border: 1px solid {p.border};
}}
QPushButton[btnRole="equals"]:hover {{ background-color: {p.equals_hover}; }}
QPushButton[btnRole="equals"]:pressed {{ background-color: {p.equals_pressed}; }}
QPushButton[btnRole="chip"] {{
    background-color: {p.chip_bg}; color: {p.chip_text}; font-size: 16px;
    min-height: 26px; max-height: 28px; padding: 0 8px; border: none;
    border-radius: {RADIUS_BUTTON}px; text-align: center;
}}
QPushButton[btnRole="chip"]:hover {{ background-color: {p.chip_hover}; }}
QPushButton[btnRole="chip"]:pressed {{ background-color: {p.chip_pressed}; }}
QPushButton:disabled {{ color: {p.text_disabled}; }}
QToolTip {{
    background-color: {p.surface_bg}; color: {p.text_primary}; border: 1px solid {p.border};
    padding: 4px 8px; border-radius: 4px;
}}
"""

# Совместимое имя для старого импорта из standard_calc.py.
build_qss = build_standard_calc_qss


# ---------------------------------------------------------------------------
# Готовые QSS-константы. Старые имена сохранены, чтобы не переписывать импорты.
# ---------------------------------------------------------------------------
def apply_theme_mode(theme_mode: str | None = None) -> Palette:
    """Пересобирает все QSS-константы под выбранный режим темы."""
    global _theme_mode, P
    global DIALOG_QSS, SETTINGS_QSS, MENU_QSS, SLIDER_QSS, NOTE_INPUT_QSS
    global TOOLBUTTON_QSS, RESET_BUTTON_QSS, MENU_CHECKBOX_QSS
    global SECTION_HEADER_QSS, SECTION_HEADER_LABEL_QSS
    global LABEL_TITLE, LABEL_DESC, LABEL_DIM, LABEL_SEPARATOR, LABEL_NOTE, TRANSPARENT_BG

    _theme_mode = normalize_theme_mode(theme_mode)
    P = active_palette(_theme_mode)

    DIALOG_QSS = build_dialog_qss(P)
    SETTINGS_QSS = build_settings_qss(P)
    MENU_QSS = build_menu_qss(P)
    SLIDER_QSS = build_slider_qss(P)
    NOTE_INPUT_QSS = build_note_input_qss(P)
    TOOLBUTTON_QSS = build_toolbutton_qss(P)
    RESET_BUTTON_QSS = build_reset_button_qss(P)
    MENU_CHECKBOX_QSS = build_menu_checkbox_qss(P)
    SECTION_HEADER_QSS = build_section_header_qss(P)
    SECTION_HEADER_LABEL_QSS = build_section_header_label_qss(P)

    LABEL_TITLE = f"font-size:15px; color:{P.text_primary}; background:transparent;"
    LABEL_DESC = f"color:{P.text_secondary}; background:transparent;"
    LABEL_DIM = f"color:{P.text_secondary}; font-size:11px; background:transparent;"
    LABEL_SEPARATOR = f"color:{P.separator}; background:transparent;"
    LABEL_NOTE = f"color:{P.text_primary}; background:transparent;"
    TRANSPARENT_BG = "background:transparent;"
    return P


def current_theme_mode() -> str:
    return _theme_mode


apply_theme_mode(THEME_SYSTEM)


__all__ = [
    "Palette", "LIGHT_PALETTE", "DARK_PALETTE",
    "THEME_SYSTEM", "THEME_LIGHT", "THEME_DARK", "THEME_MODES",
    "normalize_theme_mode", "active_palette", "apply_theme_mode", "current_theme_mode",
    "is_windows_dark_mode",
    "build_standard_calc_qss", "build_qss",
    "DIALOG_QSS", "SETTINGS_QSS", "MENU_QSS", "SLIDER_QSS", "NOTE_INPUT_QSS",
    "TOOLBUTTON_QSS", "RESET_BUTTON_QSS", "MENU_CHECKBOX_QSS",
    "SECTION_HEADER_QSS", "SECTION_HEADER_LABEL_QSS",
    "LABEL_TITLE", "LABEL_DESC", "LABEL_DIM", "LABEL_SEPARATOR", "LABEL_NOTE",
    "TRANSPARENT_BG",
]
