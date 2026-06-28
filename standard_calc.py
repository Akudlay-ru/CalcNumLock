# -*- coding: utf-8 -*-
"""
standard_calc.py — встроенный стандартный калькулятор CalcNumLock.

Использует кодовую логику Windows Calculator Standard Mode из предоставленного
архива, но без scientific/programmer/converter и без memory-блока.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QTimer
from PyQt5.QtGui import QFontMetrics, QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QPlainTextEdit, QPushButton, QSizePolicy, QShortcut, QVBoxLayout, QWidget,
)

from standard_calc_engine import ACTION_TO_OP, Op, StandardEngine, StandardState, Formatter, FormatOptions
from styles import active_palette, build_qss, is_windows_dark_mode

try:
    from functions import load_embedded_icon, startup_profile
except Exception:  # standalone preview fallback
    load_embedded_icon = None
    def startup_profile(label: str) -> None:
        return None

def _calc_profile(label: str) -> None:
    try:
        startup_profile(label)
    except Exception:
        pass


MIN_FONT_PX = 22
MAX_FONT_PX = 104

CLIPBOARD_OFF = "off"
CLIPBOARD_RESULT = "result"
CLIPBOARD_TEXT = "text"
CLIPBOARD_MONEY_TEXT = "money_text"
CLIPBOARD_MODES = (CLIPBOARD_OFF, CLIPBOARD_RESULT, CLIPBOARD_TEXT, CLIPBOARD_MONEY_TEXT)


def _normalize_clipboard_mode(value: str | None) -> str:
    mode = str(value or CLIPBOARD_RESULT).strip().lower()
    return mode if mode in CLIPBOARD_MODES else CLIPBOARD_RESULT


def _colorref(hex_color: str) -> int:
    """#RRGGBB -> Windows COLORREF 0x00BBGGRR."""
    h = str(hex_color or "").strip().lstrip("#")
    if len(h) != 6:
        return 0
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def _apply_win_titlebar(hwnd: int, dark: bool, caption_color: str, text_color: str) -> None:
    """Synchronize native Windows title bar with the calculator palette.

    DWMWA_USE_IMMERSIVE_DARK_MODE fixes the dark/light mode.
    DWMWA_CAPTION_COLOR and DWMWA_TEXT_COLOR keep the title bar from drifting
    away from the calculator body on Windows 11.
    """
    if not sys.platform.startswith("win") or not hwnd:
        return
    try:
        dwm = ctypes.windll.dwmapi
    except Exception:
        return

    dark_value = ctypes.c_int(1 if dark else 0)
    for attr in (20, 19):
        try:
            dwm.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), ctypes.c_uint(attr),
                ctypes.byref(dark_value), ctypes.sizeof(dark_value),
            )
        except Exception:
            pass

    # Windows 11: DWMWA_CAPTION_COLOR = 35, DWMWA_TEXT_COLOR = 36.
    for attr, color in ((35, caption_color), (36, text_color)):
        try:
            value = ctypes.c_int(_colorref(color))
            dwm.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), ctypes.c_uint(attr),
                ctypes.byref(value), ctypes.sizeof(value),
            )
        except Exception:
            pass


class DisplayWidget(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(88)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.expr_lbl = QLabel("")
        self.expr_lbl.setProperty("labelRole", "expression")
        self.expr_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.expr_lbl.setFixedHeight(22)
        v.addWidget(self.expr_lbl)
        self.disp_lbl = QLabel("0")
        self.disp_lbl.setProperty("labelRole", "display")
        self.disp_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.disp_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(self.disp_lbl, 1)

    def update_from_state(self, state: StandardState) -> None:
        self.expr_lbl.setText(state.expression)
        self.disp_lbl.setText(state.display)
        self._adapt_display_font()

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._adapt_display_font()

    def _adapt_display_font(self) -> None:
        """Подбирает размер результата по фактической ширине текста.

        До первого показа окна не запускаем QFontMetrics/layout-расчёт:
        на холодном старте это превращалось в дорогой пересчёт геометрии Qt.
        Первый экран получает быстрый фиксированный размер, точная подгонка
        выполняется после showEvent через отложенный refresh.
        """
        win = self.window()
        if win is None or not win.isVisible():
            self.disp_lbl.setStyleSheet(
                "QLabel[labelRole='display'] { font-size: 58px; font-weight: 500; }"
            )
            return

        text = self.disp_lbl.text() or "0"
        result_h = max(40, self.height() - self.expr_lbl.height())
        max_by_height = max(MIN_FONT_PX, min(MAX_FONT_PX, int(result_h * 0.68)))
        available_w = max(40, self.disp_lbl.contentsRect().width() - 10)

        lo, hi = MIN_FONT_PX, max_by_height
        best = lo
        base_font = self.disp_lbl.font()

        while lo <= hi:
            mid = (lo + hi) // 2
            f = base_font
            f.setPixelSize(mid)
            fm = QFontMetrics(f)
            if fm.horizontalAdvance(text) <= available_w:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1

        self.disp_lbl.setStyleSheet(
            f"QLabel[labelRole='display'] {{ font-size: {best}px; font-weight: 500; }}"
        )


_GRID_LAYOUT = [
    # Основная сетка. Верхний служебный ряд вынесен отдельно в TopActionBar,
    # чтобы он выглядел как memory bar Win11 Calculator, а не как полноценный
    # кнопочный ряд. Да, это именно та скучная мелочь, из-за которой UI начинает
    # выглядеть не как черновик.
    ("C",   "operator", "clear",        0, 0, 1, 1),
    ("(",   "operator", "open_paren",   0, 1, 1, 1),
    (")",   "operator", "close_paren",  0, 2, 1, 1),
    ("÷",   "operator", "op:/",         0, 3, 1, 1),

    ("7",   "digit",    "digit:7",      1, 0, 1, 1),
    ("8",   "digit",    "digit:8",      1, 1, 1, 1),
    ("9",   "digit",    "digit:9",      1, 2, 1, 1),
    ("×",   "operator", "op:*",         1, 3, 1, 1),

    ("4",   "digit",    "digit:4",      2, 0, 1, 1),
    ("5",   "digit",    "digit:5",      2, 1, 1, 1),
    ("6",   "digit",    "digit:6",      2, 2, 1, 1),
    ("−",   "operator", "op:-",         2, 3, 1, 1),

    ("1",   "digit",    "digit:1",      3, 0, 1, 1),
    ("2",   "digit",    "digit:2",      3, 1, 1, 1),
    ("3",   "digit",    "digit:3",      3, 2, 1, 1),
    ("+",   "operator", "op:+",         3, 3, 1, 1),

    ("±",   "operator", "negate",       4, 0, 1, 1),
    ("0",   "digit",    "digit:0",      4, 1, 1, 1),
    (",",   "digit",    "decimal",      4, 2, 1, 1),
    ("=",   "equals",   "equals",       4, 3, 1, 1),
]



class SplitChip(QWidget):
    """Мини-кнопка memory-bar: основная часть выполняет действие, стрелка раскрывает меню."""

    actionTriggered = pyqtSignal(str)

    def __init__(self, icon: str, label: str, default_action: str, items=None, parent=None) -> None:
        super().__init__(parent)
        self._current_icon = icon
        self._current_label = label
        self._current_action = default_action
        self._current_tooltip = label
        self._items = list(items or [])
        self._enabled_current = True
        self.setProperty("role", "split-chip")

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self.main_btn = QPushButton(icon)
        self.main_btn.setProperty("btnRole", "chip")
        self.main_btn.setProperty("chipPart", "main")
        self.main_btn.setFocusPolicy(Qt.NoFocus)
        self.main_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.main_btn.setMinimumHeight(26)
        self.main_btn.setMaximumHeight(28)
        self.main_btn.clicked.connect(self._trigger_current)
        h.addWidget(self.main_btn, 1)

        self.arrow_btn = QPushButton("▾")
        self.arrow_btn.setProperty("btnRole", "chip")
        self.arrow_btn.setProperty("chipPart", "arrow")
        self.arrow_btn.setFocusPolicy(Qt.NoFocus)
        self.arrow_btn.setFixedWidth(20)
        self.arrow_btn.setMinimumHeight(26)
        self.arrow_btn.setMaximumHeight(28)
        self.arrow_btn.clicked.connect(self._show_menu)
        h.addWidget(self.arrow_btn, 0)
        self._sync_visuals()

    def _sync_visuals(self) -> None:
        self.main_btn.setText(self._current_icon)
        self.main_btn.setToolTip(self._current_tooltip)
        self.main_btn.setEnabled(bool(self._enabled_current))
        self.arrow_btn.setToolTip(f"Выбрать действие: {self._current_label}")
        self.setToolTip(self._current_tooltip)

    def set_current_action(self, action: str, enabled: bool = True) -> None:
        for item in self._items:
            icon, label, item_action, tooltip = item
            if item_action == action:
                self._current_icon = icon
                self._current_label = label
                self._current_action = item_action
                self._current_tooltip = tooltip
                self._enabled_current = bool(enabled)
                self._sync_visuals()
                return
        self._enabled_current = bool(enabled)
        self._sync_visuals()

    def _trigger_current(self) -> None:
        if not self._enabled_current:
            return
        self.actionTriggered.emit(self._current_action)

    def _show_menu(self) -> None:
        if not self._items:
            return
        menu = QMenu(self)
        menu.setStyleSheet(self.window().styleSheet())
        for item in self._items:
            icon, label, action, tooltip = item
            act = menu.addAction(f"{icon}  {label}")
            act.setToolTip(tooltip)
            act.triggered.connect(lambda _=False, it=item: self._choose(*it))
        menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def _choose(self, icon: str, label: str, action: str, tooltip: str) -> None:
        self._current_icon = icon
        self._current_label = label
        self._current_action = action
        self._current_tooltip = tooltip
        self._enabled_current = action != "copy_disabled"
        self._sync_visuals()
        self.actionTriggered.emit(action)


class TopActionBar(QWidget):
    """Горизонтальная мини-полоса по типу memory bar Win11 Calculator."""

    actionTriggered = pyqtSignal(str)

    def __init__(self, parent=None, money_text_enabled: bool = False) -> None:
        super().__init__(parent)
        self.setProperty("role", "top-action-bar")
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.buttons: dict[str, QWidget] = {}

        unary = SplitChip("1/x", "Обратное число", "reciprocal", [
            ("1/x", "Обратное число", "reciprocal", "Вычислить 1/x для текущего числа"),
            ("x²", "Квадрат", "square", "Возвести текущее число в квадрат"),
            ("√x", "Квадратный корень", "square_root", "Вычислить квадратный корень текущего числа"),
        ], self)
        unary.actionTriggered.connect(self.actionTriggered.emit)
        h.addWidget(unary, 1)
        self.buttons["unary"] = unary

        percent = SplitChip("%", "Обычный процент", "percent", [
            ("%", "Обычный процент", "percent", "Обычный процент как в стандартном калькуляторе Windows"),
            ("+%", "Увеличить на процент", "percent_add", "Увеличить A на B процентов: A + B%"),
            ("-%", "Уменьшить на процент", "percent_subtract", "Уменьшить A на B процентов: A - B%"),
            ("%от", "Сколько процентов A от B", "percent_of", "Посчитать, сколько процентов A составляет от B"),
            ("Δ%", "Процентное изменение", "percent_delta", "Посчитать процентное изменение от A к B"),
        ], self)
        percent.actionTriggered.connect(self.actionTriggered.emit)
        h.addWidget(percent, 1)
        self.buttons["percent"] = percent

        copy_items = [
            ("○", "Отключить", "copy_disabled", "Отключить кнопку буфера на калькуляторе"),
            ("⧉", "Копировать результат", "copy_result", "Скопировать текущий результат в буфер обмена"),
            ("Тx", "Число → текст", "copy_number_text", "Постоянно копировать результат текстом"),
        ]
        if money_text_enabled:
            copy_items.append(("₽т", "Сумма ₽ текстом", "copy_money_text", "Постоянно копировать результат как сумму прописью"))
        copy = SplitChip("⧉", "Копировать результат", "copy_result", copy_items, self)
        copy.actionTriggered.connect(self.actionTriggered.emit)
        h.addWidget(copy, 1)
        self.copy_chip = copy
        self.buttons["copy"] = copy

        backspace = QPushButton("⌫")
        backspace.setProperty("btnRole", "chip")
        backspace.setFocusPolicy(Qt.NoFocus)
        backspace.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        backspace.setMinimumHeight(26)
        backspace.setMaximumHeight(28)
        backspace.setToolTip("Удалить последний введённый символ")
        backspace.clicked.connect(lambda _=False: self.actionTriggered.emit("backspace"))
        h.addWidget(backspace, 1)
        self.buttons["backspace"] = backspace

    def set_clipboard_mode(self, mode: str) -> None:
        mode = _normalize_clipboard_mode(mode)
        if mode == CLIPBOARD_OFF:
            self.copy_chip.set_current_action("copy_disabled", enabled=False)
        elif mode == CLIPBOARD_TEXT:
            self.copy_chip.set_current_action("copy_number_text", enabled=True)
        elif mode == CLIPBOARD_MONEY_TEXT:
            self.copy_chip.set_current_action("copy_money_text", enabled=True)
        else:
            self.copy_chip.set_current_action("copy_result", enabled=True)


class StandardKeypad(QWidget):
    actionTriggered = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(1)
        self.buttons: dict[str, QPushButton] = {}
        for label, role, action, r, c, rs, cs in _GRID_LAYOUT:
            btn = QPushButton(label)
            btn.setProperty("btnRole", role)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            btn.setMinimumHeight(38)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda _=False, a=action: self.actionTriggered.emit(a))
            grid.addWidget(btn, r, c, rs, cs)
            self.buttons[action] = btn
        for i in range(4):
            grid.setColumnStretch(i, 1)
        for i in range(5):
            grid.setRowStretch(i, 1)


_KEY_ACTIONS = {
    Qt.Key_0: "digit:0", Qt.Key_1: "digit:1", Qt.Key_2: "digit:2", Qt.Key_3: "digit:3",
    Qt.Key_4: "digit:4", Qt.Key_5: "digit:5", Qt.Key_6: "digit:6", Qt.Key_7: "digit:7",
    Qt.Key_8: "digit:8", Qt.Key_9: "digit:9",
    Qt.Key_Period: "decimal", Qt.Key_Comma: "decimal",
    Qt.Key_Plus: "op:+", Qt.Key_Minus: "op:-", Qt.Key_Asterisk: "op:*", Qt.Key_Slash: "op:/",
    Qt.Key_ParenLeft: "open_paren", Qt.Key_ParenRight: "close_paren",
    Qt.Key_Percent: "percent", Qt.Key_Equal: "equals", Qt.Key_Return: "equals", Qt.Key_Enter: "equals",
    Qt.Key_Backspace: "backspace", Qt.Key_Escape: "clear", Qt.Key_Delete: "clear_entry",
}


class HistoryPopup(QFrame):
    """Popup со списком истории, текст в нём можно выделять и копировать."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setProperty("role", "history-popup")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(0)

        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setUndoRedoEnabled(False)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.text.setProperty("role", "history-list")
        lay.addWidget(self.text)

    def set_items(self, history: list[str]) -> None:
        # В popup показываем только завершённую историю.
        # Текущий ввод намеренно не выводится: он уже виден на основном дисплее.
        # Последнее выражение показываем внизу, как обычный журнал событий.
        lines = list(history[-30:])
        self.text.setPlainText("\n".join(lines))
        self.text.moveCursor(self.text.textCursor().End)


class HistoryDropDown(QPushButton):
    """Компактная строка текущего ввода и истории.

    Заменяет заголовок "Стандартный": показывает текущую строку вычисления
    у правого края, а по клику раскрывает копируемую историю вверх.
    """

    def __init__(self, engine: StandardEngine, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setProperty("btnRole", "history")
        self.setFocusPolicy(Qt.NoFocus)
        self.setMinimumHeight(32)
        self.clicked.connect(self._show_history_popup)
        self._popup = None
        self.refresh()

    def _current_text(self) -> str:
        st = self.engine.state
        if st.history_entry:
            return st.history_entry
        history = self.engine.history()
        if history:
            return history[-1]
        return ""

    def refresh(self) -> None:
        text = self._current_text()
        self.setText((f"{text}  ▾") if text else "▾")
        self.setToolTip(text or "История вычислений")

    def _show_history_popup(self) -> None:
        popup = HistoryPopup(self.window())
        popup.setStyleSheet(self.window().styleSheet())
        popup.set_items(self.engine.history())

        width = max(self.width(), min(560, self.window().width() - 10))
        item_count = max(1, len(self.engine.history()[-30:]))
        height = min(320, max(120, 28 + 22 * item_count))
        popup.resize(width, height)

        # Привязка к правому краю строки истории. Список раскрывается вверх.
        pos = self.mapToGlobal(QPoint(self.width() - width, -height))
        popup.move(pos)
        popup.show()
        popup.text.setFocus(Qt.MouseFocusReason)
        self._popup = popup


_NUM_0_19 = [
    "ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
    "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
    "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать",
]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]


def _plural_ru(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n) % 100
    if 11 <= n <= 14:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def _triad_to_words(n: int, feminine: bool = False) -> str:
    parts = []
    h = n // 100
    rest = n % 100
    if h:
        parts.append(_HUNDREDS[h])
    if rest >= 20:
        parts.append(_TENS[rest // 10])
        u = rest % 10
        if u:
            if feminine and u in (1, 2):
                parts.append("одна" if u == 1 else "две")
            else:
                parts.append(_NUM_0_19[u])
    elif rest:
        if feminine and rest in (1, 2):
            parts.append("одна" if rest == 1 else "две")
        else:
            parts.append(_NUM_0_19[rest])
    return " ".join(parts)


def _capitalize_first_letter(text: str) -> str:
    if not text:
        return text
    for i, ch in enumerate(text):
        if ch.isalpha():
            return text[:i] + ch.upper() + text[i + 1:]
    return text


def number_to_words_ru(text: str) -> str:
    from decimal import Decimal, InvalidOperation
    raw = str(text or "").strip().replace(" ", "").replace("\u00a0", "")
    raw = raw.replace(",", ".")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return ""
    sign = "минус " if value < 0 else ""
    value = abs(value)
    int_part = int(value)
    frac_text = ""
    if "." in raw:
        frac = raw.split(".", 1)[1].rstrip("0")
        if frac:
            frac_num = int(frac)
            denom_forms = {
                1: ("десятая", "десятых", "десятых"),
                2: ("сотая", "сотых", "сотых"),
                3: ("тысячная", "тысячных", "тысячных"),
                4: ("десятитысячная", "десятитысячных", "десятитысячных"),
                5: ("стотысячная", "стотысячных", "стотысячных"),
                6: ("миллионная", "миллионных", "миллионных"),
            }.get(min(len(frac), 6), ("дробная", "дробных", "дробных"))
            frac_text = " " + _int_to_words_ru(frac_num, feminine=True) + " " + _plural_ru(frac_num, denom_forms)
    whole = _int_to_words_ru(int_part, feminine=False)
    return (sign + whole + (" целых" if frac_text else "") + frac_text).strip()


def _int_to_words_ru(n: int, feminine: bool = False) -> str:
    if n == 0:
        return "ноль"
    scales = [
        ("", "", "", False),
        ("тысяча", "тысячи", "тысяч", True),
        ("миллион", "миллиона", "миллионов", False),
        ("миллиард", "миллиарда", "миллиардов", False),
    ]
    parts = []
    triads = []
    while n:
        triads.append(n % 1000)
        n //= 1000
    for idx in range(len(triads) - 1, -1, -1):
        tri = triads[idx]
        if not tri:
            continue
        one, two, many, fem = scales[idx]
        words = _triad_to_words(tri, feminine=(fem or (idx == 0 and feminine)))
        if idx:
            words = f"{words} {_plural_ru(tri, (one, two, many))}"
        parts.append(words)
    return " ".join(parts)

class StandardPercentCalculator(QMainWindow):
    clipboardModeChanged = pyqtSignal(str)

    def __init__(
        self,
        theme_mode: str | None = None,
        history_path: str | None = None,
        group_digits: bool = False,
        clipboard_mode: str = CLIPBOARD_RESULT,
        context_menu_factory=None,
        money_text_formatter=None,
        allow_money_text: bool = False,
        copy_text_postprocessor=None,
    ) -> None:
        _calc_profile("CALC_WINDOW_INIT_BEGIN")
        super().__init__()
        _calc_profile("CALC_WINDOW_QMAINWINDOW_DONE")
        self.setWindowTitle("CalcNumLock Calculator")
        try:
            if load_embedded_icon is not None:
                _calc_profile("CALC_ICON_BEGIN")
                self.setWindowIcon(load_embedded_icon())
                _calc_profile("CALC_ICON_DONE")
        except Exception:
            pass
        self.resize(380, 600)
        self.setMinimumSize(320, 500)
        _calc_profile("CALC_GEOMETRY_DONE")
        self.engine = StandardEngine(Formatter(FormatOptions(group_digits=bool(group_digits))))
        _calc_profile("CALC_ENGINE_CREATE_DONE")
        self._theme_mode = theme_mode or "system"
        self._history_path = str(history_path or "").strip()
        self._clipboard_mode = _normalize_clipboard_mode(clipboard_mode)
        self._context_menu_factory = context_menu_factory
        self._money_text_formatter = money_text_formatter
        self._allow_money_text = bool(allow_money_text)
        self._copy_text_postprocessor = copy_text_postprocessor
        self._persisted_history_count = 0
        self._build_ui()
        _calc_profile("CALC_BUILD_UI_DONE")
        self.set_clipboard_mode(self._clipboard_mode, notify=False)
        _calc_profile("CALC_CLIPBOARD_MODE_DONE")
        self._deferred_startup_done = False
        self._apply_theme(startup=True)
        _calc_profile("CALC_APPLY_THEME_DONE")
        self._set_initial_display_fast()
        _calc_profile("CALC_INITIAL_DISPLAY_FAST_DONE")
        self._shortcuts = []
        self._shortcuts.append(QShortcut(QKeySequence("Ctrl+C"), self, self.copy_result))
        self._shortcuts.append(QShortcut(QKeySequence("Ctrl+V"), self, self.paste_from_clipboard))
        # Дублируем Enter/= через QShortcut: на Windows фокус иногда остаётся
        # на QPushButton, и keyPressEvent окна не получает клавишу. Спасибо, GUI.
        for _seq in ("Return", "Enter", "="):
            try:
                sc = QShortcut(QKeySequence(_seq), self)
                sc.setContext(Qt.WindowShortcut)
                sc.activated.connect(lambda a="equals": self._on_action(a))
                self._shortcuts.append(sc)
            except Exception:
                pass
        _calc_profile("CALC_SHORTCUTS_CREATE_DONE")
        _calc_profile("CALC_WINDOW_INIT_DONE")

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("WCRoot")
        root.setFocusPolicy(Qt.NoFocus)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCentralWidget(root)
        _calc_profile("CALC_ROOT_CREATE_DONE")
        v = QVBoxLayout(root)
        v.setContentsMargins(5, 5, 5, 5)
        v.setSpacing(4)

        navbar = QFrame()
        navbar.setProperty("role", "navbar")
        nh = QHBoxLayout(navbar)
        nh.setContentsMargins(0, 0, 0, 0)
        nh.setSpacing(0)
        self.history_bar = HistoryDropDown(self.engine, self)
        _calc_profile("CALC_HISTORY_CREATE_DONE")
        nh.addWidget(self.history_bar, 1)
        v.addWidget(navbar)

        self.display = DisplayWidget(self)
        _calc_profile("CALC_DISPLAY_CREATE_DONE")
        v.addWidget(self.display)

        sep = QFrame()
        sep.setProperty("role", "separator")
        v.addWidget(sep)

        self.top_actions = TopActionBar(self, money_text_enabled=self._allow_money_text)
        _calc_profile("CALC_TOPBAR_CREATE_DONE")
        self.top_actions.actionTriggered.connect(self._on_action)
        v.addWidget(self.top_actions, 0)

        self.keypad = StandardKeypad(self)
        _calc_profile("CALC_KEYPAD_CREATE_DONE")
        self.keypad.actionTriggered.connect(self._on_action)
        v.addWidget(self.keypad, 1)

    def _on_action(self, action: str) -> None:
        # После кликов по memory-bar/menu фокус возвращаем окну,
        # иначе физическая клавиатура начинает играть в молчанку.
        try:
            self.setFocus(Qt.OtherFocusReason)
        except Exception:
            pass
        eng = self.engine
        copy_after_equals = False
        if action.startswith("digit:"):
            eng.input_digit(action.split(":", 1)[1])
        elif action == "decimal":
            eng.input_decimal()
        elif action in ACTION_TO_OP:
            eng.input_operator(ACTION_TO_OP[action])
        elif action == "equals":
            eng.equals()
            copy_after_equals = True
        elif action == "clear":
            eng.clear()
        elif action == "clear_entry":
            eng.clear_entry()
        elif action == "backspace":
            eng.backspace()
        elif action == "negate":
            eng.negate()
        elif action == "percent":
            eng.percent()
        elif action == "reciprocal":
            eng.reciprocal()
        elif action == "square":
            eng.square()
        elif action == "square_root":
            eng.square_root()
        elif action == "open_paren":
            eng.open_paren()
        elif action == "close_paren":
            eng.close_paren()
        elif action == "copy_result":
            self.set_clipboard_mode(CLIPBOARD_RESULT)
            self.copy_result()
        elif action == "copy_number_text":
            self.set_clipboard_mode(CLIPBOARD_TEXT)
            self.copy_result()
        elif action == "copy_money_text":
            self.set_clipboard_mode(CLIPBOARD_MONEY_TEXT)
            self.copy_result()
        elif action == "copy_disabled":
            self.set_clipboard_mode(CLIPBOARD_OFF)
        self._save_new_history_entries()
        self._refresh_ui()
        if copy_after_equals:
            # Кнопка буфера — это режим. После =/Enter копируем уже обновлённый
            # результат в выбранном формате.
            QTimer.singleShot(0, self.copy_result)

    def _set_initial_display_fast(self) -> None:
        """Минимальная синхронизация результата для первого показа окна.

        Не трогаем историю и не запускаем точную адаптацию шрифта до show().
        Это оставляет калькулятор визуально готовым сразу, а дорогие операции
        уходят в отложенный этап после первого показа.
        """
        try:
            self.display.expr_lbl.setText(self.engine.state.expression)
            self.display.disp_lbl.setText(self.engine.state.display)
            self.display.disp_lbl.setStyleSheet(
                "QLabel[labelRole='display'] { font-size: 58px; font-weight: 500; }"
            )
        except Exception:
            pass

    def _refresh_ui(self) -> None:
        _calc_profile("CALC_REFRESH_UI_BEGIN")
        _calc_profile("CALC_REFRESH_DISPLAY_BEGIN")
        self.display.update_from_state(self.engine.state)
        _calc_profile("CALC_REFRESH_DISPLAY_DONE")
        try:
            self.history_bar.refresh()
        except Exception:
            pass
        _calc_profile("CALC_HISTORY_BAR_REFRESH_DONE")

    def _apply_theme(self, startup: bool = False) -> None:
        _calc_profile("CALC_ACTIVE_PALETTE_BEGIN")
        p = active_palette(self._theme_mode)
        _calc_profile("CALC_ACTIVE_PALETTE_DONE")
        _calc_profile("CALC_QSS_BUILD_BEGIN")
        qss = build_qss(p)
        _calc_profile("CALC_QSS_BUILD_DONE")
        _calc_profile("CALC_QSS_SET_BEGIN")
        self.setStyleSheet(qss)
        _calc_profile("CALC_QSS_SET_DONE")

        if not startup and self.isVisible():
            _calc_profile("CALC_WIDGET_POLISH_BEGIN")
            for w in self.findChildren(QWidget):
                w.style().unpolish(w)
                w.style().polish(w)
            _calc_profile("CALC_WIDGET_POLISH_DONE")
        else:
            _calc_profile("CALC_WIDGET_POLISH_SKIPPED")

        if not startup:
            self._apply_titlebar_now()
        else:
            _calc_profile("CALC_TITLEBAR_DEFERRED")

    def _apply_titlebar_now(self) -> None:
        try:
            p = active_palette(self._theme_mode)
            _calc_profile("CALC_TITLEBAR_BEGIN")
            _apply_win_titlebar(int(self.winId()), p.name == "dark", p.window_bg, p.text_primary)
            _calc_profile("CALC_TITLEBAR_DONE")
        except Exception:
            _calc_profile("CALC_TITLEBAR_FAILED")

    def _run_deferred_startup(self) -> None:
        if self._deferred_startup_done:
            return
        self._deferred_startup_done = True
        _calc_profile("CALC_DEFERRED_START_BEGIN")
        self._refresh_ui()
        _calc_profile("CALC_DEFERRED_REFRESH_DONE")
        self._apply_titlebar_now()
        _calc_profile("CALC_DEFERRED_TITLEBAR_DONE")
        _calc_profile("CALC_DEFERRED_START_DONE")

    def showEvent(self, event) -> None:
        _calc_profile("CALC_SHOW_EVENT")
        super().showEvent(event)
        QTimer.singleShot(0, self._run_deferred_startup)

    def set_theme_mode(self, theme_mode: str | None) -> None:
        self._theme_mode = theme_mode or "system"
        self._apply_theme()

    def current_copy_text(self) -> str:
        if self.engine.state.error:
            return ""
        text = self.engine.state.display
        if self._clipboard_mode == CLIPBOARD_OFF:
            return ""
        if self._clipboard_mode == CLIPBOARD_TEXT:
            text = _capitalize_first_letter(number_to_words_ru(text))
        elif self._clipboard_mode == CLIPBOARD_MONEY_TEXT:
            formatter = self._money_text_formatter
            if callable(formatter):
                try:
                    text = formatter(text) or text
                except Exception:
                    pass
        post = getattr(self, "_copy_text_postprocessor", None)
        if callable(post) and text:
            try:
                text = post(text) or text
            except Exception:
                pass
        return text

    def set_history_path(self, history_path: str | None) -> None:
        self._history_path = str(history_path or "").strip()

    def set_group_digits(self, enabled: bool, notify: bool = True) -> None:
        self.engine.formatter.options.group_digits = bool(enabled)
        self._refresh_ui()

    def set_clipboard_mode(self, mode: str, notify: bool = True) -> None:
        old_mode = getattr(self, "_clipboard_mode", CLIPBOARD_RESULT)
        self._clipboard_mode = _normalize_clipboard_mode(mode)
        if self._clipboard_mode == CLIPBOARD_MONEY_TEXT and not self._allow_money_text:
            self._clipboard_mode = CLIPBOARD_RESULT
        if hasattr(self, "top_actions"):
            self.top_actions.set_clipboard_mode(self._clipboard_mode)
        if notify and self._clipboard_mode != old_mode:
            try:
                self.clipboardModeChanged.emit(self._clipboard_mode)
            except Exception:
                pass

    def set_money_text_formatter(self, formatter=None, allow_money_text: bool = False, copy_text_postprocessor=None) -> None:
        self._money_text_formatter = formatter
        self._allow_money_text = bool(allow_money_text and callable(formatter))
        if copy_text_postprocessor is not None:
            self._copy_text_postprocessor = copy_text_postprocessor
        if self._clipboard_mode == CLIPBOARD_MONEY_TEXT and not self._allow_money_text:
            self.set_clipboard_mode(CLIPBOARD_RESULT)

    def set_money_text_options(self, formatter=None, allow_money_text: bool | None = None, copy_text_postprocessor=None) -> None:
        if formatter is not None:
            self._money_text_formatter = formatter
        if copy_text_postprocessor is not None:
            self._copy_text_postprocessor = copy_text_postprocessor
        if allow_money_text is not None:
            self._allow_money_text = bool(allow_money_text)
            if not self._allow_money_text and self._clipboard_mode == CLIPBOARD_MONEY_TEXT:
                self.set_clipboard_mode(CLIPBOARD_RESULT)

    def _save_new_history_entries(self) -> None:
        history = self.engine.history()
        if self._persisted_history_count > len(history):
            self._persisted_history_count = 0
        new_entries = history[self._persisted_history_count:]
        if not new_entries:
            return
        self._persisted_history_count = len(history)
        if not self._history_path:
            return
        try:
            path = Path(self._history_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="") as f:
                for entry in new_entries:
                    f.write(str(entry).rstrip() + "\n")
        except Exception:
            # История не должна ронять калькулятор. Логировать здесь нечем: это автономный виджет.
            pass

    def copy_result(self) -> None:
        text = self.current_copy_text()
        if text:
            QApplication.clipboard().setText(text)


    def copy_number_text(self) -> None:
        self.set_clipboard_mode(CLIPBOARD_TEXT)
        self.copy_result()

    def copy_money_text(self) -> None:
        self.set_clipboard_mode(CLIPBOARD_MONEY_TEXT)
        self.copy_result()

    def paste_from_clipboard(self) -> None:
        cb = QApplication.clipboard()
        self._paste_text(cb.text() or "")

    def _paste_text(self, text: str) -> None:
        allowed = set("0123456789.,+-*/×÷−()% ")
        for ch in text:
            if ch not in allowed:
                continue
            if ch.isdigit():
                self._on_action(f"digit:{ch}")
            elif ch in ".,":
                self._on_action("decimal")
            elif ch == "+":
                self._on_action("op:+")
            elif ch in "-−":
                self._on_action("op:-")
            elif ch in "*×":
                self._on_action("op:*")
            elif ch in "/÷":
                self._on_action("op:/")
            elif ch == "%":
                self._on_action("percent")
            elif ch == "(":
                self._on_action("open_paren")
            elif ch == ")":
                self._on_action("close_paren")

    def contextMenuEvent(self, event) -> None:
        factory = getattr(self, "_context_menu_factory", None)
        if callable(factory):
            try:
                menu = factory()
            except TypeError:
                try:
                    menu = factory(self)
                except Exception:
                    menu = None
            except Exception:
                menu = None
            if menu is not None:
                try:
                    menu.exec_(event.globalPos())
                    event.accept()
                    return
                except Exception:
                    pass
                finally:
                    try:
                        menu.deleteLater()
                    except Exception:
                        pass
        super().contextMenuEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.Copy):
            self.copy_result()
            event.accept()
            return
        if event.matches(QKeySequence.Paste):
            self.paste_from_clipboard()
            event.accept()
            return
        action = _KEY_ACTIONS.get(event.key())
        if action is not None:
            self._on_action(action)
            event.accept()
            return
        super().keyPressEvent(event)

    # showEvent выше запускает отложенную доводку первого экрана.


CalculatorWindow = StandardPercentCalculator
