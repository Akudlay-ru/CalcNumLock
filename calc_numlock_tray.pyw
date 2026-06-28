"""NumLockCalc 2026 Free Core release 9.0.1.

Free Core: быстрый локальный калькулятор для Windows, NumLock-hotkey,
встроенный калькулятор, единицы измерения, буфер обмена, история и базовые
настройки. Публичная сборка не содержит Pro-модулей, лицензирования,
автозамены, дневника, скриншотов, трекера активности и окон в трей.
"""

import sys
import os
import json
import time
import ctypes
import subprocess
import shlex
import traceback
import importlib
import webbrowser
import hashlib
import platform
import uuid
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from ctypes import wintypes
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Профилирование запуска / диагностика зависаний
# ---------------------------------------------------------------------------
_STARTUP_T0 = time.perf_counter()
_STARTUP_LAST = _STARTUP_T0

def startup_mark(label: str) -> None:
    """Пишет измеряемую точку старта в debug.log и startup_profile.log.
    Формат: общий ms от старта процесса + delta ms от предыдущей точки.
    """
    global _STARTUP_LAST
    try:
        now = time.perf_counter()
        total_ms = int((now - _STARTUP_T0) * 1000)
        delta_ms = int((now - _STARTUP_LAST) * 1000)
        _STARTUP_LAST = now
        line = f"STARTUP +{total_ms:05d} ms Δ{delta_ms:05d} ms | {label}"
        try:
            log(line)
        except Exception:
            pass
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOGS_DIR / "startup_profile.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {line}\n")
        except Exception:
            pass
    except Exception:
        pass

# Скрываем консольное окно ДО импорта keyboard (он любит её мигать).
# SW_HIDE = 0. Если консоли нет — GetConsoleWindow вернёт NULL, ничего не делаем.
try:
    _hcon = ctypes.windll.kernel32.GetConsoleWindow()
    if _hcon:
        ctypes.windll.user32.ShowWindow(_hcon, 0)
except Exception:
    pass

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
    KEYBOARD_IMPORT_ERROR = ""
except Exception as _keyboard_exc:
    keyboard = None
    KEYBOARD_AVAILABLE = False
    KEYBOARD_IMPORT_ERROR = f"{type(_keyboard_exc).__name__}: {_keyboard_exc}"

# Окончательно отвязываем процесс от консоли (если осталась)
try:
    ctypes.windll.kernel32.FreeConsole()
except Exception:
    pass

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, QTimer, QFileInfo
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QAction,
    QWidgetAction, QSlider, QLabel, QHBoxLayout, QVBoxLayout,
    QWidget, QActionGroup, QDialog, QPushButton, QMessageBox,
    QLineEdit, QFileDialog, QInputDialog, QCheckBox,
    QTabWidget, QFormLayout, QSpinBox, QDoubleSpinBox, QGroupBox, QScrollArea,
    QFrame, QComboBox, QRadioButton, QButtonGroup, QPlainTextEdit,
    QSizePolicy, QToolButton, QFileIconProvider, QTableWidget
)

# Импорт стилей
import styles as app_styles
from styles import (
    DIALOG_QSS, SETTINGS_QSS, MENU_QSS, SLIDER_QSS, NOTE_INPUT_QSS,
    TOOLBUTTON_QSS, RESET_BUTTON_QSS, MENU_CHECKBOX_QSS,
    THEME_SYSTEM, THEME_LIGHT, THEME_DARK, normalize_theme_mode,
    LABEL_TITLE, LABEL_DESC, LABEL_DIM, LABEL_SEPARATOR, LABEL_NOTE,
    SECTION_HEADER_QSS, SECTION_HEADER_LABEL_QSS, TRANSPARENT_BG
)

# ---------------------------------------------------------------------------
# Базовый функционал — всегда нужен.
# ---------------------------------------------------------------------------
from functions import *
# Приватные имена (with leading _) star-импорт не подхватывает — добираем явно.
from functions import (
    _send_ctrl_v, _send_ctrl_c, _force_foreground, _apply_native_titlebar,
    _get_text, _get_class, _exe_basename_of_hwnd,
)

# ---------------------------------------------------------------------------
# Отложенные модули.
#
# Pro-слои не импортируются на верхнем уровне. Главный сценарий —
# открыть калькулятор и начать считать; платные модули поднимаются позже
# и только при наличии license.txt.
# ---------------------------------------------------------------------------
pro_soft = None
pro_secure = None
extra = None
managed_windows = None
PRO_SOFT_AVAILABLE = False
PRO_SECURE_AVAILABLE = False
EXTRA_AVAILABLE = False
MANAGED_WINDOWS_AVAILABLE = False
LICENSE_FILE = APP_ROOT / "license.txt"
LICENSE_VERIFIER_MODULE = "license_verifier"
LICENSE_STRICT_VERIFICATION = True
PAID_FORCE_SHOW_DAYS = (3, 7, 12)
PRODUCT_DISPLAY_NAME = "NumLockCalc 2026"
PRODUCT_VERSION_LABEL = "9.0.1"
STARTUP_SHORTCUT_NAME = f"{PRODUCT_DISPLAY_NAME} 9.0.1.lnk"
KEYBOARD_IDLE_RECOVERY_SEC = 30 * 60
KEYBOARD_RECOVERY_POLL_MS = 60 * 1000
LICENSE_REQUEST_YANDEX_FORM_URL = "https://forms.yandex.ru/u/6a1726ce505690503a9fa8c3"
LICENSE_REQUEST_FIELD_DEFAULTS = {
    "product": "",
    "version": "",
    "edition": "",
    "hardware_code": "",
    "source": "",
}

AUTO_COPY_OFF = "off"
AUTO_COPY_RESULT = "result"
AUTO_COPY_TEXT = "text"
AUTO_COPY_MONEY_TEXT = "money_text"
AUTO_COPY_MODES = (AUTO_COPY_OFF, AUTO_COPY_RESULT, AUTO_COPY_TEXT, AUTO_COPY_MONEY_TEXT)

CALC_CLIPBOARD_OFF = AUTO_COPY_OFF
CALC_CLIPBOARD_RESULT = AUTO_COPY_RESULT
CALC_CLIPBOARD_TEXT = AUTO_COPY_TEXT
CALC_CLIPBOARD_MONEY_TEXT = AUTO_COPY_MONEY_TEXT
CALC_CLIPBOARD_MODES = AUTO_COPY_MODES


def _normalize_auto_copy_mode(value: str | None) -> str:
    mode = str(value or AUTO_COPY_RESULT).strip().lower()
    return mode if mode in AUTO_COPY_MODES else AUTO_COPY_RESULT


def _normalize_calc_clipboard_mode(value: str | None, allow_money_text: bool = False) -> str:
    mode = _normalize_auto_copy_mode(value)
    if mode == CALC_CLIPBOARD_MONEY_TEXT and not allow_money_text:
        return CALC_CLIPBOARD_RESULT
    return mode

# ---------------------------------------------------------------------------
# Встроенный стандартный калькулятор CalcNumLock — форк вместо Windows Calculator.
# ---------------------------------------------------------------------------
BUILTIN_CALC_CMD = "__calcnumlock_builtin_standard__"
DEFAULT_CALC_HISTORY_FILE = DATA_DIR / "calc_history.txt"
try:
    startup_mark("CALC_IMPORT_STANDARD_CALC_BEGIN")
    from standard_calc import StandardPercentCalculator
    startup_mark("CALC_IMPORT_STANDARD_CALC_DONE")
    BUILTIN_CALC_AVAILABLE = True
except Exception as _sc_err:
    StandardPercentCalculator = None
    BUILTIN_CALC_AVAILABLE = False
    try:
        log(f"standard_calc import failed: {_sc_err}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Преобразование числа в русский текст (для пункта меню «Число → текст»)
# ---------------------------------------------------------------------------
# Целое до 999 999 999 999 (триллионов нет — на практике хватает с запасом).
# Дробная часть: до 6 знаков, читается как «N целых M десятитысячных» и т.п.
# Если число отрицательное — префикс «минус ».

_RU_ONES_M = ("", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_RU_ONES_F = ("", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_RU_TEENS = ("десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
             "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать")
_RU_TENS = ("", "", "двадцать", "тридцать", "сорок", "пятьдесят",
            "шестьдесят", "семьдесят", "восемьдесят", "девяносто")
_RU_HUNDREDS = ("", "сто", "двести", "триста", "четыреста",
                "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот")


def _ru_plural(n: int, forms: tuple[str, str, str]) -> str:
    """forms = (1, 2-4, 5+). Например ("рубль", "рубля", "рублей")."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def _ru_three_digits(num: int, feminine: bool = False) -> str:
    """Триада 0..999 → текст. feminine=True для разрядов «тысячи»."""
    if num == 0:
        return ""
    parts: list[str] = []
    h = num // 100
    rest = num % 100
    if h:
        parts.append(_RU_HUNDREDS[h])
    if rest >= 20:
        t = rest // 10
        u = rest % 10
        parts.append(_RU_TENS[t])
        if u:
            parts.append((_RU_ONES_F if feminine else _RU_ONES_M)[u])
    elif rest >= 10:
        parts.append(_RU_TEENS[rest - 10])
    elif rest > 0:
        parts.append((_RU_ONES_F if feminine else _RU_ONES_M)[rest])
    return " ".join(parts)


def _ru_int_to_text(n: int) -> str:
    """Целое число → русский текст. Без единиц — только число.
    Для нуля возвращает «ноль»."""
    if n == 0:
        return "ноль"
    sign = "минус " if n < 0 else ""
    n = abs(n)

    # Разбиваем на триады: единицы, тысячи, миллионы, миллиарды.
    triads = []
    while n > 0:
        triads.append(n % 1000)
        n //= 1000
    # triads[0] — единицы, triads[1] — тысячи, ...

    parts: list[str] = []
    # Миллиарды
    if len(triads) > 3 and triads[3]:
        parts.append(_ru_three_digits(triads[3], feminine=False))
        parts.append(_ru_plural(triads[3], ("миллиард", "миллиарда", "миллиардов")))
    # Миллионы
    if len(triads) > 2 and triads[2]:
        parts.append(_ru_three_digits(triads[2], feminine=False))
        parts.append(_ru_plural(triads[2], ("миллион", "миллиона", "миллионов")))
    # Тысячи
    if len(triads) > 1 and triads[1]:
        parts.append(_ru_three_digits(triads[1], feminine=True))
        parts.append(_ru_plural(triads[1], ("тысяча", "тысячи", "тысяч")))
    # Единицы
    if triads[0]:
        parts.append(_ru_three_digits(triads[0], feminine=False))
    return sign + " ".join(p for p in parts if p)


def _capitalize_first_letter(text: str) -> str:
    """Делает первую букву заглавной, не трогая остальной текст."""
    if not text:
        return text
    for i, ch in enumerate(text):
        if ch.isalpha():
            return text[:i] + ch.upper() + text[i + 1:]
    return text


def number_to_russian_text(value: str) -> Optional[str]:
    """
    Парсит строку как число (поддерживает «1 234,56», «1,234.56», «-42»),
    возвращает текстовое представление в русском, либо None, если строка
    не похожа на число.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Убираем неразрывные пробелы, обычные пробелы, апострофы — это разделители тысяч.
    cleaned = s.replace("\u00A0", "").replace(" ", "").replace("'", "").replace("_", "")
    # Определяем десятичный разделитель: если есть и «.», и «,» — последний из них десятичный.
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "")
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        # decimal — чтобы не терять точность дробной части.
        from decimal import Decimal, InvalidOperation
        d = Decimal(cleaned)
    except Exception:
        return None
    sign = "минус " if d < 0 else ""
    d_abs = -d if d < 0 else d
    # Целая и дробная части как строки.
    int_part = int(d_abs)
    int_text = _ru_int_to_text(int_part)
    # Дробная часть.
    if "." in cleaned:
        frac_str = cleaned.split(".", 1)[1]
        # Обрезаем до 6 знаков и убираем хвостовые нули.
        frac_str = frac_str[:6].rstrip("0")
        if frac_str:
            frac_int = int(frac_str)
            frac_len = len(frac_str)
            frac_text = _ru_int_to_text(frac_int) if frac_int else "ноль"
            # Названия дробных разрядов (женский род для согласования).
            FRAC_NAMES = {
                1: ("десятая", "десятые", "десятых"),
                2: ("сотая", "сотые", "сотых"),
                3: ("тысячная", "тысячные", "тысячных"),
                4: ("десятитысячная", "десятитысячные", "десятитысячных"),
                5: ("стотысячная", "стотысячные", "стотысячных"),
                6: ("миллионная", "миллионные", "миллионных"),
            }
            unit = _ru_plural(frac_int, FRAC_NAMES[frac_len])
            int_word = _ru_plural(int_part, ("целая", "целые", "целых"))
            # Для целой части в этой форме согласование женское: «одна целая», «две целых».
            int_text_f = _ru_int_to_text_feminine_last(int_part) if int_part else "ноль"
            return _capitalize_first_letter(f"{sign}{int_text_f} {int_word} {frac_text} {unit}".strip())
    return _capitalize_first_letter((sign + int_text).strip())


def _ru_int_to_text_feminine_last(n: int) -> str:
    """То же, что _ru_int_to_text, но последняя единица читается в женском роде:
    «одна», «две». Нужно для конструкций «одна целая», «две целых»."""
    if n == 0:
        return "ноль"
    if n < 0:
        return "минус " + _ru_int_to_text_feminine_last(-n)
    # Берём базовый текст и переписываем хвост, если он 1 или 2 в последней триаде.
    last = n % 100
    base = _ru_int_to_text(n)
    if last % 10 == 1 and last != 11:
        if base.endswith(" один"):
            return base[: -len(" один")] + " одна"
        if base == "один":
            return "одна"
    if last % 10 == 2 and last != 12:
        if base.endswith(" два"):
            return base[: -len(" два")] + " две"
        if base == "два":
            return "две"
    return base


# ---------------------------------------------------------------------------
# Диалог «О программе»
# ---------------------------------------------------------------------------
class AboutDialog(QDialog):
    def __init__(self, app=None):
        super().__init__()
        self.app = app
        self.setWindowTitle(f"О программе — {PRODUCT_DISPLAY_NAME}")
        self.setMinimumWidth(660)
        self.setStyleSheet(DIALOG_QSS)
        try:
            p = app_styles.active_palette(getattr(app, "interface_theme", THEME_SYSTEM) if app else THEME_SYSTEM)
            _apply_native_titlebar(int(self.winId()), p.name == "dark", p.window_bg, p.text_primary)
        except Exception:
            pass

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel(f"<b>{PRODUCT_DISPLAY_NAME}</b>&nbsp;&nbsp;{PRODUCT_VERSION_LABEL}")
        title.setTextFormat(Qt.RichText)
        lay.addWidget(title)

        summary = QLabel(
            "NumLockCalc 2026 Free Core — лёгкий локальный калькулятор для Windows: "
            "быстрый вызов по NumLock, встроенный калькулятор, единицы измерения, "
            "история и аккуратная работа с буфером обмена."
        )
        summary.setWordWrap(True)
        lay.addWidget(summary)

        body = QLabel(
            "<b>Что внутри Free Core</b><br>"
            "• собственный встроенный калькулятор в стиле Win11;<br>"
            "• нормальный математический движок: приоритет операций, проценты, скобки;<br>"
            "• запуск и скрытие по NumLock без тяжёлого старта;<br>"
            "• история вычислений и копирование результата;<br>"
            "• меню единиц измерения, символов и строительных обозначений;<br>"
            "• число → текст и быстрые вставки через трей.<br><br>"
            "Сборка Free Core не содержит платных модулей, лицензий и фоновых Pro-функций. "
            "Это публичная версия для публикации и свободной установки."
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        lay.addWidget(body)

        links = QLabel(
            "Автор: <a href='https://akudlay.ru'>Андрей Кудлай</a><br>"
            "Telegram автора: <a href='https://t.me/AKudlay_ru'>@AKudlay_ru</a><br>"
            "Канал проекта: <a href='https://t.me/+2p1k8w4OiVowMGM6'>PM-Tools</a>"
        )
        links.setTextFormat(Qt.RichText)
        links.setOpenExternalLinks(True)
        links.setWordWrap(True)
        lay.addWidget(links)

        b = QPushButton("OK")
        b.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(b)
        lay.addLayout(row)

    def _copy_hw_code(self):
        if self.app is None:
            return
        self.app._copy_hardware_code()

    def _open_license_form(self):
        if self.app is None:
            return
        self.app._open_license_request_form()

    def _on_show_paid_toggled(self, checked: bool):
        if self.app is None:
            return
        self.app._set_paid_items_visible(bool(checked))


class HotkeyLineEdit(QLineEdit):
    def __init__(self, value: str = "", parent=None, default_value: str = ""):
        super().__init__(parent)
        self.default_value = default_value
        self.setText(value or default_value or "")
        self.setReadOnly(True)
        self.setPlaceholderText("Нажмите сочетание клавиш")
        self.setToolTip(
            "Кликните в поле и нажмите нужную клавишу или сочетание. "
            "Backspace/Delete очищают поле."
        )
        self.setCursor(Qt.PointingHandCursor)

    def mouseDoubleClickEvent(self, event):
        self.clear()
        event.accept()

    def keyPressEvent(self, event):
        key = event.key()

        if key in (Qt.Key_Backspace, Qt.Key_Delete):
            self.clear()
            event.accept()
            return

        if key == Qt.Key_Escape:
            self.clearFocus()
            event.accept()
            return

        base = self._key_name(event)
        # Не фиксируем одиночное нажатие модификатора: ждём основную клавишу.
        if not base:
            event.accept()
            return

        mods = []
        m = event.modifiers()
        if m & Qt.ControlModifier:
            mods.append("ctrl")
        if m & Qt.AltModifier:
            mods.append("alt")
        if m & Qt.ShiftModifier:
            mods.append("shift")
        if m & Qt.MetaModifier:
            mods.append("windows")

        # Если сама клавиша является модификатором, не дублируем её.
        if base in ("ctrl", "alt", "shift", "windows"):
            event.accept()
            return

        seen = []
        for part in mods + [base]:
            if part and part not in seen:
                seen.append(part)
        self.setText("+".join(seen))
        event.accept()

    def _key_name(self, event) -> str:
        key = event.key()
        manual = {
            Qt.Key_NumLock: "num lock",
            Qt.Key_Return: "enter",
            Qt.Key_Enter: "enter",
            Qt.Key_Escape: "esc",
            Qt.Key_Tab: "tab",
            Qt.Key_Space: "space",
            Qt.Key_Left: "left",
            Qt.Key_Right: "right",
            Qt.Key_Up: "up",
            Qt.Key_Down: "down",
            Qt.Key_Home: "home",
            Qt.Key_End: "end",
            Qt.Key_PageUp: "page up",
            Qt.Key_PageDown: "page down",
            Qt.Key_Insert: "insert",
            Qt.Key_Pause: "pause",
            Qt.Key_Print: "print screen",
            Qt.Key_CapsLock: "caps lock",
            Qt.Key_ScrollLock: "scroll lock",
            Qt.Key_Shift: "shift",
            Qt.Key_Control: "ctrl",
            Qt.Key_Alt: "alt",
            Qt.Key_Meta: "windows",
            Qt.Key_Super_L: "windows",
            Qt.Key_Super_R: "windows",
            Qt.Key_Menu: "menu",
        }
        if key in manual:
            return manual[key]
        if Qt.Key_F1 <= key <= Qt.Key_F35:
            return f"f{key - Qt.Key_F1 + 1}"
        if Qt.Key_0 <= key <= Qt.Key_9:
            return chr(ord('0') + key - Qt.Key_0)
        if Qt.Key_A <= key <= Qt.Key_Z:
            return chr(ord('a') + key - Qt.Key_A)

        txt = (event.text() or "").strip()
        if len(txt) == 1 and txt.isprintable():
            return txt.lower()

        name = QtGui.QKeySequence(key).toString(QtGui.QKeySequence.NativeText)
        if not name:
            name = QtGui.QKeySequence(key).toString()
        name = (name or "").strip().lower()
        replacements = {
            "numlock": "num lock",
            "num lock": "num lock",
            "pgup": "page up",
            "pgdown": "page down",
            "ins": "insert",
            "del": "delete",
            "return": "enter",
            "escape": "esc",
            "win": "windows",
            "meta": "windows",
        }
        return replacements.get(name, name)

# ---------------------------------------------------------------------------
# Синхронизация QSS после смены темы интерфейса.
# Из-за from styles import ... локальные имена нужно обновлять явно.
# ---------------------------------------------------------------------------
def _sync_style_globals_from_styles():
    global DIALOG_QSS, SETTINGS_QSS, MENU_QSS, SLIDER_QSS, NOTE_INPUT_QSS
    global TOOLBUTTON_QSS, RESET_BUTTON_QSS, MENU_CHECKBOX_QSS
    global LABEL_TITLE, LABEL_DESC, LABEL_DIM, LABEL_SEPARATOR, LABEL_NOTE, SECTION_HEADER_QSS, SECTION_HEADER_LABEL_QSS, TRANSPARENT_BG

    DIALOG_QSS = app_styles.DIALOG_QSS
    SETTINGS_QSS = app_styles.SETTINGS_QSS
    MENU_QSS = app_styles.MENU_QSS
    SLIDER_QSS = app_styles.SLIDER_QSS
    NOTE_INPUT_QSS = app_styles.NOTE_INPUT_QSS
    TOOLBUTTON_QSS = app_styles.TOOLBUTTON_QSS
    RESET_BUTTON_QSS = app_styles.RESET_BUTTON_QSS
    MENU_CHECKBOX_QSS = app_styles.MENU_CHECKBOX_QSS
    LABEL_TITLE = app_styles.LABEL_TITLE
    LABEL_DESC = app_styles.LABEL_DESC
    LABEL_DIM = app_styles.LABEL_DIM
    LABEL_SEPARATOR = app_styles.LABEL_SEPARATOR
    LABEL_NOTE = app_styles.LABEL_NOTE
    SECTION_HEADER_QSS = app_styles.SECTION_HEADER_QSS
    SECTION_HEADER_LABEL_QSS = app_styles.SECTION_HEADER_LABEL_QSS
    TRANSPARENT_BG = app_styles.TRANSPARENT_BG

    # Обновляем QSS-константы в базовых модулях, которые были импортированы раньше.
    # Иначе вкладки/диалоги из этих модулей остаются в старой теме, как привет из Win95.
    for _mod in (globals().get("extra"), globals().get("managed_windows")):
        if _mod is None:
            continue
        for _name in (
            "DIALOG_QSS", "SETTINGS_QSS", "MENU_QSS", "SLIDER_QSS",
            "NOTE_INPUT_QSS", "TOOLBUTTON_QSS", "RESET_BUTTON_QSS",
            "MENU_CHECKBOX_QSS", "SECTION_HEADER_QSS", "SECTION_HEADER_LABEL_QSS",
            "LABEL_TITLE", "LABEL_DESC", "LABEL_DIM", "LABEL_SEPARATOR",
            "LABEL_NOTE", "TRANSPARENT_BG",
        ):
            if hasattr(app_styles, _name):
                try:
                    setattr(_mod, _name, getattr(app_styles, _name))
                except Exception:
                    pass

    if EXTRA_AVAILABLE and extra is not None:
        for name in (
            "DIALOG_QSS", "LABEL_DIM", "MENU_QSS",
            "SECTION_HEADER_QSS", "SECTION_HEADER_LABEL_QSS",
        ):
            if hasattr(app_styles, name):
                try:
                    setattr(extra, name, getattr(app_styles, name))
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Общий диалог «Настройки» — все параметры программы в одном окне.
# Вкладки extra (Скриншоты, Трекер, Дневник) добавляются только при
# EXTRA_AVAILABLE через extra.build_*_tab(self, app).
# ---------------------------------------------------------------------------
class SettingsDialog(QDialog):

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(f"Настройки — {APP_NAME}")
        # Donor stable behavior: обычный модальный диалог без кеширования и
        # без ручного raise/show поверх других modal-popup. Так вкладка
        # «Общие» строится как нормальный QWidget, а не как stale C++ wrapper.
        self.resize(960, 760)
        self.setMinimumSize(900, 700)
        self.setStyleSheet(SETTINGS_QSS)
        try:
            p = app_styles.active_palette(getattr(app, "interface_theme", THEME_SYSTEM))
            _apply_native_titlebar(int(self.winId()), p.name == "dark", p.window_bg, p.text_primary)
        except Exception:
            pass

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(False)
        self.tabs.setElideMode(Qt.ElideNone)

        # Donor stable pattern: вкладки Free строятся прямо, без промежуточного
        # error-tab wrapper. Этот wrapper как раз маскировал реальную проблему
        # и оставлял вкладку «Общие» пустой.
        self.tabs.addTab(self._scroll_tab(self._build_general_tab()), "Общие")
        self.tabs.addTab(self._scroll_tab(self._build_units_tab()), "Единицы")

        license_active = bool(app._pro_license_active())
        pro_soft_ready = False
        extra_ready = False
        managed_ready = False
        if license_active:
            try:
                pro_soft_ready = bool(app._pro_soft_active() and app._ensure_pro_soft_loaded())
            except Exception as e:
                log(f"Settings: pro_soft readiness failed: {e}\n{traceback.format_exc()}")
            try:
                extra_ready = bool(app._pro_secure_active() and app._ensure_extra_loaded())
            except Exception as e:
                log(f"Settings: extra readiness failed: {e}\n{traceback.format_exc()}")
            try:
                managed_ready = bool(app._pro_secure_active() and app._ensure_managed_windows_loaded())
            except Exception as e:
                log(f"Settings: managed readiness failed: {e}\n{traceback.format_exc()}")

        if pro_soft_ready:
            self.tabs.addTab(self._scroll_tab(self._build_notes_tab()), "Заметки")
            self.tabs.addTab(self._build_programs_tab(), "Ярлыки")
        elif app._paid_items_visible() and not license_active:
            self.tabs.addTab(self._scroll_tab(self._locked_tab("Заметки")), "🔒 Заметки")
            self.tabs.addTab(self._scroll_tab(self._locked_tab("Ярлыки")), "🔒 Ярлыки")

        if extra_ready:
            try:
                self.tabs.addTab(self._scroll_tab(self._build_autoreplace_tab()), "Автозамена")
            except Exception as e:
                log(f"build_autoreplace_tab failed: {e}\n{traceback.format_exc()}")
            try:
                self.tabs.addTab(self._scroll_tab(extra.build_shots_tab(self, app)), "Скриншоты")
            except Exception as e:
                log(f"build_shots_tab failed: {e}\n{traceback.format_exc()}")
            try:
                self.tabs.addTab(self._scroll_tab(extra.build_tracker_tab(self, app)), "Трекер")
            except Exception as e:
                log(f"build_tracker_tab failed: {e}\n{traceback.format_exc()}")
            try:
                self.tabs.addTab(self._scroll_tab(extra.build_diary_tab(self, app)), "Дневник")
            except Exception as e:
                log(f"build_diary_tab failed: {e}\n{traceback.format_exc()}")
        elif app._paid_items_visible() and not license_active:
            self.tabs.addTab(self._scroll_tab(self._locked_tab("Автозамена")), "🔒 Автозамена")
            self.tabs.addTab(self._scroll_tab(self._locked_tab("Скриншоты")), "🔒 Скриншоты")
            self.tabs.addTab(self._scroll_tab(self._locked_tab("Трекер")), "🔒 Трекер")
            self.tabs.addTab(self._scroll_tab(self._locked_tab("Дневник")), "🔒 Дневник")

        if managed_ready:
            try:
                self.tabs.addTab(self._scroll_tab(managed_windows.build_settings_tab(self, app)), "Окна в трей")
            except Exception as e:
                log(f"managed_windows.build_settings_tab failed: {e}\n{traceback.format_exc()}")
        elif app._paid_items_visible() and not license_active:
            self.tabs.addTab(self._scroll_tab(self._locked_tab("Окна в трей")), "🔒 Окна в трей")

        root.addWidget(self.tabs)

        btn_row = QHBoxLayout()
        b_reset = QPushButton("Сбросить все настройки")
        b_reset.clicked.connect(self._on_reset_all)
        b_cancel = QPushButton("Отмена")
        b_cancel.clicked.connect(self.reject)
        b_apply = QPushButton("Применить")
        b_apply.clicked.connect(self._on_apply)
        b_ok = QPushButton("OK")
        b_ok.setDefault(True)
        b_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(b_reset)
        btn_row.addStretch()
        btn_row.addWidget(b_cancel)
        btn_row.addWidget(b_apply)
        btn_row.addWidget(b_ok)
        root.addLayout(btn_row)

    def _add_settings_tab(self, title: str, builder, *, scroll: bool = True) -> None:
        """Добавляет вкладку настроек без срыва всего диалога из-за одной вкладки.

        Ошибка ``wrapped C/C++ object ... has been deleted`` раньше роняла весь
        SettingsDialog. Теперь она попадает в debug.log с traceback, а диалог
        всё равно открывается с диагностической вкладкой.
        """
        try:
            widget = builder()
            if widget is None:
                raise RuntimeError(f"builder returned None for {title}")
            if scroll:
                widget = self._scroll_tab(widget)
            self.tabs.addTab(widget, title)
        except Exception as e:
            log(f"Settings tab build failed [{title}]: {e}\n{traceback.format_exc()}")
            try:
                self.tabs.addTab(self._settings_error_tab(title, e), f"⚠ {title}")
            except Exception as e2:
                log(f"Settings error tab build failed [{title}]: {e2}\n{traceback.format_exc()}")

    def _settings_error_tab(self, title: str, error: Exception) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(8)
        label = QLabel(f"Не удалось построить вкладку «{title}».")
        label.setWordWrap(True)
        lay.addWidget(label)
        detail = QLabel(str(error))
        detail.setWordWrap(True)
        detail.setStyleSheet(LABEL_DIM)
        lay.addWidget(detail)
        lay.addStretch()
        return w

    def _locked_tab(self, feature: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 24, 24, 24)
        label = QLabel(f"🔒 {feature} доступно в Pro-версии")
        label.setWordWrap(True)
        lay.addWidget(label)
        btn = QPushButton("Подробнее")
        btn.clicked.connect(lambda _=False, f=feature: self.app._show_pro_locked_popup(f))
        lay.addWidget(btn)
        lay.addStretch()
        return w

    def _scroll_tab(self, widget: QWidget) -> QWidget:
        """Оборачивает вкладку в вертикальную прокрутку, если она ещё не QScrollArea."""
        if isinstance(widget, QScrollArea):
            widget.setWidgetResizable(True)
            widget.setFrameShape(QFrame.NoFrame)
            return widget
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(widget)
        return scroll

    # ----- Вкладка «Общие» -----
    def _build_general_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        gbHK = QGroupBox("Горячая клавиша и приложение")
        f = QFormLayout(gbHK)
        f.setLabelAlignment(Qt.AlignRight)

        self.chk_numlock_enabled = QCheckBox("Горячая клавиша показывает / скрывает калькулятор")
        self.chk_numlock_enabled.setChecked(self.app.calc_hotkey_enabled)
        f.addRow(self.chk_numlock_enabled)


        self.le_main_hotkey = HotkeyLineEdit(self.app.main_hotkey, self, "num lock")
        self.le_main_hotkey.setMaximumWidth(220)
        f.addRow("Открыть / закрыть калькулятор:", self.le_main_hotkey)

        self.le_calc_pause_hotkey = HotkeyLineEdit(getattr(self.app, "calc_pause_hotkey", "shift+num lock"), self, "shift+num lock")
        self.le_calc_pause_hotkey.setMaximumWidth(220)
        f.addRow("Пауза обработки сочетанием:", self.le_calc_pause_hotkey)

        row_delay = QHBoxLayout()
        row_delay.setContentsMargins(0, 0, 0, 0)
        self.spn_main_delay = QDoubleSpinBox()
        self.spn_main_delay.setRange(0.0, 5.0)
        self.spn_main_delay.setDecimals(2)
        self.spn_main_delay.setSingleStep(0.05)
        self.spn_main_delay.setSuffix(" с")
        self.spn_main_delay.setValue(float(self.app.main_hotkey_delay_sec))
        b_delay_min = QPushButton("Минимум")
        b_delay_min.clicked.connect(lambda: self.spn_main_delay.setValue(0.05))
        b_delay_opt = QPushButton("Оптимум")
        b_delay_opt.clicked.connect(lambda: self.spn_main_delay.setValue(0.15))
        row_delay.addWidget(self.spn_main_delay)
        row_delay.addWidget(b_delay_min)
        row_delay.addWidget(b_delay_opt)
        row_delay.addStretch()
        row_delay_w = QWidget(); row_delay_w.setLayout(row_delay)
        f.addRow("Пауза между срабатываниями:", row_delay_w)

        self.cmb_calc_mode = QComboBox()
        self.cmb_calc_mode.addItem("Встроенный стандартный CalcNumLock", "builtin")
        self.cmb_calc_mode.addItem("Стандартный (calc.exe Windows)", "default")
        self.cmb_calc_mode.addItem("Свой exe" if self.app._pro_soft_active() else "🔒 Свой exe", "custom")
        _cmd = str(getattr(self.app, "calc_custom_cmd", "") or "")
        if _cmd == BUILTIN_CALC_CMD:
            self.cmb_calc_mode.setCurrentIndex(0)
        elif _cmd:
            self.cmb_calc_mode.setCurrentIndex(2)
        else:
            self.cmb_calc_mode.setCurrentIndex(1)
        self.cmb_calc_mode.currentIndexChanged.connect(self._on_calc_mode_changed)
        f.addRow("Запускать:", self.cmb_calc_mode)

        self.chk_calc_open_on_start = QCheckBox("Открывать калькулятор сразу при запуске NumLockCalcTray")
        self.chk_calc_open_on_start.setChecked(bool(getattr(self.app, "calc_open_on_start", False)))
        self.chk_calc_open_on_start.setToolTip("Для отдельного ярлыка можно также добавить аргумент --open-calc")
        f.addRow(self.chk_calc_open_on_start)

        self.chk_autostart = QCheckBox("Автозапуск при входе в Windows (ярлык в папке Startup)")
        self.chk_autostart.setChecked(bool(self.app._is_startup_enabled()))
        self.chk_autostart.setToolTip("Создаёт или удаляет .lnk-ярлык приложения в папке автозагрузки текущего пользователя.")
        f.addRow(self.chk_autostart)

        self.le_calc_exe = QLineEdit("" if self.app.calc_custom_cmd == BUILTIN_CALC_CMD else self.app.calc_custom_cmd)
        self.le_calc_exe.setPlaceholderText("Полный путь к exe")
        btn_pick = QPushButton("…")
        btn_pick.setFixedWidth(30)
        btn_pick.clicked.connect(self._pick_calc_exe)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.le_calc_exe, 1)
        row.addWidget(btn_pick)
        row_w = QWidget()
        row_w.setLayout(row)
        f.addRow("Путь к exe:", row_w)

        self.le_calc_args = QLineEdit(self.app.calc_custom_args)
        self.le_calc_args.setPlaceholderText("Необязательно")
        f.addRow("Аргументы:", self.le_calc_args)

        self._on_calc_mode_changed(self.cmb_calc_mode.currentIndex())
        if not self.app._pro_soft_active():
            self.le_calc_exe.setEnabled(False)
            self.le_calc_args.setEnabled(False)
            if not self.app._paid_items_visible():
                self.cmb_calc_mode.removeItem(2)
        lay.addWidget(gbHK)


        gbCopy = QGroupBox("Автокопирование результата")
        fc = QFormLayout(gbCopy)
        fc.setLabelAlignment(Qt.AlignRight)

        self.chk_auto_copy_on_enter = QCheckBox(
            "Автокопировать результат по Enter из активного окна калькулятора"
        )
        self.chk_auto_copy_on_enter.setChecked(bool(self.app.auto_copy_on_enter))
        fc.addRow(self.chk_auto_copy_on_enter)

        row_copy_delay = QHBoxLayout()
        row_copy_delay.setContentsMargins(0, 0, 0, 0)
        self.spn_auto_copy_delay_ms = QSpinBox()
        self.spn_auto_copy_delay_ms.setRange(0, 2000)
        self.spn_auto_copy_delay_ms.setSuffix(" мс")
        self.spn_auto_copy_delay_ms.setValue(int(self.app.auto_copy_enter_delay_ms))
        b_copy_min = QPushButton("Минимум")
        b_copy_min.clicked.connect(lambda: self.spn_auto_copy_delay_ms.setValue(50))
        b_copy_opt = QPushButton("Оптимум")
        b_copy_opt.clicked.connect(lambda: self.spn_auto_copy_delay_ms.setValue(120))
        row_copy_delay.addWidget(self.spn_auto_copy_delay_ms)
        row_copy_delay.addWidget(b_copy_min)
        row_copy_delay.addWidget(b_copy_opt)
        row_copy_delay.addStretch()
        row_copy_delay_w = QWidget(); row_copy_delay_w.setLayout(row_copy_delay)
        fc.addRow("Задержка после Enter:", row_copy_delay_w)

        self.chk_auto_copy_prefix = QCheckBox("Добавлять префикс" if self.app._pro_soft_active() else "🔒 Добавлять префикс")
        self.chk_auto_copy_prefix.setChecked(bool(self.app.auto_copy_prefix_enabled))
        fc.addRow(self.chk_auto_copy_prefix)
        self.le_auto_copy_prefix = QLineEdit(self.app.auto_copy_prefix)
        fc.addRow("Префикс:", self.le_auto_copy_prefix)

        self.chk_auto_copy_suffix = QCheckBox("Добавлять суффикс" if self.app._pro_soft_active() else "🔒 Добавлять суффикс")
        self.chk_auto_copy_suffix.setChecked(bool(self.app.auto_copy_suffix_enabled))
        fc.addRow(self.chk_auto_copy_suffix)
        self.le_auto_copy_suffix = QLineEdit(self.app.auto_copy_suffix)
        fc.addRow("Суффикс:", self.le_auto_copy_suffix)

        hint_copy = QLabel(
            "<span style='color:#888; font-size:11px;'>"
            "Логика: Enter → проверка активного окна калькулятора → Ctrl+C. "
            "Префикс/суффикс применяются уже к тексту, который калькулятор положил в буфер.</span>"
        )
        if not self.app._pro_soft_active():
            for _w in (self.chk_auto_copy_prefix, self.le_auto_copy_prefix, self.chk_auto_copy_suffix, self.le_auto_copy_suffix):
                _w.setEnabled(False)
            if not self.app._paid_items_visible():
                self.chk_auto_copy_prefix.hide(); self.le_auto_copy_prefix.hide()
                self.chk_auto_copy_suffix.hide(); self.le_auto_copy_suffix.hide()
        hint_copy.setWordWrap(True)
        fc.addRow(hint_copy)
        lay.addWidget(gbCopy)

        gbWin = QGroupBox("Окно приложения")
        fw = QFormLayout(gbWin)
        fw.setLabelAlignment(Qt.AlignRight)

        self.cmb_pos_mode = QComboBox()
        for label, mode in [
            ("По центру экрана", POS_CENTER),
            ("Правый нижний угол", POS_BOTTOM_RIGHT),
            ("Запомнить последнее место", POS_LAST),
        ]:
            self.cmb_pos_mode.addItem(label, mode)
            if mode == self.app.pos_mode:
                self.cmb_pos_mode.setCurrentIndex(self.cmb_pos_mode.count() - 1)
        fw.addRow("Позиция при открытии:", self.cmb_pos_mode)

        self.spn_opacity = QSpinBox()
        self.spn_opacity.setRange(0, 100)
        self.spn_opacity.setSuffix(" %")
        self.spn_opacity.setValue(self.app.opacity_pct)
        fw.addRow("Непрозрачность:", self.spn_opacity)

        # Способ скрытия
        self.rb_hide_keep  = QRadioButton("Скрывать (живёт в памяти, мгновенный показ)")
        self.rb_hide_close = QRadioButton("Закрывать (выгружается, при показе запуск заново)")
        if self.app.hide_mode == "close":
            self.rb_hide_close.setChecked(True)
        else:
            self.rb_hide_keep.setChecked(True)
        grp_hide = QButtonGroup(self)
        grp_hide.addButton(self.rb_hide_keep)
        grp_hide.addButton(self.rb_hide_close)
        hide_box = QVBoxLayout()
        hide_box.setContentsMargins(0, 0, 0, 0)
        hide_box.setSpacing(2)
        hide_box.addWidget(self.rb_hide_keep)
        hide_box.addWidget(self.rb_hide_close)
        hide_w = QWidget()
        hide_w.setLayout(hide_box)
        fw.addRow("Способ скрытия:", hide_w)

        lay.addWidget(gbWin)

        gbTheme = QGroupBox("Интерфейс")
        v_theme = QVBoxLayout(gbTheme)
        v_theme.setSpacing(3)
        self.rb_theme_system = QRadioButton("Как в системе")
        self.rb_theme_light = QRadioButton("Светлый")
        self.rb_theme_dark = QRadioButton("Тёмный")
        theme_mode = normalize_theme_mode(getattr(self.app, "interface_theme", THEME_SYSTEM))
        if theme_mode == THEME_LIGHT:
            self.rb_theme_light.setChecked(True)
        elif theme_mode == THEME_DARK:
            self.rb_theme_dark.setChecked(True)
        else:
            self.rb_theme_system.setChecked(True)
        self.grp_theme = QButtonGroup(gbTheme)
        self.grp_theme.addButton(self.rb_theme_system)
        self.grp_theme.addButton(self.rb_theme_light)
        self.grp_theme.addButton(self.rb_theme_dark)
        v_theme.addWidget(self.rb_theme_system)
        v_theme.addWidget(self.rb_theme_light)
        v_theme.addWidget(self.rb_theme_dark)

        self.chk_calc_group_digits = QCheckBox("Делить числа калькулятора на группы: 000 000 000")
        self.chk_calc_group_digits.setChecked(bool(getattr(self.app, "calc_group_digits", False)))
        self.chk_calc_group_digits.setToolTip("Показывать большие числа с пробелами между группами по 3 знака")
        v_theme.addWidget(self.chk_calc_group_digits)

        hint_theme = QLabel(
            "<span style='color:#888; font-size:11px;'>"
            "Режим применяется к меню трея, диалогу настроек и элементам CalcNumLock. "
            "В режиме «Как в системе» используется тема приложений Windows.</span>"
        )
        hint_theme.setWordWrap(True)
        v_theme.addWidget(hint_theme)
        lay.addWidget(gbTheme)


        gbHistory = QGroupBox("История вычислений")
        fh = QFormLayout(gbHistory)
        fh.setLabelAlignment(Qt.AlignRight)
        self.le_calc_history_path = QLineEdit(getattr(self.app, "calc_history_path", str(DEFAULT_CALC_HISTORY_FILE)))
        self.le_calc_history_path.setPlaceholderText("Файл истории вычислений")
        btn_hist_pick = QPushButton("…")
        btn_hist_pick.setFixedWidth(30)
        btn_hist_pick.clicked.connect(self._pick_calc_history_path)
        hist_row = QHBoxLayout()
        hist_row.setContentsMargins(0, 0, 0, 0)
        hist_row.addWidget(self.le_calc_history_path, 1)
        hist_row.addWidget(btn_hist_pick)
        hist_row_w = QWidget()
        hist_row_w.setLayout(hist_row)
        fh.addRow("Файл истории:", hist_row_w)
        lay.addWidget(gbHistory)

        lay.addStretch()
        return w




    def _pick_calc_history_path(self):
        current = self.le_calc_history_path.text().strip() or str(DEFAULT_CALC_HISTORY_FILE)
        start_dir = str(Path(current).parent if current else DATA_DIR)
        path, _ = QFileDialog.getSaveFileName(
            self, "Выберите файл истории вычислений",
            current or str(DEFAULT_CALC_HISTORY_FILE),
            "Текстовые файлы (*.txt *.md);;Все файлы (*)"
        )
        if path:
            self.le_calc_history_path.setText(path)

    def _on_calc_mode_changed(self, idx: int):
        mode = self.cmb_calc_mode.itemData(idx)
        custom = mode == "custom"
        self.le_calc_exe.setEnabled(custom)
        self.le_calc_args.setEnabled(custom)

    def _pick_calc_exe(self):
        start_dir = (str(Path(self.le_calc_exe.text()).parent)
                     if self.le_calc_exe.text() and
                     Path(self.le_calc_exe.text()).exists()
                     else str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите exe приложения",
            start_dir, "Исполняемые файлы (*.exe);;Все файлы (*)")
        if path:
            self.le_calc_exe.setText(path)

    # ----- Вкладка «Единицы» -----
    def _build_units_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        gb = QGroupBox("Поведение при клике по единице")
        v = QVBoxLayout(gb)

        self.rb_unit_append = QRadioButton("Дописать единицу к содержимому буфера")
        self.rb_unit_copy   = QRadioButton("Скопировать только единицу в буфер")
        if self.app.unit_mode == UNIT_MODE_APPEND:
            self.rb_unit_append.setChecked(True)
        else:
            self.rb_unit_copy.setChecked(True)
        grp = QButtonGroup(gb)
        grp.addButton(self.rb_unit_append)
        grp.addButton(self.rb_unit_copy)
        v.addWidget(self.rb_unit_append)
        v.addWidget(self.rb_unit_copy)

        v.addSpacing(6)
        self.chk_unit_paste = QCheckBox(
            "Вставлять в поле курсора (Ctrl+V в предыдущее активное окно)")
        self.chk_unit_paste.setChecked(self.app.unit_auto_paste)
        v.addWidget(self.chk_unit_paste)

        self.chk_unit_keep = QCheckBox(
            "Не закрывать меню по ПКМ/Shift+ЛКМ")
        self.chk_unit_keep.setChecked(self.app.unit_keep_menu_open)
        v.addWidget(self.chk_unit_keep)

        hint = QLabel(
            "<span style='color:#888; font-size:11px;'>"
            "При включённой галке: обычный ЛКМ закрывает меню как обычно, "
            "а ПКМ или Shift+ЛКМ выполняют команду и оставляют меню открытым — "
            "удобно копировать несколько единиц подряд. "
            "Если включена и «вставлять в поле курсора», "
            "при обычном ЛКМ автовставка срабатывает по предыдущему окну.</span>"
        )
        hint.setWordWrap(True)
        v.addWidget(hint)
        lay.addWidget(gb)

        gb2 = QGroupBox("Файл списка единиц")
        v2 = QVBoxLayout(gb2)
        lab = QLabel(f"Редактируется в файле <code>{UNITS_FILE.name}</code> "
                     "(формат: категория|метка|значение).")
        lab.setWordWrap(True)
        v2.addWidget(lab)
        row2 = QHBoxLayout()
        b1 = QPushButton("Открыть файл")
        b1.clicked.connect(lambda: self.app._open_units_file())
        b2 = QPushButton("Перечитать")
        b2.clicked.connect(lambda: self.app._reload_units_file())
        row2.addWidget(b1); row2.addWidget(b2); row2.addStretch()
        v2.addLayout(row2)
        lay.addWidget(gb2)

        lay.addStretch()
        return w

    # ----- Вкладка «Автозамена» -----
    def _build_autoreplace_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        gb = QGroupBox("Автозамена при вводе")
        v = QVBoxLayout(gb)
        v.setSpacing(8)

        self.chk_autoreplace_enabled = QCheckBox("Включить автозамену")
        self.chk_autoreplace_enabled.setChecked(bool(getattr(self.app, "autoreplace_enabled", True)))
        v.addWidget(self.chk_autoreplace_enabled)

        row_file = QHBoxLayout()
        self.le_autoreplace_file = QLineEdit(str(getattr(self.app, "autoreplace_file", "autoreplace.txt") or "autoreplace.txt"))
        row_file.addWidget(QLabel("Файл:"))
        row_file.addWidget(self.le_autoreplace_file, 1)
        b_open = QPushButton("Открыть")
        b_open.clicked.connect(lambda: self.app._open_autoreplace_file())
        b_reload = QPushButton("Перечитать")
        b_reload.clicked.connect(lambda: self.app._reload_autoreplace_rules())
        row_file.addWidget(b_open)
        row_file.addWidget(b_reload)
        v.addLayout(row_file)

        self.chk_autoreplace_trigger_instant = QCheckBox("Заменять сразу после набора триггера")
        self.chk_autoreplace_trigger_instant.setChecked(bool(getattr(self.app, "autoreplace_trigger_instant", True)))
        v.addWidget(self.chk_autoreplace_trigger_instant)

        self.chk_autoreplace_trigger_space = QCheckBox("Заменять по пробелу")
        self.chk_autoreplace_trigger_space.setChecked(bool(getattr(self.app, "autoreplace_trigger_space", True)))
        v.addWidget(self.chk_autoreplace_trigger_space)

        self.chk_autoreplace_trigger_enter = QCheckBox("Заменять по Enter")
        self.chk_autoreplace_trigger_enter.setChecked(bool(getattr(self.app, "autoreplace_trigger_enter", True)))
        v.addWidget(self.chk_autoreplace_trigger_enter)

        self.chk_autoreplace_trigger_tab = QCheckBox("Заменять по Tab")
        self.chk_autoreplace_trigger_tab.setChecked(bool(getattr(self.app, "autoreplace_trigger_tab", True)))
        v.addWidget(self.chk_autoreplace_trigger_tab)

        self.chk_autoreplace_block_after_backspace = QCheckBox("Не заменять сразу после Backspace")
        self.chk_autoreplace_block_after_backspace.setChecked(bool(getattr(self.app, "autoreplace_block_after_backspace", True)))
        v.addWidget(self.chk_autoreplace_block_after_backspace)

        self.chk_autoreplace_block_after_arrows = QCheckBox("Не заменять сразу после стрелок")
        self.chk_autoreplace_block_after_arrows.setChecked(bool(getattr(self.app, "autoreplace_block_after_arrows", True)))
        v.addWidget(self.chk_autoreplace_block_after_arrows)

        self.chk_autoreplace_physical_keys_mode = QCheckBox("Учитывать физическую раскладку клавиатуры")
        self.chk_autoreplace_physical_keys_mode.setChecked(bool(getattr(self.app, "autoreplace_physical_keys_mode", True)))
        v.addWidget(self.chk_autoreplace_physical_keys_mode)

        row_ex = QHBoxLayout()
        row_ex.addWidget(QLabel("Исключить exe:"))
        self.le_autoreplace_excluded_exes = QLineEdit(", ".join(getattr(self.app, "autoreplace_excluded_exes", []) or []))
        self.le_autoreplace_excluded_exes.setPlaceholderText("keepass.exe, bitwarden.exe")
        row_ex.addWidget(self.le_autoreplace_excluded_exes, 1)
        v.addLayout(row_ex)

        hint = QLabel("Правила берутся из autoreplace.txt в формате trigger|replacement. Эта вкладка доступна только при license.txt.")
        hint.setWordWrap(True)
        hint.setStyleSheet(LABEL_DIM)
        v.addWidget(hint)

        lay.addWidget(gb)
        lay.addStretch()
        return w

    # ----- Вкладка «Заметки» (включая popup-настройки, ТЗ §7) -----
    def _build_notes_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # --- Файл заметок ---
        gb = QGroupBox("Файл быстрых заметок")
        f = QFormLayout(gb)
        f.setLabelAlignment(Qt.AlignRight)

        self.le_notes_path = QLineEdit(self.app.notes_path)
        btn_notes_file = QPushButton("Файл")
        btn_notes_file.setFixedWidth(60)
        btn_notes_file.clicked.connect(self._pick_notes_path)
        btn_notes_dir = QPushButton("Папка")
        btn_notes_dir.setFixedWidth(60)
        btn_notes_dir.clicked.connect(self._pick_notes_folder)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.le_notes_path, 1)
        row.addWidget(btn_notes_file)
        row.addWidget(btn_notes_dir)
        row_w = QWidget(); row_w.setLayout(row)
        f.addRow("Путь:", row_w)

        self.cmb_notes_fmt = QComboBox()
        for label, fmt in [("Markdown (.md)", NOTE_FMT_MD),
                           ("Text (.txt)",    NOTE_FMT_TXT),
                           ("Rich Text (.rtf)", NOTE_FMT_RTF)]:
            self.cmb_notes_fmt.addItem(label, fmt)
            if fmt == self.app.notes_format:
                self.cmb_notes_fmt.setCurrentIndex(self.cmb_notes_fmt.count() - 1)
        f.addRow("Формат:", self.cmb_notes_fmt)
        lay.addWidget(gb)

        # --- Формат записи ---
        gb2 = QGroupBox("Формат записи")
        f2 = QFormLayout(gb2)
        f2.setLabelAlignment(Qt.AlignRight)
        self.le_notes_sep = QLineEdit(self.app.notes_separator)
        self.le_notes_sep.setMaxLength(10)
        f2.addRow("Разделитель между датой и текстом:", self.le_notes_sep)

        self.chk_notes_newline_before = QCheckBox("Начинать новую заметку с новой строки")
        self.chk_notes_newline_before.setChecked(bool(self.app.notes_newline_before))
        f2.addRow(self.chk_notes_newline_before)

        hint = QLabel(
            "<span style='color:#888; font-size:11px;'>"
            "Для Markdown каждая заметка — отдельный пункт списка. "
            "Для Text — отдельная строка. Для RTF — отдельная строка "
            "перед закрывающей скобкой файла.</span>")
        hint.setWordWrap(True)
        f2.addRow(hint)
        lay.addWidget(gb2)

        row_btn = QHBoxLayout()
        b_open = QPushButton("Открыть файл заметок")
        b_open.clicked.connect(lambda: self.app._open_notes_file())
        b_folder = QPushButton("Открыть папку")
        b_folder.clicked.connect(lambda: self.app._open_notes_folder())
        row_btn.addWidget(b_open); row_btn.addWidget(b_folder); row_btn.addStretch()
        lay.addLayout(row_btn)

        # --- Popup-заметка по горячей клавише (ТЗ §7 — перенесено сюда) ---
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(LABEL_SEPARATOR)
        lay.addWidget(sep)

        gb3 = QGroupBox("Popup-окно заметки по горячей клавише")
        v3 = QVBoxLayout(gb3)

        self.chk_note_popup_enabled = QCheckBox("Окно быстрой заметки по горячей клавише")
        self.chk_note_popup_enabled.setChecked(bool(self.app.note_popup_enabled))
        v3.addWidget(self.chk_note_popup_enabled)

        hk_row = QHBoxLayout()
        hk_row.addWidget(QLabel("Горячая клавиша:"))
        self.le_note_popup_hotkey = HotkeyLineEdit(self.app.note_popup_hotkey or "ctrl+shift+n", self, "ctrl+shift+n")
        self.le_note_popup_hotkey.setMaximumWidth(220)
        hk_row.addWidget(self.le_note_popup_hotkey)
        hk_row.addWidget(QLabel("Кликните в поле и нажмите сочетание"))
        hk_row.addStretch()
        v3.addLayout(hk_row)

        sb_row = QHBoxLayout()
        sb_row.addWidget(QLabel("Сохранение по:"))
        self.cmb_note_popup_submit = QComboBox()
        self.cmb_note_popup_submit.addItem("Enter (Shift+Enter — перенос строки)", "enter")
        self.cmb_note_popup_submit.addItem("Ctrl+Enter (Enter — перенос строки)", "ctrl+enter")
        idx = 1 if self.app.note_popup_submit == "ctrl+enter" else 0
        self.cmb_note_popup_submit.setCurrentIndex(idx)
        sb_row.addWidget(self.cmb_note_popup_submit)
        sb_row.addStretch()
        v3.addLayout(sb_row)

        lay.addWidget(gb3)

        lay.addStretch()
        return w

    def _pick_notes_path(self):
        start = self.le_notes_path.text() or str(DEFAULT_NOTES_FILE)
        path, _ = QFileDialog.getSaveFileName(
            self, "Файл заметок", start,
            "Markdown (*.md);;Text (*.txt);;Rich Text (*.rtf);;Все файлы (*)")
        if path:
            self.le_notes_path.setText(path)
            ext = Path(path).suffix.lower().lstrip(".")
            if ext in (NOTE_FMT_MD, NOTE_FMT_TXT, NOTE_FMT_RTF):
                for i in range(self.cmb_notes_fmt.count()):
                    if self.cmb_notes_fmt.itemData(i) == ext:
                        self.cmb_notes_fmt.setCurrentIndex(i)
                        break
            self._sync_paths_tab()

    def _pick_notes_folder(self):
        start = (str(Path(self.le_notes_path.text()).parent)
                 if self.le_notes_path.text()
                 else str(DEFAULT_NOTES_FILE.parent))
        folder = QFileDialog.getExistingDirectory(self, "Папка для заметок", start)
        if folder:
            cur_name = Path(self.le_notes_path.text()).name or f"notes.{self.app.notes_format}"
            new_path = str(Path(folder) / cur_name)
            self.le_notes_path.setText(new_path)
            self._sync_paths_tab()


    # ----- Вкладка «Программы» -----
    def _build_programs_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        info = QLabel(
            "Назначенные программы показываются в меню трея рядом с калькулятором. "
            "Для каждой программы можно указать exe/lnk, иконку, параметры запуска, "
            "хоткей, автозапуск и подсказку Win+номер для закрепления на панели задач."
        )
        info.setWordWrap(True)
        info.setStyleSheet(LABEL_DIM)
        lay.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.launcher_rows_lay = QVBoxLayout(body)
        self.launcher_rows_lay.setContentsMargins(0, 0, 0, 0)
        self.launcher_rows_lay.setSpacing(10)
        self.launcher_rows = []

        apps = list(getattr(self.app, "launcher_apps", []) or [])
        if not apps:
            apps = []
        for item in apps:
            self._add_launcher_row(item)

        self.launcher_rows_lay.addStretch()
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        row = QHBoxLayout()
        b_add = QPushButton("+ Добавить программу")
        b_add.clicked.connect(lambda: self._add_launcher_row({}))
        row.addWidget(b_add)
        row.addStretch()
        lay.addLayout(row)
        return w

    def _add_launcher_row(self, item: dict):
        gb = QGroupBox(item.get("title") or "Программа")
        f = QFormLayout(gb)
        f.setLabelAlignment(Qt.AlignRight)

        chk_enabled = QCheckBox("Включена")
        chk_enabled.setChecked(bool(item.get("enabled", True)))
        f.addRow(chk_enabled)

        le_title = QLineEdit(str(item.get("title", "") or ""))
        f.addRow("Название:", le_title)

        le_path = QLineEdit(str(item.get("path", "") or ""))
        b_exe = QPushButton("EXE…")
        row_path = QHBoxLayout(); row_path.setContentsMargins(0, 0, 0, 0)
        row_path.addWidget(le_path, 1); row_path.addWidget(b_exe)
        row_path_w = QWidget(); row_path_w.setLayout(row_path)
        f.addRow("Файл программы:", row_path_w)

        le_icon = QLineEdit(str(item.get("custom_icon_path", "") or ""))
        b_icon = QPushButton("Иконка…")
        b_from_exe = QPushButton("Из EXE")
        b_reset = QPushButton("Сброс")
        row_icon = QHBoxLayout(); row_icon.setContentsMargins(0, 0, 0, 0)
        row_icon.addWidget(le_icon, 1); row_icon.addWidget(b_icon); row_icon.addWidget(b_from_exe); row_icon.addWidget(b_reset)
        row_icon_w = QWidget(); row_icon_w.setLayout(row_icon)
        f.addRow("Иконка:", row_icon_w)

        le_args = QLineEdit(str(item.get("args", "") or ""))
        f.addRow("Параметры запуска:", le_args)

        le_hotkey = QLineEdit(str(item.get("hotkey", "") or ""))
        le_hotkey.setPlaceholderText("ctrl+alt+o")
        f.addRow("Горячая клавиша:", le_hotkey)

        chk_show = QCheckBox("Показывать в меню трея")
        chk_show.setChecked(bool(item.get("show_in_tray", True)))
        f.addRow(chk_show)

        chk_start = QCheckBox("Открывать вместе с NumLockCalcTray")
        chk_start.setChecked(bool(item.get("open_on_start", False)))
        f.addRow(chk_start)

        chk_taskbar = QCheckBox("Закреплена в панели задач")
        chk_taskbar.setChecked(bool(item.get("taskbar_pinned", False)))
        f.addRow(chk_taskbar)

        spn_taskbar = QSpinBox()
        spn_taskbar.setRange(1, 9)
        try:
            _taskbar_index = int(item.get("taskbar_index", 1) or 1)
        except Exception:
            _taskbar_index = 1
        spn_taskbar.setValue(max(1, min(9, _taskbar_index)))
        lbl_hint = QLabel("")
        lbl_hint.setStyleSheet(LABEL_DIM)
        row_tb = QHBoxLayout(); row_tb.setContentsMargins(0, 0, 0, 0)
        row_tb.addWidget(spn_taskbar)
        row_tb.addWidget(lbl_hint)
        row_tb.addStretch()
        row_tb_w = QWidget(); row_tb_w.setLayout(row_tb)
        f.addRow("Номер на панели задач:", row_tb_w)

        b_delete = QPushButton("Удалить")
        f.addRow(b_delete)

        row = {
            "box": gb,
            "enabled": chk_enabled,
            "title": le_title,
            "path": le_path,
            "icon": le_icon,
            "args": le_args,
            "hotkey": le_hotkey,
            "show_in_tray": chk_show,
            "open_on_start": chk_start,
            "taskbar_pinned": chk_taskbar,
            "taskbar_index": spn_taskbar,
            "hint": lbl_hint,
        }

        def _refresh_hint():
            if chk_taskbar.isChecked():
                lbl_hint.setText(f"Подсказка: Win+{spn_taskbar.value()}")
            elif le_hotkey.text().strip():
                lbl_hint.setText(f"Подсказка: {le_hotkey.text().strip()}")
            else:
                lbl_hint.setText("Подсказка: —")

        def _pick_exe():
            start = str(Path(le_path.text()).parent) if le_path.text() else str(Path.home())
            path, _ = QFileDialog.getOpenFileName(
                self, "Выберите программу", start,
                "Программы (*.exe *.lnk *.bat *.cmd *.ps1);;Все файлы (*)"
            )
            if path:
                le_path.setText(path)
                if not le_title.text().strip():
                    le_title.setText(Path(path).stem)
                gb.setTitle(le_title.text().strip() or Path(path).stem)
                if not le_icon.text().strip():
                    le_icon.setPlaceholderText("Иконка будет взята из EXE/ярлыка")

        def _pick_icon():
            start = str(Path(le_icon.text()).parent) if le_icon.text() else str(Path.home())
            path, _ = QFileDialog.getOpenFileName(
                self, "Выберите иконку", start,
                "Иконки (*.ico *.png *.jpg *.jpeg *.bmp);;Все файлы (*)"
            )
            if path:
                le_icon.setText(path)

        b_exe.clicked.connect(_pick_exe)
        b_icon.clicked.connect(_pick_icon)
        b_from_exe.clicked.connect(lambda: le_icon.clear())
        b_reset.clicked.connect(lambda: le_icon.clear())
        chk_taskbar.toggled.connect(lambda _: _refresh_hint())
        spn_taskbar.valueChanged.connect(lambda _: _refresh_hint())
        le_hotkey.textChanged.connect(lambda _: _refresh_hint())
        le_title.textChanged.connect(lambda t: gb.setTitle(t.strip() or "Программа"))

        def _delete():
            self.launcher_rows.remove(row)
            gb.setParent(None)
            gb.deleteLater()
        b_delete.clicked.connect(_delete)

        self.launcher_rows.append(row)
        # Вставляем перед stretch, если он уже есть.
        idx = max(0, self.launcher_rows_lay.count() - 1)
        self.launcher_rows_lay.insertWidget(idx, gb)
        _refresh_hint()

    def _collect_launcher_apps(self) -> list:
        result = []
        seen_hotkeys = set()
        for row in getattr(self, "launcher_rows", []):
            path = row["path"].text().strip()
            title = row["title"].text().strip() or (Path(path).stem if path else "")
            hotkey = row["hotkey"].text().strip().lower()
            if hotkey:
                if hotkey in seen_hotkeys:
                    QMessageBox.warning(self, APP_NAME, f"Дублируется хоткей: {hotkey}")
                    continue
                seen_hotkeys.add(hotkey)
            if not path and not title and not hotkey:
                continue
            result.append({
                "enabled": bool(row["enabled"].isChecked()),
                "title": title or "Программа",
                "path": path,
                "args": row["args"].text().strip(),
                "custom_icon_path": row["icon"].text().strip(),
                "hotkey": hotkey,
                "show_in_tray": bool(row["show_in_tray"].isChecked()),
                "open_on_start": bool(row["open_on_start"].isChecked()),
                "taskbar_pinned": bool(row["taskbar_pinned"].isChecked()),
                "taskbar_index": int(row["taskbar_index"].value()),
            })
        return result

    def _sync_paths_tab(self):
        """Stub: вкладка «Пути» удалена. Метод оставлен пустым, чтобы не ломать
        существующие вызовы из других мест диалога настроек."""
        return

    def _open_target(self, path: Path, kind: str):
        try:
            p = Path(path)
            if kind == "folder" or (not p.exists() and not p.suffix):
                p.mkdir(parents=True, exist_ok=True)
                os.startfile(str(p))
            else:
                if kind == "file" and not p.exists():
                    p.parent.mkdir(parents=True, exist_ok=True)
                    os.startfile(str(p.parent))
                    return
                if kind == "folder":
                    os.startfile(str(p))
                else:
                    os.startfile(str(p.parent))
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"Не удалось открыть: {e}")

    # ----- Кнопки диалога -----
    def _on_reset_all(self):
        ans = QMessageBox.question(
            self, APP_NAME,
            "Сбросить все настройки к значениям по умолчанию?\n"
            "Это не удалит данные трекера, категории, "
            "список единиц, заметки и скриншоты.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if ans == QMessageBox.Yes:
            self.app._reset_settings()
            self.accept()

    def _apply_settings(self, close: bool = False):
        a = self.app
        if not hasattr(self, "chk_numlock_enabled"):
            log("Settings apply skipped: General tab controls are absent")
            if close:
                self.accept()
            return
        # --- Общие ---
        a.calc_hotkey_enabled = self.chk_numlock_enabled.isChecked()
        a.main_hotkey = self.le_main_hotkey.text().strip().lower() or "num lock"
        a.calc_pause_hotkey = self.le_calc_pause_hotkey.text().strip().lower() or "shift+num lock"
        a.main_hotkey_delay_sec = float(self.spn_main_delay.value())
        a.calc_open_on_start = bool(self.chk_calc_open_on_start.isChecked())
        if hasattr(self, "chk_autostart"):
            wanted_autostart = bool(self.chk_autostart.isChecked())
            if wanted_autostart != bool(a._is_startup_enabled()):
                if not a._set_startup_enabled(wanted_autostart):
                    self.chk_autostart.blockSignals(True)
                    self.chk_autostart.setChecked(bool(a._is_startup_enabled()))
                    self.chk_autostart.blockSignals(False)
                    QMessageBox.warning(self, APP_NAME, "Не удалось изменить автозапуск. См. debug.log.")
            a.autostart_enabled = bool(a._is_startup_enabled())
        a.auto_copy_on_enter = bool(self.chk_auto_copy_on_enter.isChecked())
        a.auto_copy_enter_delay_ms = int(self.spn_auto_copy_delay_ms.value())
        if hasattr(self, "cmb_calc_clipboard_mode"):
            selected_clipboard_mode = self.cmb_calc_clipboard_mode.currentData() or CALC_CLIPBOARD_RESULT
        else:
            selected_clipboard_mode = getattr(a, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT) or CALC_CLIPBOARD_RESULT
        if not a.auto_copy_on_enter:
            selected_clipboard_mode = CALC_CLIPBOARD_OFF
        if selected_clipboard_mode == CALC_CLIPBOARD_MONEY_TEXT and not a._pro_soft_active():
            a._show_pro_locked_popup("Сумма текстом")
            selected_clipboard_mode = CALC_CLIPBOARD_RESULT
        a.calc_clipboard_mode = _normalize_calc_clipboard_mode(
            selected_clipboard_mode,
            allow_money_text=a._pro_soft_active(),
        )
        a.auto_copy_on_enter = a.calc_clipboard_mode != CALC_CLIPBOARD_OFF
        a.auto_copy_mode = a.calc_clipboard_mode
        if a._pro_soft_active():
            if hasattr(self, "chk_money_text_parentheses"):
                a.money_text_parentheses = bool(self.chk_money_text_parentheses.isChecked())
            if hasattr(self, "cmb_money_text_kopecks"):
                a.money_text_kopecks_mode = self.cmb_money_text_kopecks.currentData() or "digits"
            a.amount_text_parentheses = a.money_text_parentheses
            a.amount_text_kopecks_mode = a.money_text_kopecks_mode
            a.money_text_format = "number_parentheses" if a.money_text_parentheses else "number_plain"
            a.money_text_kopecks = a.money_text_kopecks_mode
            a.auto_copy_prefix_enabled = bool(self.chk_auto_copy_prefix.isChecked())
            a.auto_copy_prefix = self.le_auto_copy_prefix.text()
            a.auto_copy_suffix_enabled = bool(self.chk_auto_copy_suffix.isChecked())
            a.auto_copy_suffix = self.le_auto_copy_suffix.text()
        else:
            a.money_text_parentheses = True
            a.money_text_kopecks_mode = "digits"
            a.amount_text_parentheses = True
            a.amount_text_kopecks_mode = "digits"
            a.money_text_format = "number_parentheses"
            a.money_text_kopecks = "digits"
            a.auto_copy_prefix_enabled = False
            a.auto_copy_prefix = ""
            a.auto_copy_suffix_enabled = False
            a.auto_copy_suffix = ""
        a.calc_history_path = self.le_calc_history_path.text().strip() or str(DEFAULT_CALC_HISTORY_FILE)
        a.calc_group_digits = bool(self.chk_calc_group_digits.isChecked())
        try:
            if getattr(a, "_builtin_calc_window", None) is not None:
                a._builtin_calc_window.set_history_path(a.calc_history_path)
                if hasattr(a._builtin_calc_window, "set_group_digits"):
                    a._builtin_calc_window.set_group_digits(a.calc_group_digits, notify=False)
                if hasattr(a._builtin_calc_window, "set_clipboard_mode"):
                    a._builtin_calc_window.set_clipboard_mode(a.calc_clipboard_mode, notify=False)
                if hasattr(a._builtin_calc_window, "set_money_text_formatter"):
                    a._builtin_calc_window.set_money_text_formatter(
                        formatter=a._format_money_text_for_copy,
                        allow_money_text=a._pro_soft_active(),
                    )
        except Exception:
            pass
        if hasattr(a, "act_calc_hotkey_enabled"):
            a.act_calc_hotkey_enabled.setChecked(a.calc_hotkey_enabled)
        mode = self.cmb_calc_mode.currentData()
        if mode == "builtin":
            a.calc_custom_cmd = BUILTIN_CALC_CMD
            a.calc_custom_args = ""
        elif mode == "custom" and a._pro_soft_active():
            a.calc_custom_cmd  = self.le_calc_exe.text().strip()
            a.calc_custom_args = self.le_calc_args.text().strip()
        elif mode == "custom":
            a.calc_custom_cmd = BUILTIN_CALC_CMD
            a.calc_custom_args = ""
            a._show_pro_locked_popup("Свой exe")
        else:
            a.calc_custom_cmd  = ""
            a.calc_custom_args = ""
        a.pos_mode = self.cmb_pos_mode.currentData()
        if a.pos_mode != POS_LAST:
            a.session_pos = None
        new_op = int(self.spn_opacity.value())
        if new_op != a.opacity_pct:
            a.opacity_pct = new_op
            if hasattr(a, "sld_opacity"):
                a.sld_opacity.setValue(new_op)
            hwnd = a._find_target_hwnd()
            if hwnd:
                apply_opacity(hwnd, new_op)
        a.hide_mode = "close" if self.rb_hide_close.isChecked() else "hide"

        old_interface_theme = normalize_theme_mode(getattr(a, "interface_theme", THEME_SYSTEM))
        if self.rb_theme_light.isChecked():
            a.interface_theme = THEME_LIGHT
        elif self.rb_theme_dark.isChecked():
            a.interface_theme = THEME_DARK
        else:
            a.interface_theme = THEME_SYSTEM
        if normalize_theme_mode(a.interface_theme) != old_interface_theme:
            a._apply_interface_theme(rebuild=False)
            self.setStyleSheet(SETTINGS_QSS)
            try:
                for _tbl in self.findChildren(QTableWidget):
                    _tbl.setStyleSheet(SETTINGS_QSS)
                for _scroll in self.findChildren(QScrollArea):
                    _scroll.setStyleSheet(SETTINGS_QSS)
            except Exception:
                pass
            try:
                p = app_styles.active_palette(getattr(a, "interface_theme", THEME_SYSTEM))
                _apply_native_titlebar(int(self.winId()), p.name == "dark", p.window_bg, p.text_primary)
            except Exception:
                pass

        # --- Единицы ---
        a.unit_mode = UNIT_MODE_APPEND if self.rb_unit_append.isChecked() else UNIT_MODE_COPY
        a.unit_auto_paste     = self.chk_unit_paste.isChecked()
        a.unit_keep_menu_open = self.chk_unit_keep.isChecked()

        if a._pro_soft_active() and hasattr(self, "le_notes_path"):
            a.notes_path = self.le_notes_path.text().strip() or str(DEFAULT_NOTES_FILE)
            a.notes_format = self.cmb_notes_fmt.currentData() or NOTE_FMT_MD
            sep = self.le_notes_sep.text()
            a.notes_separator = sep if sep else " — "
            a.notes_newline_before = self.chk_notes_newline_before.isChecked()
            old_hotkey = a.note_popup_hotkey
            old_enabled = a.note_popup_enabled
            a.note_popup_enabled = self.chk_note_popup_enabled.isChecked()
            a.note_popup_hotkey = self.le_note_popup_hotkey.text().strip().lower() or "ctrl+shift+n"
            a.note_popup_submit = self.cmb_note_popup_submit.currentData() or "enter"
            if old_hotkey != a.note_popup_hotkey or old_enabled != a.note_popup_enabled:
                try:
                    a._register_note_popup_hotkey()
                except Exception:
                    pass
        if a._pro_soft_active() and hasattr(self, "launcher_rows"):
            a.launcher_apps = self._collect_launcher_apps()
        elif not a._pro_soft_active():
            a.launcher_apps = []
        try:
            a._register_calc_hotkeys()
        except Exception as e:
            log(f"register calc hotkeys after settings failed: {e}")
        try:
            a._register_launcher_hotkeys()
        except Exception as e:
            log(f"register launcher hotkeys after settings failed: {e}")
        if a._pro_secure_active() and hasattr(self, "chk_autoreplace_enabled"):
            try:
                a.autoreplace_enabled = bool(self.chk_autoreplace_enabled.isChecked())
                a.autoreplace_file = self.le_autoreplace_file.text().strip() or "autoreplace.txt"
                a.autoreplace_trigger_instant = bool(self.chk_autoreplace_trigger_instant.isChecked())
                a.autoreplace_trigger_space = bool(self.chk_autoreplace_trigger_space.isChecked())
                a.autoreplace_trigger_enter = bool(self.chk_autoreplace_trigger_enter.isChecked())
                a.autoreplace_trigger_tab = bool(self.chk_autoreplace_trigger_tab.isChecked())
                a.autoreplace_block_after_backspace = bool(self.chk_autoreplace_block_after_backspace.isChecked())
                a.autoreplace_block_after_arrows = bool(self.chk_autoreplace_block_after_arrows.isChecked())
                a.autoreplace_physical_keys_mode = bool(self.chk_autoreplace_physical_keys_mode.isChecked())
                raw_exes = self.le_autoreplace_excluded_exes.text().replace(";", ",").replace("\n", ",")
                a.autoreplace_excluded_exes = [x.strip().lower() for x in raw_exes.split(",") if x.strip()]
                if a._ensure_pro_secure_loaded():
                    pro_secure.save_autoreplace_settings(a)
                    pro_secure.load_autoreplace_rules(a)
            except Exception as e:
                log(f"autoreplace settings apply failed: {e}\n{traceback.format_exc()}")

        try:
            a._register_keyboard_hook(reason="settings")
        except Exception as e:
            log(f"register keyboard hook after settings failed: {e}")

        # --- Extra-вкладки (Скриншоты/Трекер/Дневник) — отдаём в extra ---
        if a._pro_secure_active() and EXTRA_AVAILABLE:
            try:
                extra.apply_settings_dialog(self, a)
            except Exception as e:
                log(f"extra.apply_settings_dialog failed: {e}")
        if a._pro_secure_active() and MANAGED_WINDOWS_AVAILABLE:
            try:
                managed_windows.apply_settings_dialog(self, a)
            except Exception as e:
                log(f"managed_windows.apply_settings_dialog failed: {e}")

        # Сохраняем + применяем производные вещи
        a._save_settings()
        if a._pro_soft_active() and a._ensure_pro_soft_loaded():
            try:
                pro_soft.save_settings(a)
            except Exception as e:
                log(f"pro_soft.save_settings failed: {e}")
        if a._pro_secure_active() and EXTRA_AVAILABLE:
            try:
                extra.save_settings(a)
            except Exception as e:
                log(f"extra.save_settings failed: {e}")
            try:
                a.screenshots_apply_timer()
            except Exception:
                pass
        if a._pro_secure_active() and MANAGED_WINDOWS_AVAILABLE:
            try:
                managed_windows.save_settings(a)
            except Exception as e:
                log(f"managed_windows.save_settings failed: {e}")
            try:
                if getattr(a, "tray_window_manager", None) is not None:
                    a.tray_window_manager.reload_settings()
            except Exception as e:
                log(f"managed_windows reload settings failed: {e}")
        try:
            a._rebuild_units_menu()
        except Exception:
            pass
        if a._pro_soft_active():
            try:
                a._refresh_notes_label()
            except Exception:
                pass
        try:
            a._rebuild_tray_ui()
        except Exception as e:
            log(f"rebuild tray after settings failed: {e}")
        log("Settings saved via SettingsDialog")
        if close:
            self.accept()



    def _on_apply(self):
        self._apply_settings(close=False)

    def _on_ok(self):
        self._apply_settings(close=True)

# ---------------------------------------------------------------------------
# Главный класс приложения
# ---------------------------------------------------------------------------
class CalcTrayApp(QWidget):

    _sig_toggle = QtCore.pyqtSignal()
    _sig_note_popup_show = QtCore.pyqtSignal()
    # Автокопирование вызывается из keyboard-hook потока.
    # QTimer.singleShot из чужого потока не обязан сработать, поэтому
    # сначала перекидываем запрос в главный Qt-поток через сигнал.
    _sig_auto_copy_request = QtCore.pyqtSignal(int, int)
    _sig_calc_pause_toggle = QtCore.pyqtSignal()
    _sig_autoreplace_request = QtCore.pyqtSignal(int, str, str)

    def __init__(self):
        super().__init__()
        self._startup_mark("CalcTrayApp.__init__: begin")

        # Калькулятор
        self.opacity_pct  = 100
        self.pos_mode     = POS_CENTER
        self.session_pos  = None
        self.running      = True
        self.calc_hotkey_enabled = True
        self.main_hotkey = "num lock"
        self.calc_pause_hotkey = "shift+num lock"
        self.main_hotkey_delay_sec = 0.15
        self.auto_copy_on_enter = False
        self.auto_copy_enter_delay_ms = 120
        self.auto_copy_prefix_enabled = False
        self.auto_copy_prefix = ""
        self.auto_copy_suffix_enabled = False
        self.auto_copy_suffix = ""
        self.calc_clipboard_mode = CALC_CLIPBOARD_RESULT
        self.auto_copy_mode = self.calc_clipboard_mode
        self.paid_hide_until = ""
        self.paid_hide_count = 0
        self.paid_hide_permanent = False
        self.money_text_parentheses = True
        self.money_text_kopecks_mode = "digits"
        self.amount_text_parentheses = True
        self.amount_text_kopecks_mode = "digits"
        self.launcher_apps = []
        self._last_toggle = 0.0
        self._wait_n      = 0
        self._builtin_calc_window = None

        # Единицы измерения
        self.unit_mode = UNIT_MODE_APPEND
        self.unit_auto_paste = False
        self.unit_keep_menu_open = True
        self.units_by_category = {}

        # Сторонний exe по NumLock
        self.calc_custom_cmd  = ""
        self.calc_custom_args = ""
        self.calc_open_on_start = False


        # Рабочая клавиша и автокопирование результата
        self.main_hotkey = "num lock"
        self.calc_pause_hotkey = "shift+num lock"
        self.main_hotkey_delay_sec = 0.15
        self.calc_history_path = str(DEFAULT_CALC_HISTORY_FILE)
        self.calc_group_digits = False
        self.calc_open_on_start = False
        self.auto_copy_on_enter = False
        self.auto_copy_enter_delay_ms = 120
        self.auto_copy_prefix_enabled = False
        self.auto_copy_prefix = ""
        self.auto_copy_suffix_enabled = False
        self.auto_copy_suffix = ""
        self.calc_clipboard_mode = CALC_CLIPBOARD_RESULT
        self.auto_copy_mode = self.calc_clipboard_mode
        self.money_text_parentheses = True
        self.money_text_kopecks_mode = "digits"
        self.amount_text_parentheses = True
        self.amount_text_kopecks_mode = "digits"

        # Назначенные программы / мини-лаунчер
        self.launcher_apps = []
        self.launcher_hotkey_handles = []
        self.calc_hotkey_handles = []

        # Способ скрытия калькулятора:
        #   "hide"  — SW_HIDE + WS_EX_TOOLWINDOW (живёт в памяти, taskbar чистый)
        #   "close" — закрывать (WM_CLOSE) и при показе запускать заново
        self.hide_mode = "hide"
        self.interface_theme = THEME_SYSTEM

        # Заявка на Pro / код оборудования. Это не настоящая защита лицензии,
        # а подготовленный UI-слой для заявки и будущей активации.
        self.license_request_email = ""
        self.license_request_telegram_url = ""
        self.license_request_yandex_form_url = LICENSE_REQUEST_YANDEX_FORM_URL
        self.license_request_yandex_form_fields = dict(LICENSE_REQUEST_FIELD_DEFAULTS)

        # Быстрые заметки
        self.notes_path   = str(DEFAULT_NOTES_FILE)
        self.notes_format = NOTE_FMT_MD
        self.notes_separator = " — "
        self.notes_newline_before = True

        # HWND предыдущего активного окна
        self._last_user_hwnd = 0

        # Окно быстрых заметок по горячей клавише
        self.note_popup_enabled = True
        self.note_popup_hotkey = "ctrl+shift+n"
        self.note_popup_submit = "enter"
        self._note_popup_dlg = None
        self._note_popup_hotkey_handle = None

        # Extra-параметры (значения по умолчанию; реальные значения
        # подгрузит extra.load_settings, если модуль доступен).
        # Атрибуты остаются на app, чтобы сохранить совместимость с
        # существующим кодом и виджетами SettingsDialog.
        self.activity_enabled     = True
        self.activity_poll_sec    = 5
        self.idle_threshold_sec   = 120
        self.activity_paused_until = ""
        self.categories           = {}
        self.category_names       = []
        self.archive_enabled      = True
        self.last_archive_date    = ""
        self.screenshots_enabled         = False
        self.screenshot_mode             = "window_change"
        self.screenshot_min_interval_sec = 60
        self.screenshot_timer_interval_sec = 60
        self.screenshot_slowdown_interval_sec = 600
        self.screenshot_slowdown_exes    = []
        self.screenshot_quality          = 70
        self.screenshot_downscale_pct    = 100
        self.screenshot_keep_days        = 14
        self.screenshot_max_gb           = 2.0
        self.screenshot_exclusions       = []
        self.context_mode = "title"
        self.diary_enabled = False
        self.diary_format = "txt"
        self.diary_min_length = 5
        self.diary_keep_days = 90
        self.diary_max_mb = 500
        self.diary_clipboard = False
        self.diary_excluded_exes = []
        self.diary_warning_shown = False
        self.diary_last_rotate = ""
        self.diary_last_size_warn = ""

        # managed_windows: управление окнами сторонних приложений
        self.tray_windows_enabled = True
        self.tray_windows_poll_interval_ms = 300
        self.tray_windows_restore_on_exit = True
        self.tray_windows_restore_on_module_error = True
        self.tray_windows_show_in_main_menu = True
        self.tray_windows_per_window_icons = True
        self.tray_windows_single_manager_menu = True
        self.tray_windows_left_click_action = "restore"
        self.tray_windows_double_click_action = "restore"
        self.tray_windows_close_action_default = "normal"
        self.tray_windows_minimize_action_default = "tray"
        self.tray_windows_rules = []
        self.tray_windows_exclusions = {}
        self.tray_window_manager = None
        self.paid_hide_until = ""
        self.paid_hide_count = 0
        self.paid_hide_permanent = False
        self.autoreplace_enabled = True
        self.autoreplace_file = "autoreplace.txt"
        self.autoreplace_trigger_instant = True
        self.autoreplace_trigger_space = True
        self.autoreplace_trigger_enter = True
        self.autoreplace_trigger_tab = True
        self.autoreplace_block_after_backspace = True
        self.autoreplace_block_after_arrows = True
        self.autoreplace_physical_keys_mode = True
        self.autoreplace_excluded_exes = []
        self._autoreplace_buffer = ""
        self._autoreplace_blocked = False

        # Windows Startup / keyboard recovery / future license verification.
        self.autostart_enabled = False
        self._keyboard_on_press_hook = None
        self._keyboard_recovery_timer = None
        self._keyboard_last_recovery_ts = 0.0
        self._keyboard_idle_recovery_done = False
        self._session_notifications_registered = False
        self._license_verifier_module = None
        self._license_verifier_missing = False
        self._license_cache_stamp = None
        self._license_cache_at = 0.0
        self._license_cache_active = False
        self._license_cache_source = ""
        self._license_cache_message = ""

        # Startup gate: NumLock may be pressed while heavy modules are still initializing.
        # Do not lose the first toggle; queue it until the app is ready.
        self._startup_ready = False
        self._pending_startup_toggle = False
        self._extra_started = False
        self._managed_windows_started = False
        self._tray_rebuild_pending = False
        self.tray = None
        self.tray_menu = None
        self._settings_dlg = None
        self._settings_open_pending = False

        self._startup_mark("START")
        self._startup_mark("SETTINGS_READY: load begin")
        self._load_settings()
        self.autostart_enabled = self._is_startup_enabled()
        if self._pro_soft_active() and self._ensure_pro_soft_loaded():
            try:
                pro_soft.load_settings(self)
            except Exception as e:
                log(f"pro_soft.load_settings failed: {e}")
        else:
            self.auto_copy_prefix_enabled = False
            self.auto_copy_prefix = ""
            self.auto_copy_suffix_enabled = False
            self.auto_copy_suffix = ""
            if self.calc_clipboard_mode == CALC_CLIPBOARD_MONEY_TEXT:
                self.calc_clipboard_mode = CALC_CLIPBOARD_RESULT
            self.auto_copy_mode = self.calc_clipboard_mode
            self.money_text_parentheses = True
            self.money_text_kopecks_mode = "digits"
            self.amount_text_parentheses = True
            self.amount_text_kopecks_mode = "digits"
        self._startup_mark("SETTINGS_READY")
        # Форк: по умолчанию NumLock открывает встроенный стандартный калькулятор,
        # а не внешний Windows Calculator. Если пользователь явно указал другой exe,
        # он сохраняет приоритет.
        if not self._pro_soft_active() and self.calc_custom_cmd not in ("", BUILTIN_CALC_CMD):
            self.calc_custom_cmd = BUILTIN_CALC_CMD
            self.calc_custom_args = ""
        if not self.calc_custom_cmd:
            self.calc_custom_cmd = BUILTIN_CALC_CMD
        self._startup_mark("THEME_READY: apply begin")
        self._apply_interface_theme(rebuild=False)
        self._startup_mark("THEME_READY")

        # Runtime placeholders. Создаются до отложенных запусков, но сами тяжёлые
        # модули ещё не импортируются и не стартуют.
        self.tracker = None
        self.diary = None
        self.shot_timer = None
        self.archive_timer = None
        self.menu_timer = None

        self._sig_toggle.connect(self._do_toggle)
        self._sig_note_popup_show.connect(self._show_note_popup)
        self._sig_auto_copy_request.connect(self._schedule_auto_copy_in_main_thread)
        self._sig_calc_pause_toggle.connect(self._toggle_calc_hotkey_enabled_from_hotkey)
        self._sig_autoreplace_request.connect(self._schedule_autoreplace_in_main_thread)

        # Приоритет 1: калькулятор должен быть доступен раньше трея, меню,
        # Pro Secure и окна в трей. Для обычного запуска без галочки окно не
        # открывается, но встроенный калькулятор остаётся первым тяжёлым объектом.
        self._startup_mark("CALC_OPEN_BEGIN")
        self._open_calc_on_start_if_needed(mark=False)
        self._startup_mark("CALC_READY")

        # Приоритет 2: сначала только основной NumLock. Пауза, заметки и launcher
        # регистрируются позже, чтобы не держать основной сценарий.
        self._startup_mark("NUMLOCK_HOTKEY_BEGIN")
        self._register_calc_hotkeys(primary_only=True)
        self._startup_mark("NUMLOCK_HOTKEY_READY")

        # Приоритет 3: tray icon + минимальное меню. Полное меню будет достроено
        # отложенно, потому что единицы, заметки, учёт времени и окна в трей не
        # нужны для первого расчёта.
        self._startup_mark("TRAY_ICON_BEGIN")
        self._build_tray(minimal=True)
        self._startup_mark("TRAY_ICON_READY")
        self._startup_mark("TRAY_MENU_MIN_READY")

        self._last_effective_theme_name = getattr(app_styles.P, "name", "")
        self._theme_poll_timer = QTimer()
        self._theme_poll_timer.setInterval(2000)
        self._theme_poll_timer.timeout.connect(self._poll_system_theme)
        self._theme_poll_timer.start()

        # Polling foreground-окна: timer exists immediately, starts after startup gate.
        self._our_pid = kernel32.GetCurrentProcessId()
        self.fg_poll_timer = QTimer()
        self.fg_poll_timer.setInterval(300)
        self.fg_poll_timer.timeout.connect(self._poll_foreground)

        self._register_session_notifications()
        self._keyboard_recovery_timer = QTimer()
        self._keyboard_recovery_timer.setInterval(KEYBOARD_RECOVERY_POLL_MS)
        self._keyboard_recovery_timer.timeout.connect(self._poll_keyboard_recovery_watchdog)
        self._keyboard_recovery_timer.start()

        self._startup_ready = True
        if self._pending_startup_toggle:
            self._pending_startup_toggle = False
            QTimer.singleShot(0, self._do_toggle)

        # Приоритет 4: всё остальное, неблокирующе.
        QTimer.singleShot(500, self._register_secondary_hotkeys)
        QTimer.singleShot(700, self._build_full_tray_deferred)
        QTimer.singleShot(900, self._start_foreground_polling)
        QTimer.singleShot(1100, self._register_keyboard_hook_deferred)
        if self._pro_soft_active():
            QTimer.singleShot(1300, self._launch_startup_apps)
        QTimer.singleShot(1500, self._start_extra_runtime)
        QTimer.singleShot(1800, self._prewarm_builtin_calc)
        QTimer.singleShot(2100, self._start_tray_window_manager)
        QTimer.singleShot(2500, self._mark_app_full_ready)
        QTimer.singleShot(8000, lambda: self._recover_hotkeys_after_resume("startup_watchdog"))

        self._startup_mark(f"STARTUP_CORE_READY v{APP_VERSION} extra_file={'yes' if EXTRA_AVAILABLE else 'no'} managed_file={'yes' if MANAGED_WINDOWS_AVAILABLE else 'no'}")
        log(f"Started v{APP_VERSION} (extra={'on' if EXTRA_AVAILABLE else 'off'})")

    # ------------------------------------------------------------------
    # Отложенный старт тяжёлых модулей
    # ------------------------------------------------------------------

    def _license_file_stamp(self):
        try:
            st = LICENSE_FILE.stat()
            return (str(LICENSE_FILE), int(st.st_mtime_ns), int(st.st_size))
        except Exception:
            return None

    def _load_license_verifier(self):
        if bool(getattr(self, "_license_verifier_missing", False)):
            return None
        mod = getattr(self, "_license_verifier_module", None)
        if mod is not None:
            return mod
        try:
            mod = importlib.import_module(LICENSE_VERIFIER_MODULE)
            self._license_verifier_module = mod
            log(f"License verifier loaded: {LICENSE_VERIFIER_MODULE}")
            return mod
        except ModuleNotFoundError:
            self._license_verifier_missing = True
            return None
        except Exception as e:
            self._license_verifier_missing = True
            log(f"License verifier import failed: {e}")
            return None

    def _normalize_license_result(self, result) -> bool:
        if isinstance(result, bool):
            return result
        if isinstance(result, dict):
            for key in ("active", "valid", "ok", "enabled"):
                if key in result:
                    return bool(result.get(key))
            return False
        if isinstance(result, (tuple, list)) and result:
            return bool(result[0])
        return bool(result)

    def _verify_license_with_module(self, verifier) -> bool:
        fn = None
        for name in ("verify_license", "verify", "is_license_valid"):
            candidate = getattr(verifier, name, None)
            if callable(candidate):
                fn = candidate
                break
        if fn is None:
            log("License verifier has no verify_license/verify/is_license_valid function")
            return False if LICENSE_STRICT_VERIFICATION else True
        try:
            result = fn(
                license_path=str(LICENSE_FILE),
                hardware_code=self._get_hardware_code(),
                product=PRODUCT_DISPLAY_NAME,
                version=PRODUCT_VERSION_LABEL,
                app_root=str(APP_ROOT),
            )
            return self._normalize_license_result(result)
        except TypeError:
            try:
                result = fn(str(LICENSE_FILE), self._get_hardware_code())
                return self._normalize_license_result(result)
            except Exception as e:
                log(f"License verifier call failed: {e}")
        except Exception as e:
            log(f"License verifier call failed: {e}")
        return False if LICENSE_STRICT_VERIFICATION else True

    def _pro_license_active(self) -> bool:
        return False

    def _pro_soft_active(self) -> bool:
        return False

    def _pro_secure_active(self) -> bool:
        return False

    def _paid_items_visible(self) -> bool:
        return False

    def _paid_items_hint(self) -> str:
        return "Публичная сборка Free Core не содержит платных пунктов."

    def _set_paid_items_visible(self, visible: bool) -> None:
        return None

    def _startup_folder(self) -> Optional[Path]:
        if not sys.platform.startswith("win"):
            return None
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return None
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

    def _startup_shortcut_path(self) -> Optional[Path]:
        folder = self._startup_folder()
        if folder is None:
            return None
        return folder / STARTUP_SHORTCUT_NAME

    def _is_startup_enabled(self) -> bool:
        path = self._startup_shortcut_path()
        try:
            return bool(path and path.exists())
        except Exception:
            return False

    def _launch_target_for_shortcut(self) -> tuple[str, str, str]:
        if getattr(sys, "frozen", False):
            target = Path(sys.executable).resolve()
            args = ""
        else:
            target = Path(sys.executable).resolve()
            if target.name.lower() == "python.exe":
                candidate = target.with_name("pythonw.exe")
                if candidate.exists():
                    target = candidate
            script = Path(sys.argv[0]).resolve()
            args = f'"{script}"'
        return str(target), args, str(APP_ROOT)

    def _ps_quote(self, value: str) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    def _run_powershell_encoded(self, command: str) -> bool:
        if not sys.platform.startswith("win"):
            return False
        try:
            import base64
            encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=12,
                creationflags=creationflags,
            )
            if completed.returncode != 0:
                log(f"PowerShell failed: {completed.stderr.strip() or completed.stdout.strip()}")
                return False
            return True
        except Exception as e:
            log(f"PowerShell launch failed: {e}")
            return False

    def _create_startup_shortcut(self) -> bool:
        shortcut = self._startup_shortcut_path()
        if shortcut is None:
            log("Autostart shortcut skipped: Windows Startup folder unavailable")
            return False
        try:
            shortcut.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log(f"Autostart shortcut folder create failed: {e}")
            return False
        target, args, workdir = self._launch_target_for_shortcut()
        icon = APP_ROOT / ICON_NAME
        icon_path = str(icon if icon.exists() else target)
        ps = "\n".join([
            "$WshShell = New-Object -ComObject WScript.Shell",
            f"$Shortcut = $WshShell.CreateShortcut({self._ps_quote(str(shortcut))})",
            f"$Shortcut.TargetPath = {self._ps_quote(target)}",
            f"$Shortcut.Arguments = {self._ps_quote(args)}",
            f"$Shortcut.WorkingDirectory = {self._ps_quote(workdir)}",
            f"$Shortcut.IconLocation = {self._ps_quote(icon_path)}",
            "$Shortcut.WindowStyle = 7",
            f"$Shortcut.Description = {self._ps_quote(PRODUCT_DISPLAY_NAME)}",
            "$Shortcut.Save()",
        ])
        ok = self._run_powershell_encoded(ps)
        if ok:
            log(f"Autostart shortcut created: {shortcut}")
        return ok

    def _remove_startup_shortcut(self) -> bool:
        shortcut = self._startup_shortcut_path()
        if shortcut is None:
            log("Autostart shortcut remove skipped: Windows Startup folder unavailable")
            return False
        try:
            if shortcut.exists():
                shortcut.unlink()
                log(f"Autostart shortcut removed: {shortcut}")
            return True
        except Exception as e:
            log(f"Autostart shortcut remove failed: {e}")
            return False

    def _set_startup_enabled(self, enabled: bool) -> bool:
        ok = self._create_startup_shortcut() if enabled else self._remove_startup_shortcut()
        self.autostart_enabled = self._is_startup_enabled()
        return bool(ok)

    def _get_product_edition(self) -> str:
        return "Free Core"

    def _get_hardware_code(self) -> str:
        """Стабильный короткий код оборудования для заявки на Pro.

        Это не криптографическая защита и не лицензирование. Код строится из
        локальных стабильных признаков машины и хэшируется, чтобы не показывать
        пользователю сырые идентификаторы Windows/железа.
        """
        parts = [PRODUCT_DISPLAY_NAME, APP_VERSION, platform.node(), str(uuid.getnode())]
        try:
            parts.append(str(os.environ.get("COMPUTERNAME", "")))
            parts.append(str(os.environ.get("PROCESSOR_IDENTIFIER", "")))
        except Exception:
            pass
        if sys.platform.startswith("win"):
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
                winreg.CloseKey(key)
                parts.append(str(value))
            except Exception:
                pass
        raw = "|".join(p for p in parts if p)
        digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest().upper()[:24]
        return "-".join(digest[i:i + 4] for i in range(0, len(digest), 4))

    def _license_request_payload(self) -> dict:
        return {
            "product": PRODUCT_DISPLAY_NAME,
            "version": PRODUCT_VERSION_LABEL,
            "edition": self._get_product_edition(),
            "hardware_code": self._get_hardware_code(),
            "source": "about_dialog",
        }

    def _license_request_url(self) -> str:
        base = str(getattr(self, "license_request_yandex_form_url", LICENSE_REQUEST_YANDEX_FORM_URL) or LICENSE_REQUEST_YANDEX_FORM_URL).strip()
        fields = getattr(self, "license_request_yandex_form_fields", {}) or {}
        payload = self._license_request_payload()
        params = {}
        for logical_name, field_name in fields.items():
            field_name = str(field_name or "").strip()
            if field_name and logical_name in payload:
                params[field_name] = payload[logical_name]
        if not params:
            return base
        try:
            split = urlsplit(base)
            query = dict(parse_qsl(split.query, keep_blank_values=True))
            query.update(params)
            return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))
        except Exception:
            return base

    def _copy_hardware_code(self) -> None:
        try:
            QGuiApplication.clipboard().setText(self._get_hardware_code())
        except Exception as e:
            log(f"Copy hardware code failed: {e}")

    def _open_license_request_form(self) -> None:
        try:
            self._copy_hardware_code()
            webbrowser.open(self._license_request_url())
        except Exception as e:
            log(f"Open license request form failed: {e}")
            try:
                QMessageBox.warning(self, APP_NAME, f"Не удалось открыть форму заявки: {e}")
            except Exception:
                pass

    def _show_pro_locked_popup(self, feature: str = "Эта функция") -> None:
        if self._pro_license_active():
            return
        # Платный пункт не запускает отдельный popup. Открываем «О программе»,
        # там пользователь сам управляет галкой показа платных пунктов.
        try:
            dlg = AboutDialog(self)
            dlg.exec_()
        except Exception as e:
            log(f"Open About from locked Pro item failed: {e}")

    def _locked_action(self, text: str, feature: str | None = None) -> QAction:
        act = QAction(f"🔒 {text}", self)
        act.triggered.connect(lambda _=False, f=feature or text: self._show_pro_locked_popup(f))
        return act

    def _locked_menu(self, title: str, items: list[str]) -> QMenu:
        m = QMenu(f"🔒 {title}", self)
        m.setStyleSheet(MENU_QSS)
        for item in items:
            m.addAction(self._locked_action(item, title))
        return m

    def _ensure_pro_soft_loaded(self) -> bool:
        global pro_soft, PRO_SOFT_AVAILABLE
        if not self._pro_license_active():
            return False
        if pro_soft is not None:
            return True
        if not PRO_SOFT_AVAILABLE:
            return False
        try:
            pro_soft = importlib.import_module("pro_soft")
            return True
        except Exception as e:
            pro_soft = None
            PRO_SOFT_AVAILABLE = False
            log(f"pro_soft import failed: {e}\n{traceback.format_exc()}")
            return False

    def _ensure_pro_secure_loaded(self) -> bool:
        global pro_secure, PRO_SECURE_AVAILABLE
        if not self._pro_license_active():
            return False
        if pro_secure is not None:
            return True
        if not PRO_SECURE_AVAILABLE:
            return False
        try:
            pro_secure = importlib.import_module("pro_secure")
            return True
        except Exception as e:
            pro_secure = None
            PRO_SECURE_AVAILABLE = False
            log(f"pro_secure import failed: {e}\n{traceback.format_exc()}")
            return False

    def _ensure_extra_loaded(self) -> bool:
        global extra, EXTRA_AVAILABLE
        if extra is not None:
            return True
        if not (EXTRA_AVAILABLE and self._pro_secure_active()):
            return False
        self._startup_mark("PRO_SECURE_IMPORT_BEGIN")
        try:
            if not self._ensure_pro_secure_loaded():
                return False
            extra = pro_secure.extra
            EXTRA_AVAILABLE = True
            self._startup_mark("PRO_SECURE_EXTRA_READY")
            return True
        except Exception as e:
            extra = None
            EXTRA_AVAILABLE = False
            log(f"pro_secure extra import failed: {e}")
            self._startup_mark("PRO_SECURE_EXTRA_FAILED")
            return False

    def _ensure_managed_windows_loaded(self) -> bool:
        global managed_windows, MANAGED_WINDOWS_AVAILABLE
        if managed_windows is not None:
            return True
        if not (MANAGED_WINDOWS_AVAILABLE and self._pro_secure_active()):
            return False
        self._startup_mark("PRO_SECURE_WINDOWS_IMPORT_BEGIN")
        try:
            if not self._ensure_pro_secure_loaded():
                return False
            managed_windows = pro_secure.managed_windows
            MANAGED_WINDOWS_AVAILABLE = True
            self._startup_mark("PRO_SECURE_WINDOWS_READY")
            return True
        except Exception as e:
            managed_windows = None
            MANAGED_WINDOWS_AVAILABLE = False
            log(f"pro_secure windows import failed: {e}")
            self._startup_mark("PRO_SECURE_WINDOWS_FAILED")
            return False

    def _load_extra_settings_deferred(self) -> None:
        if not self._ensure_extra_loaded():
            return
        try:
            extra.load_settings(self)
            self._startup_mark("EXTRA_SETTINGS_READY")
        except Exception as e:
            log(f"extra.load_settings failed: {e}")

    def _init_managed_windows_deferred(self) -> None:
        if not self._ensure_managed_windows_loaded():
            return
        try:
            managed_windows.load_settings(self)
            self._startup_mark("MANAGED_WINDOWS_SETTINGS_READY")
        except Exception as e:
            log(f"managed_windows.load_settings failed: {e}")
        try:
            if self.tray_window_manager is None:
                self.tray_window_manager = managed_windows.TrayWindowManager(self)
                self._startup_mark("MANAGED_WINDOWS_MANAGER_READY")
        except Exception as e:
            self.tray_window_manager = None
            log(f"TrayWindowManager init failed: {e}")

    def _register_secondary_hotkeys(self):
        self._startup_mark("SECONDARY_HOTKEYS_BEGIN")
        if self._pro_soft_active():
            try:
                self._register_note_popup_hotkey()
            except Exception as e:
                log(f"register note popup hotkey delayed failed: {e}")
        try:
            self._register_calc_hotkeys(primary_only=False)
        except Exception as e:
            log(f"register calc hotkeys delayed failed: {e}")
        if self._pro_soft_active():
            try:
                self._register_launcher_hotkeys()
            except Exception as e:
                log(f"register launcher hotkeys delayed failed: {e}")
        self._startup_mark("SECONDARY_HOTKEYS_READY")

    def _load_autoreplace_settings_deferred(self) -> None:
        if not self._pro_secure_active():
            return
        if not self._ensure_pro_secure_loaded():
            return
        try:
            pro_secure.load_autoreplace_settings(self)
            pro_secure.load_autoreplace_rules(self)
            self._startup_mark("AUTOREPLACE_SETTINGS_READY")
        except Exception as e:
            log(f"pro_secure.load_autoreplace_settings failed: {e}")

    def _register_keyboard_hook_deferred(self):
        self._startup_mark("KEYBOARD_HOOK_BEGIN")
        self._load_autoreplace_settings_deferred()
        self._register_keyboard_hook(reason="startup_deferred")
        self._startup_mark("KEYBOARD_HOOK_READY")

    def _build_full_tray_deferred(self):
        try:
            if getattr(self, "_tray_full_menu_built", False):
                return
            self._startup_mark("TRAY_MENU_FULL_BEGIN")
            self._load_units_file()
            self._startup_mark("UNITS_READY")
            # Для полного меню нужны отложенные модули, но их ошибки не должны
            # ломать уже работающий калькулятор.
            if EXTRA_AVAILABLE and self._pro_secure_active():
                self._load_extra_settings_deferred()
            if MANAGED_WINDOWS_AVAILABLE and self._pro_secure_active():
                self._init_managed_windows_deferred()
            self._build_tray(minimal=False)
            self._startup_mark("TRAY_MENU_FULL_READY")
        except Exception as e:
            log(f"Full tray deferred build failed: {e}")

    def _mark_app_full_ready(self):
        self._startup_mark("APP_FULL_READY")

    def _start_foreground_polling(self):
        try:
            if hasattr(self, "fg_poll_timer") and self.fg_poll_timer is not None and not self.fg_poll_timer.isActive():
                self.fg_poll_timer.start()
                self._startup_mark("foreground polling: started")
                log("Foreground polling started")
        except Exception as e:
            log(f"Foreground polling start failed: {e}")

    def _start_tray_window_manager(self):
        if self._managed_windows_started:
            return
        self._managed_windows_started = True
        if not (MANAGED_WINDOWS_AVAILABLE and self._pro_secure_active()):
            return
        self._startup_mark("MANAGED_WINDOWS_START_BEGIN")
        self._init_managed_windows_deferred()
        if self.tray_window_manager is None:
            return
        try:
            if self.tray_windows_enabled:
                self.tray_window_manager.start()
                self._startup_mark("MANAGED_WINDOWS_READY")
        except Exception as e:
            log(f"TrayWindowManager delayed start failed: {e}")

    def _start_extra_runtime(self):
        if self._extra_started:
            return
        self._extra_started = True
        if not (EXTRA_AVAILABLE and self._pro_secure_active()):
            return
        self._startup_mark("EXTRA_READY_BEGIN")
        self._load_extra_settings_deferred()
        if extra is None:
            return
        try:
            self.tracker = extra.ActivityTracker(self)
            if self.activity_enabled:
                self.tracker.start()
        except Exception as e:
            self.tracker = None
            log(f"ActivityTracker delayed init failed: {e}")
        try:
            self.diary = extra.DiaryManager(self)
        except Exception as e:
            self.diary = None
            log(f"DiaryManager delayed init failed: {e}")
        try:
            self.shot_timer = QTimer()
            self.shot_timer.timeout.connect(self._on_shot_timer_tick)
            self.screenshots_apply_timer()
        except Exception as e:
            self.shot_timer = None
            log(f"Screenshot timer delayed init failed: {e}")
        try:
            self.archive_timer = QTimer()
            self.archive_timer.setInterval(60 * 60 * 1000)
            self.archive_timer.timeout.connect(self._check_archive)
            self.archive_timer.start()
            QTimer.singleShot(5000, self._check_archive)
        except Exception as e:
            self.archive_timer = None
            log(f"Archive timer delayed init failed: {e}")
        try:
            self.menu_timer = QTimer()
            self.menu_timer.setInterval(30 * 1000)
            self.menu_timer.timeout.connect(self._refresh_pause_label)
            self.menu_timer.start()
        except Exception as e:
            self.menu_timer = None
            log(f"Menu timer delayed init failed: {e}")
        try:
            self._refresh_pause_label()
        except Exception:
            pass
        self._startup_mark("EXTRA_READY")

    # ------------------------------------------------------------------
    # Тема интерфейса
    # ------------------------------------------------------------------
    def _apply_interface_theme(self, rebuild: bool = False):
        self.interface_theme = normalize_theme_mode(getattr(self, "interface_theme", THEME_SYSTEM))
        try:
            app_styles.apply_theme_mode(self.interface_theme)
            _sync_style_globals_from_styles()
            self._last_effective_theme_name = getattr(app_styles.P, "name", "")
        except Exception as e:
            log(f"Apply interface theme failed: {e}")
            return

        try:
            self.setStyleSheet(SETTINGS_QSS)
        except Exception:
            pass

        try:
            w = getattr(self, "_builtin_calc_window", None)
            if w is not None and hasattr(w, "set_theme_mode"):
                w.set_theme_mode(self.interface_theme)
        except Exception as e:
            log(f"Apply interface theme to builtin calculator failed: {e}")

        if rebuild:
            try:
                self._rebuild_tray_ui()
            except Exception as e:
                log(f"Rebuild tray after interface theme failed: {e}")

    def _poll_system_theme(self):
        if normalize_theme_mode(getattr(self, "interface_theme", THEME_SYSTEM)) != THEME_SYSTEM:
            return
        try:
            effective = app_styles.active_palette(THEME_SYSTEM).name
            if effective != getattr(self, "_last_effective_theme_name", ""):
                self._apply_interface_theme(rebuild=True)
        except Exception as e:
            log(f"Poll system theme failed: {e}")

    # ------------------------------------------------------------------
    # Настройки (базовые)
    # ------------------------------------------------------------------
    def _startup_mark(self, label: str) -> None:
        startup_mark(label)

    def _load_settings(self):
        if not SETTINGS_FILE.exists():
            return
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        # Калькулятор
        self.opacity_pct = int(data.get("opacity_pct", 100))
        self.pos_mode    = data.get("pos_mode", POS_CENTER)
        self.calc_hotkey_enabled = bool(data.get("calc_hotkey_enabled", True))
        self.main_hotkey = str(data.get("main_hotkey", "num lock") or "num lock").strip().lower()
        self.calc_pause_hotkey = str(data.get("calc_pause_hotkey", data.get("pause_hotkey", "shift+num lock")) or "shift+num lock").strip().lower()
        self.main_hotkey_delay_sec = float(data.get("main_hotkey_delay_sec", 0.15))
        self.auto_copy_enter_delay_ms = int(data.get("auto_copy_enter_delay_ms", 120))
        raw_clipboard_mode = data.get("calc_clipboard_mode", None)
        if raw_clipboard_mode is None:
            raw_clipboard_mode = CALC_CLIPBOARD_RESULT if bool(data.get("auto_copy_on_enter", True)) else CALC_CLIPBOARD_OFF
        self.calc_clipboard_mode = _normalize_calc_clipboard_mode(
            raw_clipboard_mode,
            allow_money_text=self._pro_soft_active(),
        )
        self.auto_copy_on_enter = self.calc_clipboard_mode != CALC_CLIPBOARD_OFF
        self.calc_history_path = str(data.get("calc_history_path", str(DEFAULT_CALC_HISTORY_FILE)) or str(DEFAULT_CALC_HISTORY_FILE))
        self.calc_group_digits = bool(data.get("calc_group_digits", False))
        self.calc_open_on_start = bool(data.get("calc_open_on_start", False))
        self.autostart_enabled = bool(data.get("autostart_enabled", False))
        sp = data.get("session_pos")
        if isinstance(sp, list) and len(sp) == 2:
            self.session_pos = tuple(sp)
        # Единицы
        self.unit_mode = data.get("unit_mode", UNIT_MODE_APPEND)
        if self.unit_mode not in (UNIT_MODE_APPEND, UNIT_MODE_COPY):
            self.unit_mode = UNIT_MODE_APPEND
        self.unit_auto_paste     = bool(data.get("unit_auto_paste", False))
        self.unit_keep_menu_open = bool(data.get("unit_keep_menu_open", True))
        # Сторонний exe
        self.calc_custom_cmd  = str(data.get("calc_custom_cmd", "") or "")
        self.calc_custom_args = str(data.get("calc_custom_args", "") or "")
        self.paid_hide_until = str(data.get("paid_hide_until", "") or "")
        try:
            self.paid_hide_count = max(0, int(data.get("paid_hide_count", 0) or 0))
        except Exception:
            self.paid_hide_count = 0
        self.paid_hide_permanent = bool(data.get("paid_hide_permanent", False))
        # Способ скрытия
        hm = str(data.get("hide_mode", "hide"))
        self.hide_mode = hm if hm in ("hide", "close") else "hide"
        self.interface_theme = normalize_theme_mode(data.get("interface_theme", THEME_SYSTEM))
        lic_req = data.get("license_request", {}) if isinstance(data.get("license_request", {}), dict) else {}
        self.license_request_email = str(lic_req.get("email", "") or "")
        self.license_request_telegram_url = str(lic_req.get("telegram_url", "") or "")
        self.license_request_yandex_form_url = str(lic_req.get("yandex_form_url", LICENSE_REQUEST_YANDEX_FORM_URL) or LICENSE_REQUEST_YANDEX_FORM_URL)
        fields = lic_req.get("yandex_form_fields", {}) if isinstance(lic_req.get("yandex_form_fields", {}), dict) else {}
        merged_fields = dict(LICENSE_REQUEST_FIELD_DEFAULTS)
        for key, value in fields.items():
            if key in merged_fields:
                merged_fields[key] = str(value or "")
        self.license_request_yandex_form_fields = merged_fields

    def _save_settings(self):
        data = {
            "opacity_pct": self.opacity_pct,
            "pos_mode": self.pos_mode,
            "calc_hotkey_enabled": self.calc_hotkey_enabled,
            "main_hotkey": self.main_hotkey,
            "calc_pause_hotkey": self.calc_pause_hotkey,
            "main_hotkey_delay_sec": self.main_hotkey_delay_sec,
            "auto_copy_on_enter": _normalize_calc_clipboard_mode(
                getattr(self, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT),
                allow_money_text=self._pro_soft_active(),
            ) != CALC_CLIPBOARD_OFF,
            "auto_copy_enter_delay_ms": self.auto_copy_enter_delay_ms,
            "calc_clipboard_mode": _normalize_calc_clipboard_mode(
                getattr(self, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT),
                allow_money_text=self._pro_soft_active(),
            ),
            "calc_history_path": self.calc_history_path,
            "calc_group_digits": bool(getattr(self, "calc_group_digits", False)),
            "calc_open_on_start": bool(getattr(self, "calc_open_on_start", False)),
            "autostart_enabled": bool(self._is_startup_enabled()),
            "session_pos": list(self.session_pos) if self.session_pos else None,
            "unit_mode": self.unit_mode,
            "unit_auto_paste": self.unit_auto_paste,
            "unit_keep_menu_open": self.unit_keep_menu_open,
            "calc_custom_cmd": self.calc_custom_cmd if self.calc_custom_cmd in ("", BUILTIN_CALC_CMD) else "",
            "paid_hide_until": getattr(self, "paid_hide_until", ""),
            "paid_hide_count": int(getattr(self, "paid_hide_count", 0) or 0),
            "paid_hide_permanent": bool(getattr(self, "paid_hide_permanent", False)),
            "hide_mode": self.hide_mode,
            "interface_theme": normalize_theme_mode(getattr(self, "interface_theme", THEME_SYSTEM)),
            "license_request": {
                "email": str(getattr(self, "license_request_email", "") or ""),
                "telegram_url": str(getattr(self, "license_request_telegram_url", "") or ""),
                "yandex_form_url": str(getattr(self, "license_request_yandex_form_url", LICENSE_REQUEST_YANDEX_FORM_URL) or LICENSE_REQUEST_YANDEX_FORM_URL),
                "yandex_form_fields": dict(getattr(self, "license_request_yandex_form_fields", LICENSE_REQUEST_FIELD_DEFAULTS) or LICENSE_REQUEST_FIELD_DEFAULTS),
            },
        }
        try:
            SETTINGS_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            log(f"Save settings failed: {e}")

    def _save_pro_soft_settings(self) -> None:
        if not (self._pro_soft_active() and self._ensure_pro_soft_loaded()):
            return
        try:
            pro_soft.save_settings(self)
        except Exception as e:
            log(f"pro_soft.save_settings failed: {e}")

    def _reset_settings(self):
        self.opacity_pct = 100
        self.pos_mode    = POS_CENTER
        self.session_pos = None
        self.calc_hotkey_enabled = True
        self.main_hotkey = "num lock"
        self.calc_pause_hotkey = "shift+num lock"
        self.main_hotkey_delay_sec = 0.15
        self.unit_mode = UNIT_MODE_APPEND
        self.unit_auto_paste = False
        self.unit_keep_menu_open = True
        self.calc_custom_cmd  = ""
        self.calc_custom_args = ""
        self.calc_open_on_start = False
        self.calc_clipboard_mode = CALC_CLIPBOARD_RESULT
        self.auto_copy_mode = self.calc_clipboard_mode
        self.money_text_parentheses = True
        self.money_text_kopecks_mode = "digits"
        self.amount_text_parentheses = True
        self.amount_text_kopecks_mode = "digits"
        self.hide_mode = "hide"
        self.interface_theme = THEME_SYSTEM
        self._apply_interface_theme(rebuild=False)
        self.notes_separator = " — "
        self.notes_newline_before = True
        self._save_settings()
        if self._pro_secure_active() and EXTRA_AVAILABLE and self._ensure_extra_loaded():
            try:
                extra.reset_settings(self)
            except Exception as e:
                log(f"extra.reset_settings failed: {e}")
        if MANAGED_WINDOWS_AVAILABLE and self._ensure_managed_windows_loaded():
            try:
                managed_windows.reset_settings(self)
                if self.tray_window_manager is not None:
                    self.tray_window_manager.reload_settings()
            except Exception as e:
                log(f"managed_windows.reset_settings failed: {e}")
        log("Settings reset to defaults")
        if hasattr(self, "sld_opacity"):
            self.sld_opacity.setValue(self.opacity_pct)
        if hasattr(self, "act_calc_hotkey_enabled"):
            self.act_calc_hotkey_enabled.blockSignals(True)
            self.act_calc_hotkey_enabled.setChecked(self.calc_hotkey_enabled)
            self.act_calc_hotkey_enabled.blockSignals(False)
        if hasattr(self, "_unit_mode_buttons"):
            for rb in self._unit_mode_buttons:
                try:
                    rb.blockSignals(True)
                    rb.setChecked(rb.property("unit_mode") == self.unit_mode)
                finally:
                    rb.blockSignals(False)
        if hasattr(self, "chk_unit_auto_paste"):
            self.chk_unit_auto_paste.blockSignals(True)
            self.chk_unit_auto_paste.setChecked(self.unit_auto_paste)
            self.chk_unit_auto_paste.blockSignals(False)
        if hasattr(self, "chk_unit_keep_open"):
            self.chk_unit_keep_open.blockSignals(True)
            self.chk_unit_keep_open.setChecked(self.unit_keep_menu_open)
            self.chk_unit_keep_open.blockSignals(False)
        if hasattr(self, "units_menu"):
            self._rebuild_units_menu()
        self._refresh_notes_label()

    # ------------------------------------------------------------------
    # Контекст окна (заголовок, URL, чат) — делегируется extra
    # ------------------------------------------------------------------
    def get_window_context(self, exe: str, hwnd: int) -> str:
        if self._pro_secure_active() and EXTRA_AVAILABLE and self._ensure_extra_loaded():
            try:
                return extra.get_window_context(self, exe, hwnd)
            except Exception as e:
                log(f"extra.get_window_context failed: {e}")
        return ""

    # ------------------------------------------------------------------
    # Единицы измерения
    # ------------------------------------------------------------------
    def _ensure_units_file(self):
        if not UNITS_FILE.exists():
            try:
                UNITS_FILE.write_text(DEFAULT_UNITS_TEXT, encoding="utf-8")
            except Exception as e:
                log(f"Create units file failed: {e}")

    def _load_units_file(self):
        self._ensure_units_file()
        self.units_by_category = {}
        try:
            lines = UNITS_FILE.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            log(f"Read units file failed: {e}")
            return

        for i, raw in enumerate(lines, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            parts = [p.strip() for p in raw.split("|", 2)]
            if len(parts) == 2:
                category, label = parts
                value = label
            elif len(parts) == 3:
                category, label, value = parts
            else:
                log(f"Bad units line {i}: {raw}")
                continue

            if not category or not label:
                log(f"Empty category/label in units line {i}: {raw}")
                continue

            self.units_by_category.setdefault(category, []).append({
                "label": label,
                "value": value or label,
            })

    def _reload_units_file(self):
        self._load_units_file()
        self._rebuild_units_menu()
        try:
            self.tray.showMessage(
                APP_NAME,
                f"Меню единиц перечитано из {UNITS_FILE.name}",
                QSystemTrayIcon.Information,
                1500
            )
        except Exception:
            pass
        log("Units menu reloaded")

    def _open_units_file(self):
        self._ensure_units_file()
        try:
            os.startfile(str(UNITS_FILE))
        except Exception as e:
            log(f"Open units file failed: {e}")

    def _build_autoreplace_menu(self) -> QMenu:
        m = QMenu("Автозамена", self)
        m.setStyleSheet(MENU_QSS)

        act_enabled = QAction("Включена", self)
        act_enabled.setCheckable(True)
        act_enabled.setChecked(bool(getattr(self, "autoreplace_enabled", True)))
        act_enabled.triggered.connect(lambda checked: self._set_autoreplace_enabled(bool(checked)))
        m.addAction(act_enabled)

        m.addSeparator()

        act_reload = QAction("Перечитать autoreplace.txt", self)
        act_reload.triggered.connect(self._reload_autoreplace_rules)
        m.addAction(act_reload)

        act_open = QAction("Открыть autoreplace.txt", self)
        act_open.triggered.connect(self._open_autoreplace_file)
        m.addAction(act_open)

        act_settings = QAction("Настройки автозамены…", self)
        act_settings.triggered.connect(self._open_settings)
        m.addAction(act_settings)
        return m

    def _set_autoreplace_enabled(self, checked: bool) -> None:
        if not self._pro_secure_active():
            self._show_pro_locked_popup("Автозамена")
            return
        self.autoreplace_enabled = bool(checked)
        try:
            if self._ensure_pro_secure_loaded():
                pro_secure.save_autoreplace_settings(self)
                pro_secure.load_autoreplace_rules(self)
        except Exception as e:
            log(f"Save autoreplace enabled failed: {e}\n{traceback.format_exc()}")
        try:
            self._register_keyboard_hook(reason="autoreplace_toggle")
        except Exception as e:
            log(f"register keyboard hook after autoreplace toggle failed: {e}")
        try:
            self._rebuild_tray_ui()
        except Exception:
            pass

    def _reload_autoreplace_rules(self) -> None:
        if not self._pro_secure_active():
            self._show_pro_locked_popup("Автозамена")
            return
        try:
            if self._ensure_pro_secure_loaded():
                pro_secure.load_autoreplace_settings(self)
                pro_secure.reload_autoreplace_rules(self)
                try:
                    self.tray.showMessage(APP_NAME, "Автозамена перечитана из autoreplace.txt", QSystemTrayIcon.Information, 1500)
                except Exception:
                    pass
                log("Autoreplace rules reloaded")
        except Exception as e:
            log(f"Autoreplace reload failed: {e}\n{traceback.format_exc()}")

    def _open_autoreplace_file(self) -> None:
        if not self._pro_secure_active():
            self._show_pro_locked_popup("Автозамена")
            return
        try:
            if self._ensure_pro_secure_loaded():
                path = pro_secure.ensure_autoreplace_file(self)
                os.startfile(str(path))
        except Exception as e:
            log(f"Open autoreplace file failed: {e}")

    def _get_clipboard_text(self) -> str:
        try:
            cb = QApplication.clipboard()
            return cb.text() or ""
        except Exception:
            return ""

    def _set_clipboard_text(self, text: str):
        try:
            QApplication.clipboard().setText(text)
        except Exception as e:
            log(f"Set clipboard failed: {e}")

    def _paste_to_previous_window(self) -> bool:
        hwnd = self._last_user_hwnd
        if not hwnd:
            log("Paste: no saved HWND")
            return False
        if not user32.IsWindow(hwnd):
            log(f"Paste: saved HWND {hwnd} is not a window anymore")
            self._last_user_hwnd = 0
            return False

        try:
            cm = self.tray.contextMenu()
            if cm:
                cm.close()
        except Exception:
            pass

        def _do_paste():
            try:
                title = _get_text(hwnd)[:60]
                ok_fg = _force_foreground(hwnd)
                time.sleep(0.05)
                ok_send = _send_ctrl_v()
                log(f"Paste → hwnd={hwnd} title={title!r} "
                    f"fg={ok_fg} send={ok_send}")
            except Exception as e:
                log(f"Paste async error: {e}")

        QTimer.singleShot(120, _do_paste)
        return True

    def _apply_unit(self, unit_value: str):
        current = self._get_clipboard_text()

        if self.unit_mode == UNIT_MODE_COPY:
            result = unit_value
        else:
            if not current:
                result = unit_value
            elif current[-1] in (' ', '\t', '\n', '\u00A0'):
                result = current + unit_value
            else:
                result = current + ' ' + unit_value

        self._set_clipboard_text(result)

        try:
            self.tray.showMessage(
                APP_NAME,
                f"Скопировано: {result}",
                QSystemTrayIcon.Information,
                1200
            )
        except Exception:
            pass

        # Автовставка работает только при «классическом» закрытии меню
        # (обычный ЛКМ). Если меню осталось открыто (ПКМ/Shift+ЛКМ при
        # включённой галке) — фокус ещё на меню, вставлять некуда.
        pasted = False
        if self.unit_auto_paste and not self._units_menu_kept_open():
            pasted = self._paste_to_previous_window()

        log(f"Unit applied: mode={self.unit_mode}, value={unit_value!r}, "
            f"auto_paste={self.unit_auto_paste}, pasted={pasted}, "
            f"keep_open={self.unit_keep_menu_open}")

    def _units_menu_kept_open(self) -> bool:
        """True, если меню единиц сейчас остаётся открытым (ПКМ или Shift+ЛКМ)."""
        try:
            if not getattr(self, "unit_keep_menu_open", False):
                return False
            if not hasattr(self, "units_menu"):
                return False
            # Флаг ставится самим меню в _trigger_silently — на время триггера.
            return bool(self.units_menu.property("stay_open_triggered"))
        except Exception:
            return False

    def _set_unit_mode(self, mode: str):
        if mode not in (UNIT_MODE_APPEND, UNIT_MODE_COPY):
            return
        if self.unit_mode == mode:
            return
        self.unit_mode = mode
        # Синхронизируем визуальное состояние радио (на случай вызова не из toggled).
        if hasattr(self, "_unit_mode_buttons"):
            for rb in self._unit_mode_buttons:
                try:
                    rb.blockSignals(True)
                    rb.setChecked(rb.property("unit_mode") == mode)
                except Exception:
                    pass
                finally:
                    try:
                        rb.blockSignals(False)
                    except Exception:
                        pass
        self._save_settings()
        log(f"Unit mode: {mode}")

    def _set_unit_auto_paste_from_menu(self, checked: bool):
        self.unit_auto_paste = bool(checked)
        self._save_settings()
        log(f"Unit auto_paste: {self.unit_auto_paste}")

    def _set_unit_keep_open_from_menu(self, checked: bool):
        self.unit_keep_menu_open = bool(checked)
        # Применяем режим к меню без полной пересборки — иначе потеряется
        # popup и пересобранные виджеты не успеют отрисоваться корректно.
        try:
            if hasattr(self, "units_menu"):
                self.units_menu.setKeepOpenOnModifier(bool(self.unit_keep_menu_open))
        except Exception:
            pass
        self._save_settings()
        log(f"Unit keep_menu_open: {self.unit_keep_menu_open}")

    def _apply_number_to_text(self):
        """Берёт число из буфера и подставляет его текстовое представление.
        Поведение зависит от настроек единиц измерения (append/copy, autopaste)."""
        current = self._get_clipboard_text() or ""
        text_value = number_to_russian_text(current)
        if text_value is None:
            try:
                self.tray.showMessage(
                    APP_NAME,
                    "В буфере не найдено числа",
                    QSystemTrayIcon.Warning,
                    1500
                )
            except Exception:
                pass
            log(f"Num→text: no number in clipboard ({current!r:.40})")
            return

        # Режим COPY — заменяем буфер на текст. Режим APPEND — дописываем
        # текст к буферу через пробел (по аналогии с единицей).
        if self.unit_mode == UNIT_MODE_COPY:
            result = text_value
        else:
            if not current:
                result = text_value
            elif current[-1] in (' ', '\t', '\n', '\u00A0'):
                result = current + text_value
            else:
                result = current + ' ' + text_value

        self._set_clipboard_text(result)

        try:
            self.tray.showMessage(
                APP_NAME,
                f"Скопировано: {result}",
                QSystemTrayIcon.Information,
                1500
            )
        except Exception:
            pass

        pasted = False
        if self.unit_auto_paste and not self._units_menu_kept_open():
            pasted = self._paste_to_previous_window()

        log(f"Num→text applied: mode={self.unit_mode}, value={text_value!r}, "
            f"auto_paste={self.unit_auto_paste}, pasted={pasted}, "
            f"keep_open={self.unit_keep_menu_open}")

    def _apply_number_to_money_text(self):
        if not self._pro_soft_active():
            self._show_pro_locked_popup("Сумма текстом")
            return
        current = self._get_clipboard_text() or ""
        text_value = self._format_money_text_for_copy(current)
        if not text_value:
            try:
                self.tray.showMessage(APP_NAME, "В буфере не найдено числа", QSystemTrayIcon.Warning, 1500)
            except Exception:
                pass
            log(f"Num→money text: no number in clipboard ({current!r:.40})")
            return
        if self.unit_mode == UNIT_MODE_COPY:
            result = text_value
        else:
            if not current:
                result = text_value
            elif current[-1] in (' ', '\t', '\n', '\u00A0'):
                result = current + text_value
            else:
                result = current + ' ' + text_value
        self._set_clipboard_text(result)
        try:
            self.tray.showMessage(APP_NAME, f"Скопировано: {result}", QSystemTrayIcon.Information, 1500)
        except Exception:
            pass
        pasted = False
        if self.unit_auto_paste and not self._units_menu_kept_open():
            pasted = self._paste_to_previous_window()
        log(f"Num→money text applied: mode={self.unit_mode}, value={text_value!r}, auto_paste={self.unit_auto_paste}, pasted={pasted}")

    def _rebuild_units_menu(self):
        if not hasattr(self, "units_menu"):
            return

        self.units_menu.clear()

        # Новый режим: меню само решает закрываться или нет — по типу клика.
        # Обычный ЛКМ закрывает; ПКМ или Shift+ЛКМ — выполняет, не закрывая.
        try:
            self.units_menu.setKeepOpenOnModifier(bool(self.unit_keep_menu_open))
        except Exception:
            pass

        def _add_units_header(title: str):
            holder = QWidget()
            holder.setStyleSheet(SECTION_HEADER_QSS)
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(12, 5, 12, 5)
            lbl = QLabel(str(title).upper())
            lbl.setStyleSheet(SECTION_HEADER_LABEL_QSS)
            hl.addWidget(lbl)
            act = QWidgetAction(self)
            act.setDefaultWidget(holder)
            self.units_menu.addAction(act)

        for category, items in self.units_by_category.items():
            _add_units_header(category)

            for item in items:
                act = QAction(item["label"], self)
                act.triggered.connect(lambda _, v=item["value"]: self._apply_unit(v))
                self.units_menu.addAction(act)

            self.units_menu.addSeparator()

        actions = self.units_menu.actions()
        if actions and actions[-1].isSeparator():
            self.units_menu.removeAction(actions[-1])

        self.units_menu.addSeparator()

        # Конвертер числа из буфера в текстовое представление.
        act_n2t = QAction("Число в буфере → текст", self)
        act_n2t.setToolTip("Берёт число из буфера обмена и заменяет его "
                           "русским текстовым представлением")
        act_n2t.triggered.connect(self._apply_number_to_text)
        self.units_menu.addAction(act_n2t)

        if self._pro_soft_active():
            act_money = QAction("Число в буфере → сумма ₽ текстом", self)
            act_money.setToolTip("Преобразовать число в сумму: 100 500 (Сто тысяч пятьсот) рублей 00 копеек")
            act_money.triggered.connect(self._apply_number_to_money_text)
            self.units_menu.addAction(act_money)
        elif self._paid_items_visible():
            self.units_menu.addAction(self._locked_action("Число в буфере → сумма ₽ текстом", "Сумма текстом"))

        self.units_menu.addSeparator()

        mode_menu = QMenu("Поведение", self)
        mode_menu.setStyleSheet(MENU_QSS)

        # Радиокнопки режима через QWidgetAction — чтобы выглядели как в настройках,
        # а не маленьким Qt-индикатором. Группа радио — общая.
        self._unit_mode_buttons: list[QRadioButton] = []
        self._unit_mode_group = QButtonGroup(mode_menu)
        self._unit_mode_group.setExclusive(True)

        for label, mode in [
            ("Дописать в буфер", UNIT_MODE_APPEND),
            ("Скопировать ед. изм. в буфер", UNIT_MODE_COPY),
        ]:
            container = QWidget()
            container.setStyleSheet(TRANSPARENT_BG)
            row = QHBoxLayout(container)
            row.setContentsMargins(10, 4, 10, 4)
            row.setSpacing(6)
            rb = QRadioButton(label)
            rb.setStyleSheet(LABEL_NOTE)
            rb.setChecked(self.unit_mode == mode)
            rb.setProperty("unit_mode", mode)
            rb.toggled.connect(
                lambda checked, m=mode: (self._set_unit_mode(m) if checked else None)
            )
            self._unit_mode_group.addButton(rb)
            self._unit_mode_buttons.append(rb)
            row.addWidget(rb)
            row.addStretch(1)
            wa = QWidgetAction(self)
            wa.setDefaultWidget(container)
            mode_menu.addAction(wa)

        mode_menu.addSeparator()

        # Чекбокс «Вставлять в поле курсора» — внешне как «Результат в буфер».
        c1 = QWidget()
        c1.setStyleSheet(TRANSPARENT_BG)
        l1 = QHBoxLayout(c1)
        l1.setContentsMargins(10, 4, 10, 4)
        l1.setSpacing(6)
        self.chk_unit_auto_paste = QCheckBox("Вставлять в поле курсора (Ctrl+V)")
        self.chk_unit_auto_paste.setStyleSheet(MENU_CHECKBOX_QSS)
        self.chk_unit_auto_paste.setChecked(bool(self.unit_auto_paste))
        self.chk_unit_auto_paste.toggled.connect(self._set_unit_auto_paste_from_menu)
        l1.addWidget(self.chk_unit_auto_paste)
        l1.addStretch(1)
        wa1 = QWidgetAction(self)
        wa1.setDefaultWidget(c1)
        mode_menu.addAction(wa1)

        # Чекбокс «Не закрывать меню по ПКМ/Shift+ЛКМ».
        c2 = QWidget()
        c2.setStyleSheet(TRANSPARENT_BG)
        l2 = QHBoxLayout(c2)
        l2.setContentsMargins(10, 4, 10, 4)
        l2.setSpacing(6)
        self.chk_unit_keep_open = QCheckBox("Не закрывать меню по ПКМ/Shift+ЛКМ")
        self.chk_unit_keep_open.setStyleSheet(MENU_CHECKBOX_QSS)
        self.chk_unit_keep_open.setChecked(bool(self.unit_keep_menu_open))
        self.chk_unit_keep_open.toggled.connect(self._set_unit_keep_open_from_menu)
        l2.addWidget(self.chk_unit_keep_open)
        l2.addStretch(1)
        wa2 = QWidgetAction(self)
        wa2.setDefaultWidget(c2)
        mode_menu.addAction(wa2)

        self.units_menu.addMenu(mode_menu)

        self.units_menu.addSeparator()

        act_reload = QAction(f"Перечитать {UNITS_FILE.name}", self)
        act_reload.triggered.connect(self._reload_units_file)
        self.units_menu.addAction(act_reload)

        act_open = QAction(f"Открыть {UNITS_FILE.name}", self)
        act_open.triggered.connect(self._open_units_file)
        self.units_menu.addAction(act_open)

    # ------------------------------------------------------------------
    # Быстрые заметки
    # ------------------------------------------------------------------
    @staticmethod
    def _rtf_escape(s: str) -> str:
        out = []
        for ch in s:
            if ch in ('\\', '{', '}'):
                out.append('\\' + ch)
            elif ch == '\n':
                out.append('\\line ')
            elif ord(ch) < 128:
                out.append(ch)
            else:
                code = ord(ch)
                if code > 32767:
                    code -= 65536
                out.append(f'\\u{code}?')
        return ''.join(out)

    def _append_note(self, text: str):
        if not self._pro_soft_active():
            self._show_pro_locked_popup("Быстрая заметка")
            return False
        text = text.strip()
        if not text:
            return False
        try:
            path = Path(self.notes_path) if self.notes_path else DEFAULT_NOTES_FILE
            path.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            fmt = self.notes_format

            line_content = f"{ts}{self.notes_separator}{text}"
            if fmt == NOTE_FMT_MD:
                line = f"- {line_content}\n"
            elif fmt == NOTE_FMT_TXT:
                line = f"{line_content}\n"
            elif fmt == NOTE_FMT_RTF:
                entry = self._rtf_escape(line_content) + "\\line\n"
            else:
                return False

            prepend_newline = False
            if self.notes_newline_before and path.exists() and path.stat().st_size > 0:
                prepend_newline = True

            if fmt == NOTE_FMT_RTF:
                if path.exists():
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    idx = content.rfind('}')
                    if idx > 0:
                        if prepend_newline:
                            entry = "\\line\n" + entry
                        new_content = content[:idx] + entry + content[idx:]
                    else:
                        new_content = content + entry
                    path.write_text(new_content, encoding="utf-8")
                else:
                    header = ('{\\rtf1\\ansi\\ansicpg1251\\deff0'
                              '{\\fonttbl{\\f0\\fnil\\fcharset204 Segoe UI;}}'
                              '\\f0\\fs22\n')
                    path.write_text(header + entry + '}', encoding="utf-8")
            else:
                with open(path, "a", encoding="utf-8") as f:
                    if prepend_newline:
                        f.write("\n")
                    f.write(line)

            try:
                self.tray.showMessage(
                    APP_NAME,
                    f"Заметка → {path.name}",
                    QSystemTrayIcon.Information,
                    1200
                )
            except Exception:
                pass
            log(f"Note appended to {path.name} ({fmt}): {text[:60]!r}")
            return True
        except Exception as e:
            log(f"Append note failed: {e}")
            try:
                self.tray.showMessage(APP_NAME,
                                      f"Ошибка записи заметки:\n{e}",
                                      QSystemTrayIcon.Warning, 3000)
            except Exception:
                pass
            return False

    def _on_note_enter(self):
        if not self._pro_soft_active():
            self._show_pro_locked_popup("Быстрая заметка")
            return False if "_on_note_enter" == "_append_note" else None
        if not hasattr(self, "note_input"):
            return
        text = self.note_input.text()
        if not text.strip():
            return
        if self._append_note(text):
            self.note_input.clear()

    def _choose_notes_path(self):
        start_dir = str(Path(self.notes_path).parent) if self.notes_path else str(DATA_DIR)
        start_name = Path(self.notes_path).name if self.notes_path else f"notes.{self.notes_format}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Файл заметок",
            str(Path(start_dir) / start_name),
            "Markdown (*.md);;Text (*.txt);;Rich Text (*.rtf);;Все файлы (*)"
        )
        if not path:
            return
        self.notes_path = path
        ext = Path(path).suffix.lower().lstrip(".")
        if ext in (NOTE_FMT_MD, NOTE_FMT_TXT, NOTE_FMT_RTF):
            self.notes_format = ext
        self._save_settings()
        self._refresh_notes_label()
        log(f"Notes path: {self.notes_path}, format: {self.notes_format}")

    def _set_notes_format(self, fmt: str):
        if fmt not in (NOTE_FMT_MD, NOTE_FMT_TXT, NOTE_FMT_RTF):
            return
        self.notes_format = fmt
        if self.notes_path:
            p = Path(self.notes_path)
            cur_ext = p.suffix.lower().lstrip(".")
            if cur_ext != fmt:
                self.notes_path = str(p.with_suffix("." + fmt))
                self._refresh_notes_label()
        self._save_settings()
        log(f"Notes format: {fmt}")

    def _open_notes_file(self):
        if not self._pro_soft_active():
            self._show_pro_locked_popup("Заметки")
            return False if "_open_notes_file" == "_append_note" else None
        path = Path(self.notes_path) if self.notes_path else DEFAULT_NOTES_FILE
        try:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            os.startfile(str(path))
        except Exception as e:
            log(f"Open notes failed: {e}")

    def _open_notes_in_notepad(self):
        if not self._pro_soft_active():
            self._show_pro_locked_popup("Заметки")
            return False if "_open_notes_in_notepad" == "_append_note" else None
        """Открывает текущий файл заметок именно в Блокноте Windows.
        Не использует os.startfile(), чтобы не перехватывался внешним редактором
        по умолчанию.
        """
        path = Path(self.notes_path) if self.notes_path else DEFAULT_NOTES_FILE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.touch()
            subprocess.Popen(["notepad.exe", str(path)])
            log(f"Notes opened in notepad: {path}")
        except Exception as e:
            log(f"Open notes in notepad failed: {e}")
            try:
                self.tray.showMessage(
                    APP_NAME,
                    f"Не удалось открыть заметки в Блокноте:\n{e}",
                    QSystemTrayIcon.Warning,
                    3000
                )
            except Exception:
                pass

    def _open_notes_folder(self):
        if not self._pro_soft_active():
            self._show_pro_locked_popup("Заметки")
            return False if "_open_notes_folder" == "_append_note" else None
        path = Path(self.notes_path) if self.notes_path else DEFAULT_NOTES_FILE
        try:
            os.startfile(str(path.parent))
        except Exception as e:
            log(f"Open notes folder failed: {e}")

    def _refresh_notes_label(self):
        if hasattr(self, "note_input") and self.note_input:
            try:
                self.note_input.setPlaceholderText(
                    f"Заметка → {Path(self.notes_path).name} ({self.notes_format}) "
                    f"[{self.notes_separator}]"
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Трей
    # ------------------------------------------------------------------
    def _icon(self) -> QtGui.QIcon:
        return load_embedded_icon()

    def _build_tray(self, minimal: bool = False):
        try:
            old_tray = getattr(self, "tray", None)
            old_menu = getattr(self, "tray_menu", None)
            if old_tray is not None:
                try:
                    old_tray.setContextMenu(None)
                except Exception:
                    pass
                old_tray.hide()
                old_tray.deleteLater()
            if old_menu is not None:
                try:
                    old_menu.close()
                    old_menu.deleteLater()
                except Exception:
                    pass
        except Exception as e:
            log(f"Tray rebuild cleanup failed: {e}")
        self.tray = QSystemTrayIcon(self._icon(), self)
        self.tray.setToolTip(APP_NAME)
        self.tray_menu = self._build_main_menu(minimal=minimal, update_state=True)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _build_main_menu(self, minimal: bool = False, update_state: bool = True) -> QMenu:
        if update_state:
            self._tray_full_menu_built = not bool(minimal)
        menu = QMenu(self)
        menu.setStyleSheet(MENU_QSS)

        # --- Показать / скрыть калькулятор ---
        act_show = QAction(f"Показать / скрыть калькулятор\t{self.main_hotkey}", self)
        act_show.setIcon(self._icon())
        act_show.triggered.connect(self._do_toggle)
        menu.addAction(act_show)

        if not minimal:
            if self._pro_soft_active():
                self._add_launcher_actions(menu)
            elif self._paid_items_visible():
                menu.addMenu(self._locked_menu("Ярлыки", ["Управление ярлыками", "Хоткеи ярлыков", "Автозапуск ярлыков"]))

        # --- Управляемые окна / окна в трее ---
        if (not minimal) and self._pro_secure_active() and MANAGED_WINDOWS_AVAILABLE and self._ensure_managed_windows_loaded():
            try:
                tray_windows_menu = managed_windows.build_tray_windows_menu(self)
                if tray_windows_menu is not None:
                    menu.addMenu(tray_windows_menu)
                    menu.addSeparator()
            except Exception as e:
                log(f"managed_windows.build_tray_windows_menu failed: {e}")

        if (not minimal) and (not self._pro_secure_active()) and self._paid_items_visible():
            menu.addMenu(self._locked_menu("Окна в трей", ["Текущее окно → в трей", "Восстановить все", "Настройки окон…"]))
            menu.addSeparator()

        hotkey_widget = QWidget()
        hotkey_widget.setStyleSheet(TRANSPARENT_BG)
        hkh = QHBoxLayout(hotkey_widget)
        hkh.setContentsMargins(10, 4, 10, 4)
        hkh.setSpacing(4)
        self.act_calc_hotkey_enabled = QCheckBox(f"Обработка хоткея калькулятора: {self.main_hotkey}")
        self.act_calc_hotkey_enabled.setChecked(self.calc_hotkey_enabled)
        self.act_calc_hotkey_enabled.setStyleSheet(MENU_CHECKBOX_QSS)
        self.act_calc_hotkey_enabled.toggled.connect(lambda _checked: self._toggle_calc_hotkey_enabled())
        hkh.addWidget(self.act_calc_hotkey_enabled)
        hkh.addStretch(1)
        wa_hotkey = QWidgetAction(self)
        wa_hotkey.setDefaultWidget(hotkey_widget)
        menu.addAction(wa_hotkey)

        if minimal:
            menu.addSeparator()
            act_settings = QAction("Настройки…", self)
            act_settings.triggered.connect(self._open_settings)
            menu.addAction(act_settings)

            act_exit = QAction("Выход", self)
            act_exit.triggered.connect(self._exit)
            menu.addAction(act_exit)

            return menu

        # --- Ползунок прозрачности ---
        self.lbl_opacity = QLabel(f"Непрозрачность: {self.opacity_pct}%")
        self.lbl_opacity.setStyleSheet(LABEL_NOTE + " padding-left:2px; min-width:128px;")
        self.sld_opacity = QSlider(Qt.Horizontal)
        self.sld_opacity.setRange(0, 100)
        self.sld_opacity.setValue(self.opacity_pct)
        self.sld_opacity.setFixedWidth(110)
        self.sld_opacity.setStyleSheet(SLIDER_QSS)
        self.sld_opacity.valueChanged.connect(self._on_opacity)
        w_opacity = QWidget()
        w_opacity.setStyleSheet(TRANSPARENT_BG)
        hl = QHBoxLayout(w_opacity)
        hl.setContentsMargins(12, 5, 12, 5)
        hl.addWidget(self.lbl_opacity)
        hl.addWidget(self.sld_opacity)
        wa_opacity = QWidgetAction(self)
        wa_opacity.setDefaultWidget(w_opacity)
        menu.addAction(wa_opacity)

        menu.addSeparator()

        # --- Единицы измерения ---
        self.units_menu = SmartMenu("Единицы измерения", self)
        self.units_menu.setStyleSheet(MENU_QSS)
        self._rebuild_units_menu()
        menu.addMenu(self.units_menu)

        # --- Pro Secure: автозамена ---
        if self._pro_secure_active() and self._ensure_pro_secure_loaded():
            try:
                menu.addMenu(self._build_autoreplace_menu())
            except Exception as e:
                log(f"build_autoreplace_menu failed: {e}\n{traceback.format_exc()}")
        elif self._paid_items_visible():
            menu.addMenu(self._locked_menu("Автозамена", ["Включена", "Перечитать autoreplace.txt", "Открыть autoreplace.txt", "Настройки автозамены…"]))

        # --- Pro Secure: учёт времени, скриншоты, дневник ---
        if self._pro_secure_active() and EXTRA_AVAILABLE and self._ensure_extra_loaded():
            try:
                self.activity_menu = extra.build_tray_activity_menu(self)
                if self.activity_menu is not None:
                    menu.addMenu(self.activity_menu)
            except Exception as e:
                log(f"build_tray_activity_menu failed: {e}")

        if (not self._pro_secure_active()) and self._paid_items_visible():
            menu.addMenu(self._locked_menu("Учёт времени и активности", ["Трекинг", "Скриншоты", "Дневник"]))

        menu.addSeparator()

        if not self._pro_soft_active():
            if self._paid_items_visible():
                menu.addMenu(self._locked_menu("Быстрая заметка", ["Поле ввода заметки", "Открыть окно", "Открыть файл заметок"]))
        else:
            notes_widget = QWidget()
            notes_widget.setStyleSheet(TRANSPARENT_BG)
            nh = QHBoxLayout(notes_widget)
            nh.setContentsMargins(10, 4, 10, 4)
            nh.setSpacing(6)

            self.note_input = QLineEdit()
            self._refresh_notes_label()
            self.note_input.setStyleSheet(NOTE_INPUT_QSS)
            self.note_input.setMinimumWidth(240)
            self.note_input.returnPressed.connect(self._on_note_enter)
            nh.addWidget(self.note_input, 1)

            btn_note_more = QToolButton()
            btn_note_more.setText("…")
            btn_note_more.setToolTip("Открыть окно быстрой заметки")
            btn_note_more.setStyleSheet(TOOLBUTTON_QSS)
            btn_note_more.clicked.connect(self._show_note_popup)
            nh.addWidget(btn_note_more)

            btn_note_notepad = QToolButton()
            btn_note_notepad.setText("⏏")
            btn_note_notepad.setToolTip("Открыть файл заметок в Блокноте")
            btn_note_notepad.setFixedWidth(24)
            btn_note_notepad.setStyleSheet(TOOLBUTTON_QSS)
            btn_note_notepad.clicked.connect(self._open_notes_in_notepad)
            nh.addWidget(btn_note_notepad)

            wa_note = QWidgetAction(self)
            wa_note.setDefaultWidget(notes_widget)
            menu.addAction(wa_note)

        # --- Быстрые настройки автокопирования результата ---
        autocopy_widget = QWidget()
        autocopy_widget.setStyleSheet(TRANSPARENT_BG)
        ah = QHBoxLayout(autocopy_widget)
        ah.setContentsMargins(10, 4, 10, 4)
        ah.setSpacing(4)
        self.chk_quick_auto_copy = QCheckBox(self._quick_auto_copy_label())
        self.chk_quick_auto_copy.setChecked(_normalize_calc_clipboard_mode(
            getattr(self, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT),
            allow_money_text=self._pro_soft_active(),
        ) != CALC_CLIPBOARD_OFF)
        self.chk_quick_auto_copy.setStyleSheet(MENU_CHECKBOX_QSS)
        self.chk_quick_auto_copy.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.chk_quick_auto_copy.toggled.connect(self._set_auto_copy_on_enter_from_quick)
        ah.addWidget(self.chk_quick_auto_copy)
        if self._pro_soft_active():
            lbl_sep = QLabel("|")
            lbl_sep.setStyleSheet(LABEL_SEPARATOR)
            ah.addWidget(lbl_sep)
            lbl_prefix = QLabel("Префикс:")
            lbl_prefix.setStyleSheet(LABEL_NOTE)
            ah.addWidget(lbl_prefix)
            self.le_quick_auto_prefix = QLineEdit(self.auto_copy_prefix if self.auto_copy_prefix_enabled else "")
            self.le_quick_auto_prefix.setStyleSheet(NOTE_INPUT_QSS)
            self.le_quick_auto_prefix.setFixedWidth(25)
            self.le_quick_auto_prefix.textChanged.connect(self._on_quick_auto_copy_affix_changed)
            ah.addWidget(self.le_quick_auto_prefix)
            lbl_suffix = QLabel("Суффикс:")
            lbl_suffix.setStyleSheet(LABEL_NOTE)
            ah.addWidget(lbl_suffix)
            self.le_quick_auto_suffix = QLineEdit(self.auto_copy_suffix if self.auto_copy_suffix_enabled else "")
            self.le_quick_auto_suffix.setStyleSheet(NOTE_INPUT_QSS)
            self.le_quick_auto_suffix.setFixedWidth(25)
            self.le_quick_auto_suffix.textChanged.connect(self._on_quick_auto_copy_affix_changed)
            ah.addWidget(self.le_quick_auto_suffix)
            btn_auto_reset = QPushButton("✕")
            btn_auto_reset.setFixedSize(26, 26)
            btn_auto_reset.setStyleSheet(RESET_BUTTON_QSS)
            btn_auto_reset.setToolTip("Очистить префикс и суффикс. Автокопирование не выключается.")
            btn_auto_reset.clicked.connect(self._reset_quick_auto_copy_affixes)
            ah.addWidget(btn_auto_reset)
        elif self._paid_items_visible():
            ah.addWidget(QLabel("|"))
            b_affix = QPushButton("🔒 Префикс/суффикс")
            b_affix.clicked.connect(lambda: self._show_pro_locked_popup("Префикс и суффикс"))
            ah.addWidget(b_affix)
        ah.addStretch(1)
        wa_autocopy = QWidgetAction(self)
        wa_autocopy.setDefaultWidget(autocopy_widget)
        menu.addAction(wa_autocopy)

        menu.addSeparator()

        # --- Настройки / О программе / Выход ---
        act_settings = QAction("Настройки…", self)
        act_settings.triggered.connect(self._open_settings)
        menu.addAction(act_settings)

        act_about = QAction("О программе…", self)
        act_about.triggered.connect(lambda: AboutDialog(self).exec_())
        menu.addAction(act_about)

        act_exit = QAction("Выход", self)
        act_exit.triggered.connect(self._exit)
        menu.addAction(act_exit)

        return menu

    def _build_calculator_context_menu(self):
        # ПКМ калькулятора получает отдельный QMenu, но builder основного меню
        # обновляет ссылки на живые виджеты. Сохраняем ссылки tray-меню и
        # возвращаем их после закрытия контекстного меню, иначе один правый клик
        # превращает self.units_menu и quick widgets в указатели на удалённые объекты.
        names = (
            "act_calc_hotkey_enabled", "lbl_opacity", "sld_opacity",
            "units_menu", "_unit_mode_buttons", "activity_menu",
            "pause_menu", "diary_pause_menu", "act_activity_enabled",
            "act_shot_enabled", "act_diary_enabled", "note_input",
            "chk_quick_auto_copy", "le_quick_auto_prefix",
            "le_quick_auto_suffix",
        )
        saved = {name: getattr(self, name, None) for name in names}
        existed = {name: hasattr(self, name) for name in names}
        was_full = bool(getattr(self, "_tray_full_menu_built", False))
        menu = self._build_main_menu(minimal=False, update_state=False)

        restored = {"done": False}

        def _restore_context_refs(*_args):
            if restored["done"]:
                return
            restored["done"] = True
            self._tray_full_menu_built = was_full
            for name in names:
                if existed[name]:
                    setattr(self, name, saved[name])
                else:
                    try:
                        delattr(self, name)
                    except AttributeError:
                        pass

        try:
            menu.aboutToHide.connect(_restore_context_refs)
            menu.destroyed.connect(_restore_context_refs)
        except Exception:
            pass
        return menu

    def _rebuild_tray_ui(self):
        if getattr(self, "_tray_rebuild_pending", False):
            return
        self._tray_rebuild_pending = True

        def _do_rebuild():
            self._tray_rebuild_pending = False
            try:
                self._build_tray(minimal=not bool(getattr(self, "_tray_full_menu_built", True)))
            except Exception as e:
                log(f"Tray rebuild failed: {e}")

        QTimer.singleShot(0, _do_rebuild)

    def _launcher_hint(self, item: dict) -> str:
        try:
            if item.get("taskbar_pinned") and int(item.get("taskbar_index", 0)):
                return f"Win+{int(item.get('taskbar_index'))}"
        except Exception:
            pass
        return str(item.get("hotkey", "") or "").strip()

    def _launcher_icon(self, item: dict) -> QtGui.QIcon:
        custom = str(item.get("custom_icon_path", "") or "").strip()
        if custom and Path(custom).exists():
            ico = QtGui.QIcon(custom)
            if not ico.isNull():
                return ico
        path = str(item.get("path", "") or "").strip()
        if path and Path(path).exists():
            try:
                provider = QFileIconProvider()
                ico = provider.icon(QFileInfo(path))
                if not ico.isNull():
                    return ico
            except Exception:
                pass
        return self._icon()

    def _add_launcher_actions(self, menu):
        added = False
        for item in list(getattr(self, "launcher_apps", []) or []):
            if not item.get("enabled", True) or not item.get("show_in_tray", True):
                continue
            title = str(item.get("title", "") or "").strip() or Path(str(item.get("path", "") or "")).stem or "Программа"
            hint = self._launcher_hint(item)
            text = f"{title}\t{hint}" if hint else title
            act = QAction(text, self)
            act.setIcon(self._launcher_icon(item))
            act.triggered.connect(lambda _, cfg=dict(item): self._launch_launcher_app(cfg))
            menu.addAction(act)
            added = True
        if added:
            menu.addSeparator()

    def _find_launcher_hwnd(self, item: dict):
        path = str(item.get("path", "") or "").strip()
        if not path:
            return 0
        try:
            suffix = Path(path).suffix.lower()
            # Для .exe ищем окно по имени процесса. Для .lnk/.bat/.cmd/.ps1
            # надёжно определить целевой exe без COM-разбора нельзя.
            if suffix == ".exe":
                return find_hwnd_by_exe(Path(path).name.lower())
        except Exception:
            return 0
        return 0

    def _activate_launcher_hwnd(self, hwnd) -> bool:
        if not hwnd:
            return False
        try:
            ShowWindow(hwnd, SW_RESTORE)
            ShowWindow(hwnd, SW_SHOW)
            _force_foreground(hwnd)
            return True
        except Exception as e:
            log(f"Launcher activate failed: hwnd={hwnd}: {e}")
            return False

    def _launch_launcher_app(self, item: dict):
        if not self._pro_soft_active():
            self._show_pro_locked_popup("Ярлыки")
            return
        path = str(item.get("path", "") or "").strip()
        args = str(item.get("args", "") or "").strip()
        if not path:
            return
        try:
            hwnd = self._find_launcher_hwnd(item)
            if hwnd and self._activate_launcher_hwnd(hwnd):
                log(f"Launcher activated existing window: {path}, hwnd={hwnd}")
                return

            suffix = Path(path).suffix.lower()
            if suffix in (".lnk", ".bat", ".cmd", ".ps1"):
                # Для ярлыков и командных файлов Windows сама выбирает обработчик.
                os.startfile(path)
                log(f"Launcher startfile: {path}")
                return
            cmd = [path]
            if args:
                try:
                    cmd += shlex.split(args, posix=False)
                except Exception:
                    cmd += args.split()
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
            log(f"Launcher started: {cmd}")
        except Exception as e:
            log(f"Launcher failed: {path}: {e}")
            try:
                self.tray.showMessage(APP_NAME, f"Не удалось запустить:\n{path}\n{e}",
                                      QSystemTrayIcon.Warning, 3000)
            except Exception:
                pass

    def _launch_startup_apps(self):
        for item in list(getattr(self, "launcher_apps", []) or []):
            if item.get("enabled", True) and item.get("open_on_start", False):
                self._launch_launcher_app(item)

    def _open_calc_on_start_if_needed(self, mark: bool = True):
        try:
            arg_open = any(str(x).strip().lower() in {"--open-calc", "/open-calc", "--calculator", "/calculator"} for x in sys.argv[1:])
            if not (bool(getattr(self, "calc_open_on_start", False)) or arg_open):
                return
            if self._using_builtin_calc():
                w = self._ensure_builtin_calc()
                if w is not None and w.isVisible() and not w.isMinimized():
                    return
            else:
                hwnd = self._find_target_hwnd()
                if hwnd and bool(IsWindowVisible(hwnd)) and not bool(IsIconic(hwnd)):
                    return
            if mark:
                self._startup_mark("CALC_OPEN_BEGIN: delayed")
            self._do_toggle()
            if mark:
                self._startup_mark("CALC_READY: delayed")
        except Exception as e:
            log(f"Open calculator on start failed: {e}")

    def _keyboard_hook_needed(self) -> bool:
        if _normalize_calc_clipboard_mode(
            getattr(self, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT),
            allow_money_text=self._pro_soft_active(),
        ) != CALC_CLIPBOARD_OFF:
            return True
        if self._pro_secure_active():
            if bool(getattr(self, "autoreplace_enabled", False)):
                return True
            if bool(getattr(self, "diary_enabled", False)):
                return True
        return False

    def _unregister_keyboard_hook(self, reason: str = ""):
        if not globals().get("KEYBOARD_AVAILABLE", True) or keyboard is None:
            self._keyboard_on_press_hook = None
            return
        old_hook = getattr(self, "_keyboard_on_press_hook", None)
        if old_hook is None:
            return
        try:
            keyboard.unhook(old_hook)
            log(f"Keyboard hook unregistered ({reason or 'manual'})")
        except Exception as e:
            log(f"Keyboard hook unregister failed ({reason or 'manual'}): {e}")
        finally:
            self._keyboard_on_press_hook = None

    def _register_keyboard_hook(self, reason: str = ""):
        if not globals().get("KEYBOARD_AVAILABLE", True) or keyboard is None:
            try:
                log(f"Keyboard hook skipped ({reason or 'manual'}): keyboard unavailable: {globals().get('KEYBOARD_IMPORT_ERROR', '')}")
            except Exception:
                pass
            return
        try:
            self._unregister_keyboard_hook(reason=reason or "manual")
            if not self._keyboard_hook_needed():
                log(f"Keyboard hook skipped ({reason or 'manual'}): no active feature")
                return
            self._keyboard_on_press_hook = keyboard.on_press(self._on_key)
            log(f"Keyboard hook registered ({reason or 'manual'})")
        except Exception as e:
            self._keyboard_on_press_hook = None
            log(f"Keyboard hook failed ({reason or 'manual'}): {e}")

    def _pause_keyboard_listening_for_system_event(self, reason: str) -> None:
        try:
            log(f"Keyboard listening pause started ({reason})")
            self._unregister_keyboard_hook(reason=reason)
            try:
                if self._note_popup_hotkey_handle is not None:
                    keyboard.remove_hotkey(self._note_popup_hotkey_handle)
                    self._note_popup_hotkey_handle = None
            except Exception:
                pass
            self._unregister_calc_hotkeys()
            self._unregister_launcher_hotkeys()
            log(f"Keyboard listening paused ({reason})")
        except Exception as e:
            log(f"Keyboard listening pause failed ({reason}): {e}")

    def _recover_hotkeys_after_resume(self, reason: str = "resume", *, force: bool = False):
        try:
            now = time.monotonic()
            if not force and now - float(getattr(self, "_keyboard_last_recovery_ts", 0.0) or 0.0) < 3.0:
                log(f"Hotkey recovery skipped ({reason}): throttled")
                return
            self._keyboard_last_recovery_ts = now
            log(f"Hotkey recovery started ({reason})")
            self._register_keyboard_hook(reason=reason)
            if self._pro_soft_active():
                self._register_note_popup_hotkey()
            self._register_calc_hotkeys()
            if self._pro_soft_active():
                self._register_launcher_hotkeys()
            log(f"Hotkey recovery finished ({reason}); calc_handles={len(getattr(self, 'calc_hotkey_handles', []) or [])}, launcher_handles={len(getattr(self, 'launcher_hotkey_handles', []) or [])}")
        except Exception as e:
            log(f"Hotkey recovery failed ({reason}): {e}\n{traceback.format_exc()}")

    def _register_session_notifications(self) -> None:
        if not sys.platform.startswith("win"):
            return
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return
            NOTIFY_FOR_THIS_SESSION = 0
            ok = ctypes.windll.wtsapi32.WTSRegisterSessionNotification(
                wintypes.HWND(hwnd),
                wintypes.DWORD(NOTIFY_FOR_THIS_SESSION),
            )
            self._session_notifications_registered = bool(ok)
            if ok:
                log("WTS session notifications registered")
        except Exception as e:
            self._session_notifications_registered = False
            log(f"WTS session notifications register failed: {e}")

    def _unregister_session_notifications(self) -> None:
        if not sys.platform.startswith("win"):
            return
        if not bool(getattr(self, "_session_notifications_registered", False)):
            return
        try:
            ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification(wintypes.HWND(int(self.winId())))
            log("WTS session notifications unregistered")
        except Exception as e:
            log(f"WTS session notifications unregister failed: {e}")
        finally:
            self._session_notifications_registered = False

    def _poll_keyboard_recovery_watchdog(self) -> None:
        if not bool(getattr(self, "running", False)) or not bool(getattr(self, "_startup_ready", False)):
            return
        try:
            idle_sec = float(get_idle_seconds())
        except Exception as e:
            log(f"Keyboard watchdog idle check failed: {e}")
            idle_sec = 0.0

        if idle_sec >= KEYBOARD_IDLE_RECOVERY_SEC:
            if not bool(getattr(self, "_keyboard_idle_recovery_done", False)):
                self._keyboard_idle_recovery_done = True
                self._recover_hotkeys_after_resume("idle_over_30min", force=True)
            return

        if bool(getattr(self, "_keyboard_idle_recovery_done", False)):
            self._keyboard_idle_recovery_done = False
            self._recover_hotkeys_after_resume("idle_return_after_30min", force=True)
            return

        try:
            if self._keyboard_hook_needed() and getattr(self, "_keyboard_on_press_hook", None) is None:
                self._register_keyboard_hook(reason="watchdog_missing_hook")
        except Exception as e:
            log(f"Keyboard watchdog hook check failed: {e}")

        try:
            if globals().get("KEYBOARD_AVAILABLE", True) and keyboard is not None:
                if not getattr(self, "calc_hotkey_handles", None):
                    self._register_calc_hotkeys()
                if self._pro_soft_active() and self.note_popup_enabled and self._note_popup_hotkey_handle is None:
                    self._register_note_popup_hotkey()
                if self._pro_soft_active() and getattr(self, "launcher_apps", None) and not getattr(self, "launcher_hotkey_handles", None):
                    self._register_launcher_hotkeys()
        except Exception as e:
            log(f"Keyboard watchdog hotkey check failed: {e}")

    def nativeEvent(self, eventType, message):
        try:
            msg = wintypes.MSG.from_address(int(message))
            WM_POWERBROADCAST = 0x0218
            WM_WTSSESSION_CHANGE = 0x02B1
            PBT_APMSUSPEND = 0x0004
            PBT_APMRESUMECRITICAL = 0x0006
            PBT_APMRESUMESUSPEND = 0x0007
            PBT_APMRESUMEAUTOMATIC = 0x0012
            WTS_CONSOLE_CONNECT = 0x1
            WTS_CONSOLE_DISCONNECT = 0x2
            WTS_REMOTE_CONNECT = 0x3
            WTS_REMOTE_DISCONNECT = 0x4
            WTS_SESSION_LOCK = 0x7
            WTS_SESSION_UNLOCK = 0x8
            if msg.message == WM_POWERBROADCAST:
                code = int(msg.wParam)
                if code == PBT_APMSUSPEND:
                    log("Power event: suspend; pausing keyboard listening")
                    self._pause_keyboard_listening_for_system_event("power_suspend")
                elif code in (PBT_APMRESUMECRITICAL, PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC):
                    log(f"Power event: resume code={code}; scheduling hotkey recovery")
                    QTimer.singleShot(800, lambda: self._recover_hotkeys_after_resume("power_resume_800ms", force=True))
                    QTimer.singleShot(2500, lambda: self._recover_hotkeys_after_resume("power_resume_2500ms"))
            elif msg.message == WM_WTSSESSION_CHANGE:
                code = int(msg.wParam)
                if code in (WTS_SESSION_LOCK, WTS_CONSOLE_DISCONNECT, WTS_REMOTE_DISCONNECT):
                    log(f"Session event: pause code={code}")
                    self._pause_keyboard_listening_for_system_event(f"session_pause_{code}")
                elif code in (WTS_SESSION_UNLOCK, WTS_CONSOLE_CONNECT, WTS_REMOTE_CONNECT):
                    log(f"Session event: resume code={code}; scheduling hotkey recovery")
                    QTimer.singleShot(500, lambda c=code: self._recover_hotkeys_after_resume(f"session_resume_{c}", force=True))
                    QTimer.singleShot(1800, lambda c=code: self._recover_hotkeys_after_resume(f"session_resume_late_{c}"))
        except Exception as e:
            try:
                log(f"nativeEvent power/session handler failed: {e}")
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def _unregister_calc_hotkeys(self):
        if not globals().get("KEYBOARD_AVAILABLE", True) or keyboard is None:
            self.calc_hotkey_handles = []
            return
        for h in list(getattr(self, "calc_hotkey_handles", []) or []):
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
        self.calc_hotkey_handles = []

    def _register_calc_hotkeys(self, primary_only: bool = False):
        if not globals().get("KEYBOARD_AVAILABLE", True) or keyboard is None:
            try:
                log(f"Calc hotkeys skipped: keyboard unavailable: {globals().get('KEYBOARD_IMPORT_ERROR', '')}")
            except Exception:
                pass
            return
        self._unregister_calc_hotkeys()
        main_hk = (getattr(self, "main_hotkey", "num lock") or "num lock").strip().lower()
        pause_hk = (getattr(self, "calc_pause_hotkey", "shift+num lock") or "shift+num lock").strip().lower()
        used = set()
        if main_hk:
            try:
                h = keyboard.add_hotkey(
                    main_hk,
                    self._handle_calc_toggle_hotkey,
                    suppress=False,
                    trigger_on_release=False,
                )
                self.calc_hotkey_handles.append(h)
                used.add(main_hk)
                log(f"Calc toggle hotkey registered: {main_hk}")
            except Exception as e:
                log(f"Calc toggle hotkey register failed ({main_hk!r}): {e}")
        if primary_only:
            return
        if pause_hk and pause_hk not in used:
            try:
                h = keyboard.add_hotkey(
                    pause_hk,
                    self._handle_calc_pause_hotkey,
                    suppress=False,
                    trigger_on_release=False,
                )
                self.calc_hotkey_handles.append(h)
                log(f"Calc pause hotkey registered: {pause_hk}")
            except Exception as e:
                log(f"Calc pause hotkey register failed ({pause_hk!r}): {e}")

    def _hotkey_delay_blocked(self) -> bool:
        now = time.time()
        delay = float(getattr(self, "main_hotkey_delay_sec", 0.15) or 0.0)
        if now - self._last_toggle < delay:
            return True
        self._last_toggle = now
        return False

    def _handle_calc_toggle_hotkey(self):
        if not self.running:
            return
        # При дефолтной паре num lock / shift+num lock не даём Shift+NumLock
        # одновременно вызвать и паузу, и открытие калькулятора.
        try:
            if (self.main_hotkey or "").strip().lower() == "num lock" and \
                    (self.calc_pause_hotkey or "").strip().lower() == "shift+num lock" and \
                    keyboard.is_pressed("shift"):
                return
        except Exception:
            pass
        if self._hotkey_delay_blocked():
            return
        if not self.calc_hotkey_enabled:
            return
        if not getattr(self, "_startup_ready", False):
            self._pending_startup_toggle = True
            return
        self._sig_toggle.emit()

    def _handle_calc_pause_hotkey(self):
        if not self.running:
            return
        if self._hotkey_delay_blocked():
            return
        self._sig_calc_pause_toggle.emit()

    def _toggle_calc_hotkey_enabled_from_hotkey(self):
        self.calc_hotkey_enabled = not bool(self.calc_hotkey_enabled)
        if hasattr(self, "act_calc_hotkey_enabled"):
            self.act_calc_hotkey_enabled.blockSignals(True)
            self.act_calc_hotkey_enabled.setChecked(self.calc_hotkey_enabled)
            self.act_calc_hotkey_enabled.blockSignals(False)
        self._save_settings()
        log(f"Calc hotkey enabled by pause hotkey: {self.calc_hotkey_enabled}")

    def _unregister_launcher_hotkeys(self):
        for h in list(getattr(self, "launcher_hotkey_handles", []) or []):
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
        self.launcher_hotkey_handles = []

    def _register_launcher_hotkeys(self):
        self._unregister_launcher_hotkeys()
        if not self._pro_soft_active():
            return
        used = set()
        note_hk = (self.note_popup_hotkey or "").strip().lower()
        main_hk = (self.main_hotkey or "num lock").strip().lower()
        for item in list(getattr(self, "launcher_apps", []) or []):
            if not item.get("enabled", True):
                continue
            hk = str(item.get("hotkey", "") or "").strip().lower()
            if not hk:
                continue
            if hk in used or hk == note_hk or hk == main_hk:
                log(f"Launcher hotkey skipped because of conflict: {hk}")
                continue
            try:
                handle = keyboard.add_hotkey(
                    hk,
                    lambda cfg=dict(item): self._launch_launcher_app(cfg),
                    suppress=False,
                    trigger_on_release=False,
                )
                self.launcher_hotkey_handles.append(handle)
                used.add(hk)
                log(f"Launcher hotkey registered: {hk}")
            except Exception as e:
                log(f"Launcher hotkey register failed ({hk!r}): {e}")

    def _toggle_auto_copy_on_enter(self):
        if _normalize_calc_clipboard_mode(
            getattr(self, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT),
            allow_money_text=self._pro_soft_active(),
        ) == CALC_CLIPBOARD_OFF:
            self.calc_clipboard_mode = CALC_CLIPBOARD_RESULT
        else:
            self.calc_clipboard_mode = CALC_CLIPBOARD_OFF
        self.auto_copy_on_enter = self.calc_clipboard_mode != CALC_CLIPBOARD_OFF
        self.auto_copy_mode = self.calc_clipboard_mode
        self._sync_auto_copy_quick_widgets()
        self._save_settings()
        self._register_keyboard_hook(reason="auto_copy_toggle")
        log(f"Auto copy mode: {self.calc_clipboard_mode}; enabled={self.auto_copy_on_enter}")

    def _set_auto_copy_on_enter_from_quick(self, checked: bool):
        if checked:
            if _normalize_calc_clipboard_mode(
                getattr(self, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT),
                allow_money_text=self._pro_soft_active(),
            ) == CALC_CLIPBOARD_OFF:
                self.calc_clipboard_mode = CALC_CLIPBOARD_RESULT
        else:
            self.calc_clipboard_mode = CALC_CLIPBOARD_OFF
        self.auto_copy_on_enter = self.calc_clipboard_mode != CALC_CLIPBOARD_OFF
        self.auto_copy_mode = self.calc_clipboard_mode
        self._sync_auto_copy_quick_widgets()
        try:
            if getattr(self, "_builtin_calc_window", None) is not None:
                self._builtin_calc_window.set_clipboard_mode(self.calc_clipboard_mode, notify=False)
        except Exception as e:
            log(f"Sync builtin calc copy mode failed: {e}")
        self._save_settings()
        self._register_keyboard_hook(reason="auto_copy_quick")
        log(f"Auto copy mode: {self.calc_clipboard_mode}; enabled={self.auto_copy_on_enter}")

    def _on_quick_auto_copy_affix_changed(self):
        if hasattr(self, "le_quick_auto_prefix"):
            self.auto_copy_prefix = self.le_quick_auto_prefix.text()
            self.auto_copy_prefix_enabled = bool(self.auto_copy_prefix)
        if hasattr(self, "le_quick_auto_suffix"):
            self.auto_copy_suffix = self.le_quick_auto_suffix.text()
            self.auto_copy_suffix_enabled = bool(self.auto_copy_suffix)
        self._save_settings()
        self._save_pro_soft_settings()
        log(
            "Auto copy affixes changed: "
            f"prefix_enabled={self.auto_copy_prefix_enabled}, "
            f"suffix_enabled={self.auto_copy_suffix_enabled}"
        )

    def _reset_quick_auto_copy_affixes(self):
        self.auto_copy_prefix = ""
        self.auto_copy_suffix = ""
        self.auto_copy_prefix_enabled = False
        self.auto_copy_suffix_enabled = False

        for name in ("le_quick_auto_prefix", "le_quick_auto_suffix"):
            if hasattr(self, name):
                w = getattr(self, name)
                try:
                    w.blockSignals(True)
                    w.clear()
                finally:
                    w.blockSignals(False)

        self._save_settings()
        self._save_pro_soft_settings()
        log("Auto copy affixes reset")

    def _quick_auto_copy_label(self) -> str:
        mode = _normalize_calc_clipboard_mode(
            getattr(self, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT),
            allow_money_text=self._pro_soft_active(),
        )
        if mode == CALC_CLIPBOARD_TEXT:
            return "Результат в буфер: Tx"
        if mode == CALC_CLIPBOARD_MONEY_TEXT:
            return "Результат в буфер: ₽т"
        return "Результат в буфер"

    def _sync_auto_copy_quick_widgets(self):
        if hasattr(self, "chk_quick_auto_copy"):
            try:
                self.chk_quick_auto_copy.blockSignals(True)
                mode = _normalize_calc_clipboard_mode(
                    getattr(self, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT),
                    allow_money_text=self._pro_soft_active(),
                )
                self.chk_quick_auto_copy.setChecked(mode != CALC_CLIPBOARD_OFF)
                self.chk_quick_auto_copy.setText(self._quick_auto_copy_label())
            finally:
                self.chk_quick_auto_copy.blockSignals(False)
        if hasattr(self, "le_quick_auto_prefix"):
            try:
                self.le_quick_auto_prefix.blockSignals(True)
                self.le_quick_auto_prefix.setText(self.auto_copy_prefix if self.auto_copy_prefix_enabled else "")
            finally:
                self.le_quick_auto_prefix.blockSignals(False)
        if hasattr(self, "le_quick_auto_suffix"):
            try:
                self.le_quick_auto_suffix.blockSignals(True)
                self.le_quick_auto_suffix.setText(self.auto_copy_suffix if self.auto_copy_suffix_enabled else "")
            finally:
                self.le_quick_auto_suffix.blockSignals(False)

    def _open_extra_settings_file(self):
        if not (EXTRA_AVAILABLE and self._ensure_extra_loaded()):
            return
        try:
            path = getattr(extra, "EXTRA_SETTINGS_FILE", None)
            if path is None:
                return
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                try:
                    extra.save_settings(self)
                except Exception:
                    p.write_text("{}", encoding="utf-8")
            os.startfile(str(p))
        except Exception as e:
            log(f"Open Pro Secure settings failed: {e}")

    def _open_settings(self, *args):
        # Donor stable opening path: create and exec a fresh modal dialog.
        # No cached dialog, no manual top-level show/raise, no extra wrapper.
        try:
            if not getattr(self, "units_by_category", None):
                self._load_units_file()
        except Exception as e:
            log(f"Load units before settings failed: {e}\n{traceback.format_exc()}")
        try:
            if self._pro_secure_active() and EXTRA_AVAILABLE:
                self._load_extra_settings_deferred()
        except Exception as e:
            log(f"Load extra before settings failed: {e}\n{traceback.format_exc()}")
        try:
            if self._pro_secure_active() and MANAGED_WINDOWS_AVAILABLE:
                self._init_managed_windows_deferred()
        except Exception as e:
            log(f"Load managed_windows before settings failed: {e}\n{traceback.format_exc()}")
        try:
            dlg = SettingsDialog(self)
            try:
                dlg.setWindowIcon(self._icon())
            except Exception:
                pass
            dlg.exec_()
        except Exception as e:
            log(f"Open settings failed: {e}\n{traceback.format_exc()}")
            try:
                QMessageBox.critical(None, APP_NAME, f"Не удалось открыть настройки: {e}")
            except Exception:
                pass

    def _poll_foreground(self):
        try:
            hwnd = GetForegroundWindow()
            if not hwnd:
                return
            pid = wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == self._our_pid:
                return
            cls = _get_class(hwnd)
            if cls in (
                "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                "NotifyIconOverflowWindow", "TrayNotifyWnd",
                "Progman", "WorkerW",
                "Windows.UI.Core.CoreWindow",
                "MultitaskingViewFrame",
            ):
                return
            self._last_user_hwnd = hwnd
            try:
                if self.diary is not None:
                    self.diary.on_window_change(hwnd)
            except Exception:
                pass
        except Exception:
            pass

    def _on_tray_activated(self, reason):
        # ЛКМ — показать/скрыть калькулятор
        if reason == QSystemTrayIcon.Trigger:
            self._do_toggle()
        # ПКМ — контекстное меню (обрабатывается Qt через setContextMenu автоматически)



    def _calculator_foreground_info(self):
        """Возвращает (ok, hwnd, exe, cls, title) для активного окна калькулятора.
        Вынесено отдельно, чтобы автокопирование логировало, что именно видит Windows.
        """
        try:
            hwnd = GetForegroundWindow()
            if not hwnd:
                return False, 0, "", "", ""
            title = (_get_text(hwnd) or "")
            cls = (_get_class(hwnd) or "")
            exe = (_exe_basename_of_hwnd(hwnd) or "").lower()
            title_l = title.lower()
            custom_base = self._custom_exe_basename()
            ok = False
            if custom_base and exe == custom_base:
                ok = True
            elif exe in ("calculatorapp.exe", "calc.exe"):
                ok = True
            elif cls == CALC_CLASS:
                ok = True
            elif any(str(t).lower() in title_l for t in CALC_TITLES):
                ok = True
            return ok, hwnd, exe, cls, title
        except Exception as e:
            log(f"Auto copy foreground check failed: {e}")
            return False, 0, "", "", ""

    def _is_calculator_foreground(self) -> bool:
        ok, _hwnd, _exe, _cls, _title = self._calculator_foreground_info()
        return ok

    def _on_builtin_calc_clipboard_mode_changed(self, mode: str) -> None:
        self.calc_clipboard_mode = _normalize_calc_clipboard_mode(
            mode,
            allow_money_text=self._pro_soft_active(),
        )
        self.auto_copy_on_enter = self.calc_clipboard_mode != CALC_CLIPBOARD_OFF
        self.auto_copy_mode = self.calc_clipboard_mode
        self._sync_auto_copy_quick_widgets()
        self._register_keyboard_hook(reason="builtin_calc_copy_mode")
        try:
            self._save_settings()
        except Exception as e:
            log(f"Save calc clipboard mode failed: {e}")

    def _format_money_text_for_copy(self, text: str) -> str:
        raw = str(text or "")
        if not (self._pro_soft_active() and self._ensure_pro_soft_loaded()):
            return ""
        try:
            money_format = str(
                getattr(self, "money_text_format", "")
                or ("number_parentheses" if bool(getattr(self, "money_text_parentheses", True)) else "number_plain")
            )
            kopecks_mode = str(
                getattr(self, "money_text_kopecks", "")
                or getattr(self, "money_text_kopecks_mode", "digits")
                or "digits"
            )
            return pro_soft.format_money_text(raw, money_format, kopecks_mode) or ""
        except Exception as e:
            log(f"Format money text failed: {e}")
        return ""

    def _format_calc_result_for_clipboard(self, text: str) -> str:
        raw = str(text or "")
        mode = _normalize_calc_clipboard_mode(
            getattr(self, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT),
            allow_money_text=self._pro_soft_active(),
        )
        if mode == CALC_CLIPBOARD_OFF:
            return ""
        if mode == CALC_CLIPBOARD_TEXT:
            return _capitalize_first_letter(number_to_russian_text(raw) or raw)
        if mode == CALC_CLIPBOARD_MONEY_TEXT:
            return _capitalize_first_letter(self._format_money_text_for_copy(raw) or raw)
        return raw

    def _apply_auto_copy_affixes(self, text: str) -> str:
        result = str(text or "")
        if self._pro_soft_active() and self.auto_copy_prefix_enabled and self.auto_copy_prefix:
            result = f"{self.auto_copy_prefix}{result}"
        if self._pro_soft_active() and self.auto_copy_suffix_enabled and self.auto_copy_suffix:
            result = f"{result}{self.auto_copy_suffix}"
        return result

    def _format_calc_clipboard_text(self, text: str) -> str:
        formatted = self._format_calc_result_for_clipboard(text)
        if not formatted:
            return ""
        return self._apply_auto_copy_affixes(formatted)

    def _on_enter_for_calc_copy(self):
        mode = _normalize_calc_clipboard_mode(
            getattr(self, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT),
            allow_money_text=self._pro_soft_active(),
        )
        if mode == CALC_CLIPBOARD_OFF:
            return
        ok, hwnd, exe, cls, title = self._calculator_foreground_info()
        if not ok:
            log(f"Auto copy skipped: active is not calculator; exe={exe!r}, cls={cls!r}, title={title[:80]!r}")
            return
        delay = max(0, int(getattr(self, "auto_copy_enter_delay_ms", 120)))
        log(
            f"Auto copy request from keyboard thread: {delay} ms; "
            f"hwnd={hwnd}, exe={exe!r}, cls={cls!r}, title={title[:80]!r}"
        )
        # Важно: keyboard.on_press вызывает этот метод не из главного Qt-потока.
        # Поэтому QTimer.singleShot здесь ненадёжен. Перекидываем в Qt-поток.
        self._sig_auto_copy_request.emit(int(hwnd), int(delay))

    def _schedule_auto_copy_in_main_thread(self, hwnd: int, delay: int):
        log(f"Auto copy scheduled in Qt thread: {delay} ms; hwnd={hwnd}")
        QTimer.singleShot(max(0, int(delay)), lambda hwnd=int(hwnd): self._copy_from_calculator_hwnd(hwnd))

    def _copy_from_calculator_hwnd(self, hwnd: int):
        """Копирует результат из окна калькулятора, активного при Enter.
        v6: без служебного marker в буфере. Проверяем факт копирования
        через GetClipboardSequenceNumber и/или изменение текста буфера.
        """
        try:
            if not hwnd or not user32.IsWindow(hwnd):
                log(f"Auto copy failed: calculator hwnd is gone: {hwnd}")
                return

            title = (_get_text(hwnd) or "")
            exe = (_exe_basename_of_hwnd(hwnd) or "").lower()
            cls = (_get_class(hwnd) or "")

            # Встроенный калькулятор: не гоняем Ctrl+C через SendInput, берём дисплей напрямую.
            try:
                w = getattr(self, "_builtin_calc_window", None)
                if w is not None and int(hwnd) == int(w.winId()) and hasattr(w, "current_copy_text"):
                    text = w.current_copy_text() or ""
                    if not text:
                        log("Auto copy builtin skipped: empty display text")
                        return
                    QApplication.clipboard().setText(text)
                    log(f"Auto copy builtin OK: {text!r}; hwnd={hwnd}")
                    return
            except Exception as e:
                log(f"Auto copy builtin direct failed: {e}")

            ok_fg = _force_foreground(hwnd)
            time.sleep(0.08)

            cb = QApplication.clipboard()
            old_text = cb.text() or ""
            old_seq = self._clipboard_sequence()

            # ВАЖНО: ничего временного в буфер не пишем.
            # Только отправляем Ctrl+C активному калькулятору.
            ok_keyboard = False
            ok_sendinput = _send_ctrl_c()
            text, new_seq, changed = self._wait_clipboard_after_copy(
                old_text=old_text,
                old_seq=old_seq,
                timeout_ms=900,
            )

            if not changed or not text:
                log(
                    "Auto copy failed v6: clipboard was not updated after SendInput ctrl+c; "
                    f"fg={ok_fg}, keyboard={ok_keyboard}, sendinput={ok_sendinput}, "
                    f"old_seq={old_seq}, new_seq={new_seq}, "
                    f"hwnd={hwnd}, exe={exe!r}, cls={cls!r}, title={title[:80]!r}"
                )
                return

            text = self._format_calc_result_for_clipboard(text)
            text = self._apply_auto_copy_affixes(text)
            cb.setText(text)
            log(
                "Auto copy OK v6: "
                f"{text!r}; fg={ok_fg}, keyboard={ok_keyboard}, sendinput={ok_sendinput}, "
                f"old_seq={old_seq}, new_seq={new_seq}, "
                f"hwnd={hwnd}, exe={exe!r}, cls={cls!r}, title={title[:80]!r}"
            )
        except Exception as e:
            log(f"Auto copy failed with exception: {e}")

    def _clipboard_sequence(self) -> int:
        """Возвращает системный номер изменения буфера Windows.
        Если API недоступен — 0. Ничего в буфер не пишет.
        """
        try:
            return int(user32.GetClipboardSequenceNumber())
        except Exception:
            return 0

    def _wait_clipboard_after_copy(self, old_text: str, old_seq: int, timeout_ms: int = 700):
        """Ждёт результата Ctrl+C без записи служебного маркера в буфер.
        Возвращает: (text, new_seq, changed).
        changed=True, если изменился текст или системный sequence number.
        """
        deadline = time.time() + max(0, timeout_ms) / 1000.0
        last_text = old_text or ""
        last_seq = old_seq
        while time.time() < deadline:
            try:
                QApplication.processEvents()
                text = QApplication.clipboard().text() or ""
                seq = self._clipboard_sequence()
                if text and (text != old_text or (old_seq and seq != old_seq)):
                    return text, seq, True
                last_text = text
                last_seq = seq
            except Exception:
                pass
            time.sleep(0.03)
        return last_text, last_seq, False


    def _copy_from_active_calculator(self):
        ok, hwnd, _exe, _cls, _title = self._calculator_foreground_info()
        if not ok:
            return
        self._copy_from_calculator_hwnd(hwnd)

    def _postprocess_copied_calc_result(self):
        # Оставлено для совместимости со старыми вызовами. Новая логика
        # применяет prefix/suffix внутри _copy_from_calculator_hwnd().
        try:
            text = QApplication.clipboard().text() or ""
            if not text:
                return
            text = self._format_calc_result_for_clipboard(text)
            text = self._apply_auto_copy_affixes(text)
            QApplication.clipboard().setText(text)
            log(f"Auto-copy postprocessed: {text!r}")
        except Exception as e:
            log(f"Auto-copy postprocess failed: {e}")

    # ------------------------------------------------------------------
    # Слоты: калькулятор
    # ------------------------------------------------------------------

    def _schedule_autoreplace_in_main_thread(self, delete_count: int, replacement: str, suffix: str):
        QTimer.singleShot(20, lambda: self._apply_autoreplace(int(delete_count), str(replacement), str(suffix)))

    def _apply_autoreplace(self, delete_count: int, replacement: str, suffix: str = ""):
        try:
            import keyboard as _keyboard
            cb = QApplication.clipboard()
            old_text = cb.text() or ""
            for _ in range(max(0, int(delete_count))):
                _keyboard.press_and_release("backspace")
                time.sleep(0.005)
            cb.setText(f"{replacement}{suffix}")
            _send_ctrl_v()
            QTimer.singleShot(120, lambda txt=old_text: QApplication.clipboard().setText(txt))
        except Exception as e:
            log(f"Autoreplace apply failed: {e}")

    def _set_pos_mode(self, mode: str):
        self.pos_mode = mode
        if mode != POS_LAST:
            self.session_pos = None
        self._save_settings()
        log(f"Position mode: {mode}")

    def _on_opacity(self, v: int):
        self.opacity_pct = v
        if hasattr(self, "lbl_opacity"):
            self.lbl_opacity.setText(f"Непрозрачность: {v}%")
        hwnd = self._find_target_hwnd()
        if hwnd:
            apply_opacity(hwnd, v)
        self._save_settings()

    def _toggle_calc_hotkey_enabled(self):
        self.calc_hotkey_enabled = not self.calc_hotkey_enabled
        self.act_calc_hotkey_enabled.blockSignals(True)
        self.act_calc_hotkey_enabled.setChecked(self.calc_hotkey_enabled)
        self.act_calc_hotkey_enabled.blockSignals(False)
        self._save_settings()
        log(f"Calc hotkey enabled: {self.calc_hotkey_enabled}")

    def _register_note_popup_hotkey(self):
        if not self._pro_soft_active():
            return
        try:
            if self._note_popup_hotkey_handle is not None:
                try:
                    keyboard.remove_hotkey(self._note_popup_hotkey_handle)
                except Exception:
                    pass
                self._note_popup_hotkey_handle = None
            if not self.note_popup_enabled:
                return
            hk = (self.note_popup_hotkey or "").strip()
            if not hk:
                return
            self._note_popup_hotkey_handle = keyboard.add_hotkey(
                hk,
                lambda: self._sig_note_popup_show.emit(),
                suppress=False,
                trigger_on_release=False,
            )
            log(f"Note popup hotkey registered: {hk}")
        except Exception as e:
            log(f"Note popup hotkey register failed ({self.note_popup_hotkey!r}): {e}")
            self._note_popup_hotkey_handle = None

    def _show_note_popup(self):
        try:
            if self._note_popup_dlg is not None and self._note_popup_dlg.isVisible():
                self._note_popup_dlg.raise_()
                self._note_popup_dlg.activateWindow()
                return
            if not self._pro_soft_active():
                self._show_pro_locked_popup("Быстрая заметка")
                return
            if not self._ensure_pro_soft_loaded():
                return
            dlg = pro_soft.NotePopupDialog(self)
            self._note_popup_dlg = dlg
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        except Exception as e:
            log(f"Note popup show failed: {e}")

    def _exit(self):
        self.running = False
        log("Exiting")
        try:
            if MANAGED_WINDOWS_AVAILABLE and self.tray_window_manager is not None:
                self.tray_window_manager.shutdown()
        except Exception as e:
            log(f"managed_windows shutdown failed: {e}")
        try:
            if self.tracker is not None:
                self.tracker.stop()
        except Exception:
            pass
        try:
            if self._keyboard_recovery_timer is not None and self._keyboard_recovery_timer.isActive():
                self._keyboard_recovery_timer.stop()
        except Exception:
            pass
        try:
            self._unregister_session_notifications()
        except Exception:
            pass
        try:
            if self.shot_timer is not None and self.shot_timer.isActive():
                self.shot_timer.stop()
        except Exception:
            pass
        try:
            if self.diary is not None:
                self.diary.flush()
        except Exception:
            pass
        try:
            if self._note_popup_hotkey_handle is not None:
                keyboard.remove_hotkey(self._note_popup_hotkey_handle)
                self._note_popup_hotkey_handle = None
        except Exception:
            pass
        try:
            self._unregister_calc_hotkeys()
        except Exception:
            pass
        try:
            self._unregister_launcher_hotkeys()
        except Exception:
            pass
        try:
            self._unregister_keyboard_hook(reason="exit")
        except Exception:
            pass
        self.tray.hide()
        QApplication.quit()

    # ------------------------------------------------------------------
    # Хук NumLock
    # ------------------------------------------------------------------
    def _on_key(self, event):
        # Общий on_press оставлен только для дневника и автокопирования по Enter.
        # Калькулятор и пауза обработки регистрируются отдельно через add_hotkey,
        # чтобы нормально работали сочетания вида ctrl+alt+c и shift+num lock.
        try:
            if self._pro_secure_active() and self.diary is not None:
                self.diary.on_key(event)
        except Exception:
            pass

        try:
            if self._pro_secure_active() and self._ensure_pro_secure_loaded():
                replacement = pro_secure.handle_autoreplace_event(self, event)
                if replacement:
                    delete_count, repl, suffix = replacement
                    self._sig_autoreplace_request.emit(int(delete_count), str(repl), str(suffix or ""))
                    return
        except Exception as e:
            log(f"Autoreplace event failed: {e}")

        name = (event.name or "").lower()
        if name in ("enter", "num enter", "=", "equals"):
            # Автокопирование результата реагирует на Enter и =.
            # Модифицированные сочетания оставляем приложению.
            try:
                if (keyboard.is_pressed("shift") or keyboard.is_pressed("ctrl")
                        or keyboard.is_pressed("alt")):
                    return
            except Exception:
                pass
            self._on_enter_for_calc_copy()

    # ------------------------------------------------------------------
    # Логика запуска/скрытия приложения по NumLock
    # ------------------------------------------------------------------
    def _on_builtin_calc_group_digits_changed(self, enabled: bool) -> None:
        self.calc_group_digits = bool(enabled)
        try:
            self._save_settings()
        except Exception as e:
            log(f"Save calc group digits setting failed: {e}")

    def _using_builtin_calc(self) -> bool:
        return str(getattr(self, "calc_custom_cmd", "") or "").strip() == BUILTIN_CALC_CMD

    def _ensure_builtin_calc(self):
        self._startup_mark("CALC_ENSURE_BEGIN")
        if not BUILTIN_CALC_AVAILABLE or StandardPercentCalculator is None:
            try:
                self.tray.showMessage(APP_NAME, "Встроенный калькулятор недоступен: standard_calc.py не найден или не импортируется", QSystemTrayIcon.Warning, 3000)
            except Exception:
                pass
            self._startup_mark("CALC_ENSURE_UNAVAILABLE")
            return None
        if self._builtin_calc_window is None:
            self._startup_mark("CALC_WINDOW_CREATE_BEGIN")
            self._builtin_calc_window = StandardPercentCalculator(
                theme_mode=getattr(self, "interface_theme", "system"),
                history_path=getattr(self, "calc_history_path", str(DEFAULT_CALC_HISTORY_FILE)),
                group_digits=getattr(self, "calc_group_digits", False),
                clipboard_mode=_normalize_calc_clipboard_mode(
                    getattr(self, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT),
                    allow_money_text=self._pro_soft_active(),
                ),
                context_menu_factory=self._build_calculator_context_menu,
                money_text_formatter=self._format_money_text_for_copy if self._pro_soft_active() else None,
                allow_money_text=self._pro_soft_active(),
                copy_text_postprocessor=self._apply_auto_copy_affixes,
            )
            try:
                if hasattr(self._builtin_calc_window, "clipboardModeChanged"):
                    self._builtin_calc_window.clipboardModeChanged.connect(self._on_builtin_calc_clipboard_mode_changed)
            except Exception:
                pass
            self._startup_mark("CALC_WINDOW_CREATE_DONE")
            try:
                self._startup_mark("CALC_SHELL_ICON_BEGIN")
                self._builtin_calc_window.setWindowIcon(self._icon())
                self._startup_mark("CALC_SHELL_ICON_DONE")
            except Exception:
                pass
        else:
            self._startup_mark("CALC_WINDOW_REUSE")
            try:
                if hasattr(self._builtin_calc_window, "set_money_text_options"):
                    self._builtin_calc_window.set_money_text_options(
                        formatter=self._format_money_text_for_copy if self._pro_soft_active() else None,
                        allow_money_text=self._pro_soft_active(),
                        copy_text_postprocessor=self._apply_auto_copy_affixes,
                    )
                if hasattr(self._builtin_calc_window, "set_clipboard_mode"):
                    self._builtin_calc_window.set_clipboard_mode(
                        _normalize_calc_clipboard_mode(
                            getattr(self, "calc_clipboard_mode", CALC_CLIPBOARD_RESULT),
                            allow_money_text=self._pro_soft_active(),
                        ),
                        notify=False,
                    )
            except Exception as e:
                log(f"Builtin calculator option sync failed: {e}")
        self._startup_mark("CALC_ENSURE_DONE")
        return self._builtin_calc_window

    def _prewarm_builtin_calc(self):
        if not self._using_builtin_calc():
            return
        if self._builtin_calc_window is not None:
            return
        try:
            w = self._ensure_builtin_calc()
            if w is not None:
                w.hide()
                log("Builtin calculator prewarmed")
        except Exception as e:
            log(f"Builtin calculator prewarm failed: {e}")

    def _toggle_builtin_calc(self):
        self._startup_mark("CALC_TOGGLE_BUILTIN_BEGIN")
        w = self._ensure_builtin_calc()
        if w is None:
            return
        try:
            if w.isVisible() and not w.isMinimized():
                self.session_pos = (w.x(), w.y())
                w.hide()
                log(f"Builtin calculator hidden, pos={self.session_pos}")
                return
            if self.session_pos:
                try:
                    self._startup_mark("CALC_MOVE_SESSION_BEGIN")
                    w.move(int(self.session_pos[0]), int(self.session_pos[1]))
                    self._startup_mark("CALC_MOVE_SESSION_DONE")
                except Exception:
                    pass
            else:
                self._startup_mark("CALC_SCREEN_GEOMETRY_BEGIN")
                screen = QGuiApplication.primaryScreen()
                if screen:
                    geo = screen.availableGeometry()
                    if self.pos_mode == POS_BOTTOM_RIGHT:
                        w.move(geo.right() - w.width() - 12, geo.bottom() - w.height() - 12)
                    else:
                        w.move(geo.center().x() - w.width() // 2, geo.center().y() - w.height() // 2)
                self._startup_mark("CALC_SCREEN_GEOMETRY_DONE")
            # ВАЖНО: opacity до первого show() на Windows может переводить окно
            # в layered-mode и резко замедлять первый показ. Сначала показываем
            # рабочий калькулятор, затем применяем прозрачность отложенно.
            opacity_value = max(0.1, min(1.0, float(self.opacity_pct) / 100.0))
            self._startup_mark("CALC_OPACITY_DEFERRED_SCHEDULED")

            self._startup_mark("CALC_SHOW_BEGIN")
            w.show()
            self._startup_mark("CALC_SHOW_DONE")

            def _apply_calc_opacity_deferred(win=w, opacity=opacity_value):
                try:
                    self._startup_mark("CALC_OPACITY_DEFERRED_BEGIN")
                    if win is not None:
                        win.setWindowOpacity(opacity)
                    self._startup_mark("CALC_OPACITY_DEFERRED_DONE")
                except Exception as e:
                    log(f"Deferred builtin calculator opacity failed: {e}")

            QTimer.singleShot(100, _apply_calc_opacity_deferred)
            self._startup_mark("CALC_RAISE_BEGIN")
            w.raise_()
            self._startup_mark("CALC_RAISE_DONE")
            self._startup_mark("CALC_ACTIVATE_BEGIN")
            w.activateWindow()
            self._startup_mark("CALC_ACTIVATE_DONE")
            try:
                QApplication.processEvents()
                self._startup_mark("CALC_PROCESS_EVENTS_DONE")
            except Exception:
                pass
            log(f"Builtin calculator shown, opacity={self.opacity_pct}%")
            self._startup_mark("CALC_TOGGLE_BUILTIN_DONE")
        except Exception as e:
            log(f"Builtin calculator toggle failed: {e}")

    def _custom_exe_basename(self) -> str:
        if not self.calc_custom_cmd or self._using_builtin_calc():
            return ""
        try:
            return Path(self.calc_custom_cmd).name.lower()
        except Exception:
            return ""

    def _find_target_hwnd(self):
        if self._using_builtin_calc():
            w = self._builtin_calc_window
            if w is not None and w.isVisible():
                try:
                    return int(w.winId())
                except Exception:
                    return 0
            return 0
        basename = self._custom_exe_basename()
        if basename:
            return find_hwnd_by_exe(basename)
        return find_calc_hwnd()

    def _launch_target(self):
        if self._using_builtin_calc():
            self._toggle_builtin_calc()
            return
        if self.calc_custom_cmd:
            exe = self.calc_custom_cmd
            args = []
            if self.calc_custom_args.strip():
                try:
                    import shlex
                    args = shlex.split(self.calc_custom_args, posix=False)
                except Exception:
                    args = self.calc_custom_args.split()
            cmd = [exe] + args
            log(f"Launching custom: {cmd}")
        else:
            cmd = [CALC_CMD]
            log("Launching calc…")
        try:
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            log(f"Launch failed: {e}")
            try:
                self.tray.showMessage(APP_NAME,
                                      f"Не удалось запустить:\n{cmd[0]}\n{e}",
                                      QSystemTrayIcon.Warning, 3000)
            except Exception:
                pass

    def _do_toggle(self):
        log(f"Toggle (mode={self.hide_mode})")
        if self._using_builtin_calc():
            self._toggle_builtin_calc()
            QtCore.QTimer.singleShot(300, self._restore_numlock)
            return
        hwnd = self._find_target_hwnd()
        if not hwnd:
            # Окна нет — это либо первый запуск, либо режим "close" после скрытия.
            self._launch_target()
            self._wait_for_calc()
        elif bool(IsIconic(hwnd)) or is_cloaked(hwnd) or not IsWindowVisible(hwnd):
            # IsWindowVisible = False когда окно скрыто через SW_HIDE
            self._show(hwnd)
        else:
            self._hide(hwnd)
        QtCore.QTimer.singleShot(300, self._restore_numlock)

    def _wait_for_calc(self, ms: int = 200, attempts: int = 25):
        self._wait_n = attempts
        def _check():
            hwnd = self._find_target_hwnd()
            if hwnd:
                log("Target window appeared")
                self._show(hwnd)
                QtCore.QTimer.singleShot(300, self._restore_numlock)
            elif self._wait_n > 0:
                self._wait_n -= 1
                QtCore.QTimer.singleShot(ms, _check)
            else:
                log("Target window did not appear")
        QtCore.QTimer.singleShot(ms, _check)

    def _target_pos(self, hwnd) -> tuple:
        r  = get_rect(hwnd)
        ww = r.right - r.left
        wh = r.bottom - r.top
        sw = GetSystemMetrics(0)
        sh = GetSystemMetrics(1)
        if self.pos_mode == POS_CENTER:
            return (sw - ww) // 2, (sh - wh) // 2
        if self.pos_mode == POS_BOTTOM_RIGHT:
            return sw - ww - 12, sh - wh - 60
        return self.session_pos if self.session_pos else ((sw - ww) // 2, (sh - wh) // 2)

    def _show(self, hwnd):
        # В режиме "hide": вернуть стиль окна (убрать TOOLWINDOW, вернуть APPWINDOW)
        # ДО ShowWindow — иначе кнопка не появится в taskbar.
        if self.hide_mode == "hide":
            try:
                style = GetWindowLongW(hwnd, GWL_EXSTYLE)
                new_style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
                if new_style != style:
                    SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            except Exception as e:
                log(f"Restore window style failed: {e}")
        ShowWindow(hwnd, SW_RESTORE)
        ShowWindow(hwnd, SW_SHOW)
        x, y = self._target_pos(hwnd)
        SetWindowPos(hwnd, HWND_NOTOPMOST, x, y, 0, 0, SWP_NOSIZE | SWP_SHOWWINDOW)
        SetForegroundWindow(hwnd)
        apply_opacity(hwnd, self.opacity_pct)
        r = get_rect(hwnd)
        self.session_pos = (r.left, r.top)
        log(f"Shown at ({r.left},{r.top}) opacity={self.opacity_pct}%")

    def _hide(self, hwnd):
        r = get_rect(hwnd)
        self.session_pos = (r.left, r.top)
        if self.hide_mode == "close":
            # Закрываем окно — процесс выгрузится, taskbar-item исчезнет.
            try:
                PostMessageW(hwnd, WM_CLOSE, 0, 0)
                log(f"Closed (WM_CLOSE), pos={self.session_pos}")
            except Exception as e:
                log(f"WM_CLOSE failed: {e}")
        else:
            # Меняем стиль окна на tool-window — Windows исключает такие окна
            # из taskbar даже для UWP. Стиль ставится ДО SW_HIDE, чтобы Shell
            # увидел изменение при следующем ShowWindow.
            try:
                style = GetWindowLongW(hwnd, GWL_EXSTYLE)
                new_style = (style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
                if new_style != style:
                    SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            except Exception as e:
                log(f"Set tool-window style failed: {e}")
            ShowWindow(hwnd, SW_HIDE)
            log(f"Hidden (SW_HIDE + TOOLWINDOW), pos={self.session_pos}")

    def _restore_numlock(self):
        try:
            if not (GetKeyState(VK_NUMLOCK) & 1):
                keybd_event(VK_NUMLOCK, 0, 0, 0)
                keybd_event(VK_NUMLOCK, 0, KEYEVENTF_KEYUP, 0)
        except Exception as e:
            log(f"NumLock restore error: {e}")

    # ------------------------------------------------------------------
    # Делегаты в extra (вызываются из меню/таймеров; пустые без extra)
    # ------------------------------------------------------------------
    def screenshots_apply_timer(self):
        if self._pro_secure_active() and EXTRA_AVAILABLE and self._ensure_extra_loaded():
            try:
                extra.apply_screenshot_timer(self)
            except Exception as e:
                log(f"apply_screenshot_timer failed: {e}")

    def take_screenshot(self, reason: str = "manual"):
        if self._pro_secure_active() and EXTRA_AVAILABLE and self._ensure_extra_loaded():
            try:
                extra.take_screenshot(self, reason)
            except Exception as e:
                log(f"take_screenshot failed: {e}")

    def _on_shot_timer_tick(self):
        if self._pro_secure_active() and EXTRA_AVAILABLE and self._ensure_extra_loaded():
            try:
                extra.on_shot_timer_tick(self)
            except Exception as e:
                log(f"on_shot_timer_tick failed: {e}")

    def _check_archive(self):
        if self._pro_secure_active() and EXTRA_AVAILABLE and self._ensure_extra_loaded():
            try:
                extra.check_archive(self)
            except Exception as e:
                log(f"check_archive failed: {e}")

    def _refresh_pause_label(self):
        if self._pro_secure_active() and EXTRA_AVAILABLE and self._ensure_extra_loaded():
            try:
                extra.refresh_pause_label(self)
                if hasattr(extra, "refresh_diary_pause_label"):
                    extra.refresh_diary_pause_label(self)
            except Exception as e:
                log(f"refresh_pause_label failed: {e}")


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
# Глобальный держатель mutex, чтобы не сборщик мусора не освободил его до
# закрытия программы.
_SINGLE_INSTANCE_HANDLE = None


def _ensure_single_instance() -> bool:
    """
    Создаёт named mutex и возвращает True, если эта копия — единственная.
    Если другая копия уже запущена, пытается её активировать (показать
    окно настроек, если открыто) и возвращает False.
    Все ошибки гасятся — fallback к запуску без single-instance.
    """
    global _SINGLE_INSTANCE_HANDLE
    try:
        ERROR_ALREADY_EXISTS = 183
        # Уникальное имя на пользователя — Local\\, чтобы не конфликтовать
        # между сессиями RDP / разных пользователей одного хоста.
        mutex_name = "Local\\CalcNumLock-Singleton-v1"
        kernel32.SetLastError(0)
        h = kernel32.CreateMutexW(None, False, mutex_name)
        err = kernel32.GetLastError()
        if not h:
            log(f"single-instance: CreateMutexW failed, err={err}")
            return True  # не блокируем запуск, если не смогли создать
        if err == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(h)
            log("single-instance: another copy is already running")
            return False
        _SINGLE_INSTANCE_HANDLE = h
        return True
    except Exception as e:
        log(f"single-instance check failed: {e}")
        return True  # не блокируем запуск


def _install_crash_logging() -> None:
    """Перехват необработанных Python-исключений и C-крашей.

    1. sys.excepthook — Python-исключения, которые иначе пропали бы тихо
       (например, в QTimer-слотах без try/except).
    2. faulthandler — пишет стек по сигналам (SIGSEGV/SIGABRT) и при выходе.
       Поднимает шанс поймать ctypes-краши, которые сейчас уносят процесс
       без следа в debug.log.
    """
    try:
        import traceback as _tb

        _orig_excepthook = sys.excepthook

        def _hook(exc_type, exc_value, exc_tb):
            try:
                lines = _tb.format_exception(exc_type, exc_value, exc_tb)
                log("UNHANDLED EXCEPTION:\n" + "".join(lines).rstrip())
            except Exception:
                pass
            try:
                _orig_excepthook(exc_type, exc_value, exc_tb)
            except Exception:
                pass

        sys.excepthook = _hook
    except Exception:
        pass

    try:
        import faulthandler
        # Пишем faulthandler-вывод в тот же файл, что и log().
        from functions import LOG_FILE, LOGS_DIR
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            # 'a'+buffering=1 → line-buffered, чтобы успеть на дисковую запись.
            _fh_log = open(LOG_FILE, "a", buffering=1, encoding="utf-8")
            faulthandler.enable(file=_fh_log, all_threads=True)
            log("crash logging: faulthandler enabled")
        except Exception as e:
            log(f"crash logging: faulthandler open failed: {e}")
    except Exception as e:
        try:
            log(f"crash logging: install failed: {e}")
        except Exception:
            pass


def _set_windows_app_user_model_id() -> None:
    """Даёт Windows стабильный AppUserModelID, чтобы taskbar брал иконку приложения,
    а не значок python/pythonw."""
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CalcNumLock.StandardCalculator")
    except Exception:
        pass


def main():
    _set_windows_app_user_model_id()
    _install_crash_logging()

    # QApplication создаётся ДО single-instance QMessageBox. Иначе при уже
    # запущенной стабильной/старой копии процесс выходил молча: QMessageBox
    # падал без QApplication, исключение проглатывалось, sys.exit(0).
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    try:
        app.setWindowIcon(load_embedded_icon())
    except Exception:
        pass

    if not _ensure_single_instance():
        try:
            QMessageBox.information(
                None, APP_NAME,
                "CalcNumLock уже запущен. Иконка должна быть в системном трее."
            )
        except Exception:
            pass
        sys.exit(0)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "Системный трей недоступен.")
        sys.exit(1)

    tray_app = CalcTrayApp()
    if not globals().get("KEYBOARD_AVAILABLE", True):
        try:
            log(f"keyboard package unavailable: {globals().get('KEYBOARD_IMPORT_ERROR', '')}")
            tray_app.tray.showMessage(
                APP_NAME,
                "Пакет keyboard не загружен: NumLock/hotkey отключены, но приложение запущено.",
                QSystemTrayIcon.Warning,
                5000,
            )
        except Exception:
            pass
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
