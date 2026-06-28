# -*- coding: utf-8 -*-
"""
standard_calc_engine.py — математический движок CalcNumLock.

Модель расчёта:
- обычный математический приоритет операций;
- скобки считаются первыми;
- умножение/деление выше сложения/вычитания;
- Decimal используется вместо float;
- публичный интерфейс сохранён для standard_calc.py.

Удалено намеренно:
- scientific/programmer/converter режимы;
- память MC/MR/M+/M-/MS;
- sin/cos/tan/log/ln/exp/x^y/factorial/mod/base/complex/matrix/const;

Добавлено/оставлено:
- +%    percent_add: A + B%;
- -%    percent_subtract: A - B%;
- %от   percent_of: A / B * 100;
- Δ%    percent_delta: (B - A) / A * 100;
- обычный %: B% как B/100, а после +/− — процент от левой части выражения.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext
from enum import Enum
from typing import Optional, List


ENGINE_PRECISION = 50
ERROR_TEXT = "Ошибка"


class Op(Enum):
    ADD = "+"
    SUB = "−"
    MUL = "×"
    DIV = "÷"
    PERCENT_ADD = "+%"
    PERCENT_SUBTRACT = "-%"
    PERCENT_OF = "%от"
    PERCENT_DELTA = "Δ%"


REMOVED_OPERATIONS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh",
    "log", "ln", "exp", "x^y", "factorial", "nCr", "nPr", "DEG", "RAD",
    "GRAD", "DRG", "FSE", "MTRX", "STAT", "CPLX", "CONST", "CONV",
    "BIN", "OCT", "DEC", "HEX", "mod", "i", "complex", "matrix", "converter",
    "scientific", "programmer", "MC", "MR", "M+", "M-", "MS", "memory",
}


@dataclass
class FormatOptions:
    group_digits: bool = False
    group_separator: str = " "
    decimal_separator: str = ","
    max_display_digits: int = 11
    exp_threshold_high: int = 16
    exp_threshold_low: int = -9


class Formatter:
    def __init__(self, options: FormatOptions | None = None):
        self.options = options or FormatOptions()

    def parse(self, text: str) -> Decimal:
        if not text or text in ("-", "+"):
            return Decimal(0)
        cleaned = str(text).replace(self.options.group_separator, "")
        cleaned = cleaned.replace(self.options.decimal_separator, ".")
        cleaned = cleaned.replace(" ", "")
        cleaned = cleaned.replace(",", ".")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return Decimal(0)

    def format(self, value: Decimal | int | float) -> str:
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        if value.is_nan() or value.is_infinite():
            return ERROR_TEXT
        if value == 0:
            return "0"
        abs_val = abs(value)
        try:
            adjusted = abs_val.adjusted()
        except Exception:
            adjusted = 0
        opts = self.options
        if adjusted >= opts.exp_threshold_high or adjusted <= opts.exp_threshold_low:
            return self._format_scientific(value)
        return self._format_fixed(value)

    def _format_fixed(self, value: Decimal) -> str:
        with localcontext() as ctx:
            ctx.prec = ENGINE_PRECISION
            quantum = Decimal("0.000000001")
            if value == value.to_integral_value():
                value = value.to_integral_value()
            else:
                value = value.quantize(quantum).normalize()
        sign = "-" if value < 0 else ""
        s = format(abs(value), "f")
        if "." in s:
            int_part, frac_part = s.split(".", 1)
            frac_part = frac_part.rstrip("0")
        else:
            int_part, frac_part = s, ""
        if self.options.group_digits:
            int_part = self._group(int_part)
        if frac_part:
            return f"{sign}{int_part}{self.options.decimal_separator}{frac_part}"
        return f"{sign}{int_part}"

    def _format_scientific(self, value: Decimal) -> str:
        with localcontext() as ctx:
            ctx.prec = self.options.max_display_digits
            value = +value
        s = format(value, "E")
        mantissa, exp = s.split("E")
        mantissa = mantissa.rstrip("0").rstrip(".")
        if not mantissa or mantissa == "-":
            mantissa += "0"
        mantissa = mantissa.replace(".", self.options.decimal_separator)
        if exp.startswith("-"):
            exp_sign = "-"
            exp_num = exp[1:]
        elif exp.startswith("+"):
            exp_sign = "+"
            exp_num = exp[1:]
        else:
            exp_sign = "+"
            exp_num = exp
        exp_num = exp_num.lstrip("0") or "0"
        return f"{mantissa}e{exp_sign}{exp_num}"

    def _group(self, int_part: str) -> str:
        sep = self.options.group_separator
        out = []
        for i, ch in enumerate(reversed(int_part)):
            if i and i % 3 == 0:
                out.append(sep)
            out.append(ch)
        return "".join(reversed(out))


@dataclass
class StandardState:
    display: str = "0"
    expression: str = ""
    accumulator: Decimal = Decimal(0)
    current_input: str = "0"
    pending_op: Optional[Op] = None
    pending_operand: Optional[Decimal] = None
    last_op: Optional[Op] = None
    last_operand: Optional[Decimal] = None
    is_new_input: bool = True
    error: Optional[str] = None
    history_entry: Optional[str] = None


@dataclass
class _Token:
    kind: str  # number | op | lparen | rparen
    value: Decimal | Op | None
    label: str


class _ExpressionParser:
    def __init__(self, tokens: list[_Token]):
        self.tokens = tokens
        self.pos = 0

    def parse(self) -> Decimal:
        if not self.tokens:
            return Decimal(0)
        result = self._parse_expression()
        if self.pos != len(self.tokens):
            raise InvalidOperation
        return result

    def _peek(self) -> _Token | None:
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def _take(self) -> _Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _parse_expression(self) -> Decimal:
        left = self._parse_term()
        while True:
            tok = self._peek()
            if not tok or tok.kind != "op" or tok.value not in {
                Op.ADD, Op.SUB, Op.PERCENT_ADD, Op.PERCENT_SUBTRACT, Op.PERCENT_OF, Op.PERCENT_DELTA,
            }:
                break
            op = self._take().value
            right = self._parse_term()
            left = self._apply(left, op, right)
        return left

    def _parse_term(self) -> Decimal:
        left = self._parse_factor()
        while True:
            tok = self._peek()
            if not tok or tok.kind != "op" or tok.value not in {Op.MUL, Op.DIV}:
                break
            op = self._take().value
            right = self._parse_factor()
            left = self._apply(left, op, right)
        return left

    def _parse_factor(self) -> Decimal:
        tok = self._peek()
        if tok is None:
            raise InvalidOperation
        if tok.kind == "number":
            self._take()
            return tok.value if isinstance(tok.value, Decimal) else Decimal(0)
        if tok.kind == "lparen":
            self._take()
            value = self._parse_expression()
            close = self._peek()
            if close is None or close.kind != "rparen":
                raise InvalidOperation
            self._take()
            return value
        raise InvalidOperation

    def _apply(self, a: Decimal, op: Op, b: Decimal) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = ENGINE_PRECISION
            if op == Op.ADD:
                return a + b
            if op == Op.SUB:
                return a - b
            if op == Op.MUL:
                return a * b
            if op == Op.DIV:
                if b == 0:
                    raise DivisionByZero
                return a / b
            if op == Op.PERCENT_ADD:
                return a * (Decimal(1) + b / Decimal(100))
            if op == Op.PERCENT_SUBTRACT:
                return a * (Decimal(1) - b / Decimal(100))
            if op == Op.PERCENT_OF:
                if b == 0:
                    raise DivisionByZero
                return a / b * Decimal(100)
            if op == Op.PERCENT_DELTA:
                if a == 0:
                    raise DivisionByZero
                return (b - a) / a * Decimal(100)
        raise InvalidOperation


class StandardEngine:
    def __init__(self, formatter: Formatter | None = None) -> None:
        self.formatter = formatter or Formatter()
        self.state = StandardState()
        self._history: List[str] = []
        self._tokens: list[_Token] = []
        self._current_label: str | None = None
        self._open_parens = 0
        self._just_closed_paren = False

    # ---------------------------- input ----------------------------
    def input_digit(self, d: str) -> None:
        if not d.isdigit() or len(d) != 1:
            return
        if self.state.error:
            self._reset()
        self._begin_fresh_number_if_needed()
        st = self.state
        if st.is_new_input or self._just_closed_paren:
            st.current_input = d
            st.is_new_input = False
            self._current_label = None
            self._just_closed_paren = False
        else:
            digits_only = st.current_input.replace("-", "").replace(".", "").lstrip("0")
            if len(digits_only) >= self.formatter.options.max_display_digits:
                return
            if st.current_input == "0":
                st.current_input = d
            elif st.current_input == "-0":
                st.current_input = "-" + d
            else:
                st.current_input += d
        st.display = self._format_input(st.current_input)
        self._sync_expression()

    def input_decimal(self) -> None:
        if self.state.error:
            self._reset()
        self._begin_fresh_number_if_needed()
        st = self.state
        if st.is_new_input or self._just_closed_paren:
            st.current_input = "0."
            st.is_new_input = False
            self._current_label = None
            self._just_closed_paren = False
        elif "." not in st.current_input:
            st.current_input += "."
        st.display = self._format_input(st.current_input)
        self._sync_expression()

    def backspace(self) -> None:
        st = self.state
        if st.error or st.is_new_input or self._just_closed_paren:
            return
        self._current_label = None
        if len(st.current_input) <= 1 or (len(st.current_input) == 2 and st.current_input.startswith("-")):
            st.current_input = "0"
            st.is_new_input = True
        else:
            st.current_input = st.current_input[:-1]
        st.display = self._format_input(st.current_input)
        self._sync_expression()

    # -------------------------- operators --------------------------
    def input_operator(self, op: Op) -> None:
        if self.state.error:
            self._reset()
        self._clear_history_marker_for_continuation()
        if self._last_token_is("op") and (self.state.is_new_input or self._just_closed_paren):
            self._tokens[-1] = _Token("op", op, op.value)
        else:
            if not self._just_closed_paren:
                self._commit_current_operand(force_if_empty=True)
            self._tokens.append(_Token("op", op, op.value))
        self.state.pending_op = op
        self.state.is_new_input = True
        self._current_label = None
        self._just_closed_paren = False
        self._sync_expression()

    def equals(self) -> None:
        if self.state.error:
            self._reset()
            return
        self._clear_history_marker_for_continuation(clear_tokens=False)
        if not self._just_closed_paren:
            self._commit_current_operand(force_if_empty=not self._tokens)
        while self._open_parens > 0:
            self._tokens.append(_Token("rparen", None, ")"))
            self._open_parens -= 1
        while self._tokens and self._tokens[-1].kind == "op":
            self._tokens.pop()
        if not self._tokens:
            return
        expr_done = self._tokens_to_label(self._tokens)
        try:
            result = self._eval_tokens(self._tokens)
        except (DivisionByZero, InvalidOperation, ValueError):
            self._set_error()
            return
        entry = f"{expr_done} = {self.formatter.format(result)}"
        self._history.append(entry)
        st = self.state
        st.history_entry = entry
        st.accumulator = result
        st.current_input = self._to_input_string(result)
        st.display = self.formatter.format(result)
        st.expression = ""
        st.pending_op = None
        st.pending_operand = None
        st.last_op = None
        st.last_operand = None
        st.is_new_input = True
        self._tokens = []
        self._current_label = None
        self._just_closed_paren = False

    # -------------------------- unary/common --------------------------
    def negate(self) -> None:
        if self.state.error:
            return
        if self._just_closed_paren:
            return
        st = self.state
        self._current_label = None
        if st.current_input.startswith("-"):
            st.current_input = st.current_input[1:]
        elif st.current_input != "0":
            st.current_input = "-" + st.current_input
        st.display = self._format_input(st.current_input)
        self._sync_expression()

    def percent(self) -> None:
        if self.state.error:
            return
        self._clear_history_marker_for_continuation()
        st = self.state
        current_value = self.formatter.parse(st.current_input)
        source_label = self._current_label or self.formatter.format(current_value)
        try:
            with localcontext() as ctx:
                ctx.prec = ENGINE_PRECISION
                pct_value = current_value / Decimal(100)
                if self._last_token_is("op") and self._tokens[-1].value in (Op.ADD, Op.SUB):
                    base_tokens = self._tokens[:-1]
                    if base_tokens:
                        base = self._eval_tokens(base_tokens)
                        pct_value = base * current_value / Decimal(100)
        except (DivisionByZero, InvalidOperation, ValueError):
            self._set_error()
            return
        st.current_input = self._to_input_string(pct_value)
        st.display = self.formatter.format(pct_value)
        st.is_new_input = False
        self._current_label = f"{source_label}%"
        self._just_closed_paren = False
        self._sync_expression()

    def reciprocal(self) -> None:
        def fn(v: Decimal) -> Decimal | None:
            if v == 0:
                return None
            return Decimal(1) / v
        self._unary("1/", fn)

    def square(self) -> None:
        self._unary("sqr", lambda v: v * v)

    def square_root(self) -> None:
        def fn(v: Decimal) -> Decimal | None:
            if v < 0:
                return None
            return v.sqrt()
        self._unary("√", fn)

    # -------------------------- parentheses --------------------------
    def open_paren(self) -> None:
        if self.state.error:
            self._reset()
        self._clear_history_marker_for_continuation()
        if (not self.state.is_new_input or self._just_closed_paren) and not self._last_token_is("op") and not self._last_token_is("lparen"):
            self._commit_current_operand(force_if_empty=True)
            self._tokens.append(_Token("op", Op.MUL, Op.MUL.value))
        self._tokens.append(_Token("lparen", None, "("))
        self._open_parens += 1
        self.state.current_input = "0"
        self.state.display = "0"
        self.state.is_new_input = True
        self._current_label = None
        self._just_closed_paren = False
        self._sync_expression()

    def close_paren(self) -> None:
        if self.state.error or self._open_parens <= 0:
            return
        if not self._just_closed_paren:
            self._commit_current_operand(force_if_empty=False)
        if self._last_token_is("op"):
            self._tokens.pop()
        if self._last_token_is("lparen"):
            self._tokens.append(_Token("number", Decimal(0), "0"))
        self._tokens.append(_Token("rparen", None, ")"))
        self._open_parens -= 1
        try:
            result = self._eval_tokens(self._tokens)
            self.state.current_input = self._to_input_string(result)
            self.state.display = self.formatter.format(result)
        except Exception:
            pass
        self.state.is_new_input = True
        self._current_label = None
        self._just_closed_paren = True
        self._sync_expression()

    # ---------------------------- clear ----------------------------
    def clear(self) -> None:
        self._reset()

    def clear_entry(self) -> None:
        st = self.state
        st.current_input = "0"
        st.display = "0"
        st.is_new_input = True
        st.error = None
        self._current_label = None
        self._sync_expression()

    # ---------------------------- history ----------------------------
    def history(self) -> List[str]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()

    # ---------------------------- private ----------------------------
    def _begin_fresh_number_if_needed(self) -> None:
        if self.state.history_entry and not self._tokens and self.state.is_new_input:
            self.state.history_entry = None
            self.state.expression = ""
            self.state.last_op = None
            self.state.last_operand = None

    def _clear_history_marker_for_continuation(self, clear_tokens: bool = True) -> None:
        if self.state.history_entry:
            self.state.history_entry = None
            self.state.last_op = None
            self.state.last_operand = None
            if clear_tokens:
                self._tokens = []
                self._open_parens = 0
                self._just_closed_paren = False

    def _commit_current_operand(self, force_if_empty: bool = False) -> None:
        if self._just_closed_paren:
            return
        if self.state.is_new_input and not force_if_empty:
            return
        if self._last_token_is("number") or self._last_token_is("rparen"):
            return
        value = self.formatter.parse(self.state.current_input)
        label = self._current_label or self.formatter.format(value)
        self._tokens.append(_Token("number", value, label))
        self.state.pending_operand = value

    def _last_token_is(self, kind: str) -> bool:
        return bool(self._tokens and self._tokens[-1].kind == kind)

    def _tokens_to_label(self, tokens: list[_Token]) -> str:
        parts: list[str] = []
        prev = ""
        for tok in tokens:
            if tok.kind == "lparen":
                if parts and prev not in ("op", "lparen"):
                    parts.append("×")
                parts.append("(")
            elif tok.kind == "rparen":
                if parts and parts[-1] == " ":
                    parts.pop()
                parts.append(")")
            elif tok.kind == "op":
                parts.append(f" {tok.label} ")
            else:
                parts.append(tok.label)
            prev = tok.kind
        text = "".join(parts)
        text = " ".join(text.split())
        text = text.replace("( ", "(").replace(" )", ")")
        return text.strip()

    def _sync_expression(self) -> None:
        tokens = list(self._tokens)
        if not self._just_closed_paren and not self.state.is_new_input:
            value = self.formatter.parse(self.state.current_input)
            label = self._current_label or self.formatter.format(value)
            if not (tokens and tokens[-1].kind in ("number", "rparen")):
                tokens.append(_Token("number", value, label))
        self.state.expression = self._tokens_to_label(tokens)

    def _eval_tokens(self, tokens: list[_Token]) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = ENGINE_PRECISION
            return _ExpressionParser(list(tokens)).parse()

    def _unary(self, label: str, fn) -> None:
        if self.state.error:
            return
        if self._just_closed_paren:
            return
        self._clear_history_marker_for_continuation()
        current_value = self.formatter.parse(self.state.current_input)
        arg_label = self._current_label or self.formatter.format(current_value)
        try:
            with localcontext() as ctx:
                ctx.prec = ENGINE_PRECISION
                result = fn(current_value)
            if result is None:
                self._set_error()
                return
        except (DivisionByZero, InvalidOperation, ValueError):
            self._set_error()
            return
        unary_expr = f"{label}({arg_label})"
        self.state.current_input = self._to_input_string(result)
        self.state.display = self.formatter.format(result)
        self.state.is_new_input = False
        self._current_label = unary_expr
        self._sync_expression()
        if not self._tokens:
            entry = f"{unary_expr} = {self.state.display}"
            self._history.append(entry)
            self.state.history_entry = entry
            self.state.expression = ""
            self.state.is_new_input = True
            self._current_label = unary_expr

    def _set_error(self) -> None:
        self.state.error = ERROR_TEXT
        self.state.display = ERROR_TEXT
        self.state.expression = ""
        self.state.is_new_input = True
        self.state.pending_op = None
        self.state.pending_operand = None
        self._tokens = []
        self._current_label = None
        self._open_parens = 0
        self._just_closed_paren = False

    def _reset(self) -> None:
        self.state = StandardState()
        self._tokens = []
        self._current_label = None
        self._open_parens = 0
        self._just_closed_paren = False

    def _format_input(self, raw: str) -> str:
        if raw in ("", "-"):
            return "0"
        if raw.endswith("."):
            int_part = raw.rstrip(".")
            sign = "-" if int_part.startswith("-") else ""
            digits = int_part.lstrip("-") or "0"
            grouped = self.formatter._group(digits) if self.formatter.options.group_digits else digits
            return f"{sign}{grouped}{self.formatter.options.decimal_separator}"
        try:
            value = Decimal(raw)
        except InvalidOperation:
            return raw
        return self.formatter.format(value)

    def _to_input_string(self, value: Decimal) -> str:
        if value == 0:
            return "0"
        s = format(value, "f")
        if "." in s:
            int_part, frac_part = s.split(".", 1)
            frac_part = frac_part.rstrip("0")
            return f"{int_part}.{frac_part}" if frac_part else int_part
        return s


ACTION_TO_OP = {
    "op:+": Op.ADD,
    "op:-": Op.SUB,
    "op:*": Op.MUL,
    "op:/": Op.DIV,
    "percent_add": Op.PERCENT_ADD,
    "percent_subtract": Op.PERCENT_SUBTRACT,
    "percent_of": Op.PERCENT_OF,
    "percent_delta": Op.PERCENT_DELTA,
}
