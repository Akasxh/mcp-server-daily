"""Utility dispatcher with multiple sub-tools.

This module exposes a :func:`dispatch` function that interprets simple
text commands and routes them to the appropriate utility.

Supported commands:
    - ``currency <amount> <from_currency> <to_currency>``
    - ``unit <value> <from_unit> <to_unit>``
    - ``time <city>``
    - ``split <total> <num_people> <tip_percent>``
    - ``age <YYYY-MM-DD>``
    - ``calc <expression>``

Each command returns a human-readable string or an error message if
input is invalid.
"""

from __future__ import annotations

import ast
import math
import operator as op
from datetime import date, datetime
from typing import Callable
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Currency Converter
# ---------------------------------------------------------------------------

_CURRENCY_RATES: dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 150.0,
    "AUD": 1.52,
    "CAD": 1.37,
    "CHF": 0.90,
    "CNY": 7.10,
    "INR": 83.0,
}


def convert_currency(amount: float, from_currency: str, to_currency: str) -> float:
    """Convert ``amount`` from one currency to another using static rates."""
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    if from_currency not in _CURRENCY_RATES or to_currency not in _CURRENCY_RATES:
        raise ValueError("Unsupported currency code.")
    usd = amount / _CURRENCY_RATES[from_currency]
    return usd * _CURRENCY_RATES[to_currency]


# ---------------------------------------------------------------------------
# Unit Converter
# ---------------------------------------------------------------------------


def convert_units(value: float, from_unit: str, to_unit: str) -> float:
    """Convert between basic metric and imperial units.

    Supported conversions:
        - meters ↔ feet (m, ft)
        - kilometers ↔ miles (km, mi)
        - kilograms ↔ pounds (kg, lb)
        - Celsius ↔ Fahrenheit (c, f)
    """

    conversions: dict[tuple[str, str], Callable[[float], float]] = {
        ("m", "ft"): lambda v: v * 3.28084,
        ("ft", "m"): lambda v: v / 3.28084,
        ("km", "mi"): lambda v: v * 0.621371,
        ("mi", "km"): lambda v: v / 0.621371,
        ("kg", "lb"): lambda v: v * 2.20462,
        ("lb", "kg"): lambda v: v / 2.20462,
        ("c", "f"): lambda v: v * 9 / 5 + 32,
        ("f", "c"): lambda v: (v - 32) * 5 / 9,
    }
    key = (from_unit.lower(), to_unit.lower())
    if key not in conversions:
        raise ValueError("Unsupported unit conversion.")
    return conversions[key](value)


# ---------------------------------------------------------------------------
# Time Zone Checker
# ---------------------------------------------------------------------------

_CITY_TIMEZONES: dict[str, str] = {
    "new york": "America/New_York",
    "los angeles": "America/Los_Angeles",
    "london": "Europe/London",
    "paris": "Europe/Paris",
    "tokyo": "Asia/Tokyo",
    "sydney": "Australia/Sydney",
    "delhi": "Asia/Kolkata",
}


def time_in(city: str) -> str:
    """Return the current time in the given ``city``."""
    tz_name = _CITY_TIMEZONES.get(city.lower())
    if not tz_name:
        raise ValueError("Unknown city.")
    now = datetime.now(ZoneInfo(tz_name))
    return now.strftime("%Y-%m-%d %H:%M:%S (%Z)")


# ---------------------------------------------------------------------------
# Bill Splitter
# ---------------------------------------------------------------------------


def split_bill(total: float, num_people: int, tip_percent: float) -> float:
    """Split ``total`` among ``num_people`` adding ``tip_percent`` tip."""
    if num_people <= 0:
        raise ValueError("Number of people must be positive.")
    if total < 0 or tip_percent < 0:
        raise ValueError("Total and tip must be non-negative.")
    tip_amount = total * tip_percent / 100
    return (total + tip_amount) / num_people


# ---------------------------------------------------------------------------
# Age Calculator
# ---------------------------------------------------------------------------


def calculate_age(birthdate: str) -> int:
    """Return the age in whole years for the given ``birthdate`` (YYYY-MM-DD)."""
    try:
        bdate = datetime.strptime(birthdate, "%Y-%m-%d").date()
    except ValueError as exc:  # invalid format
        raise ValueError("Birthdate must be in YYYY-MM-DD format.") from exc
    today = date.today()
    if bdate > today:
        raise ValueError("Birthdate cannot be in the future.")
    years = today.year - bdate.year - ((today.month, today.day) < (bdate.month, bdate.day))
    return years


# ---------------------------------------------------------------------------
# Scientific Calculator
# ---------------------------------------------------------------------------

_ALLOWED_NAMES = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
_ALLOWED_NAMES.update({"pi": math.pi, "e": math.e})
_ALLOWED_OPERATORS: dict[type, Callable[[float, float], float]] = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.Mod: op.mod,
}


def scientific_calculator(expression: str) -> float:
    """Evaluate an algebraic ``expression`` safely."""
    try:
        node = ast.parse(expression, mode="eval")
        return _eval(node.body)
    except Exception as exc:
        raise ValueError("Invalid expression.") from exc


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):  # Python 3.11 uses Constant
        return node.value
    if isinstance(node, ast.Num):  # pragma: no cover - for older AST nodes
        return node.n
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _eval(node.operand)
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _ALLOWED_OPERATORS:
            raise ValueError("Unsupported operator.")
        left, right = _eval(node.left), _eval(node.right)
        return _ALLOWED_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_NAMES:
            raise ValueError("Function not allowed.")
        args = [_eval(arg) for arg in node.args]
        return _ALLOWED_NAMES[node.func.id](*args)
    if isinstance(node, ast.Name) and node.id in _ALLOWED_NAMES:
        return _ALLOWED_NAMES[node.id]
    raise ValueError("Invalid expression.")


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def dispatch(query: str) -> str:
    """Interpret ``query`` and route to the appropriate utility."""
    parts = query.strip().split()
    if not parts:
        return "Please provide a command."
    cmd, *args = parts
    cmd = cmd.lower()

    try:
        if cmd == "currency":
            if len(args) != 3:
                return "Usage: currency <amount> <from_currency> <to_currency>"
            amount = float(args[0])
            result = convert_currency(amount, args[1], args[2])
            return f"{amount} {args[1].upper()} = {result:.2f} {args[2].upper()}"
        if cmd == "unit":
            if len(args) != 3:
                return "Usage: unit <value> <from_unit> <to_unit>"
            value = float(args[0])
            result = convert_units(value, args[1], args[2])
            return f"{value} {args[1]} = {result:.2f} {args[2]}"
        if cmd == "time":
            if not args:
                return "Usage: time <city>"
            city = " ".join(args)
            current_time = time_in(city)
            return f"The time in {city.title()} is {current_time}"
        if cmd == "split":
            if len(args) != 3:
                return "Usage: split <total> <num_people> <tip_percent>"
            total = float(args[0])
            num_people = int(args[1])
            tip_percent = float(args[2])
            each = split_bill(total, num_people, tip_percent)
            return f"Each person should pay {each:.2f}"
        if cmd == "age":
            if len(args) != 1:
                return "Usage: age <YYYY-MM-DD>"
            years = calculate_age(args[0])
            return f"You are {years} years old."
        if cmd == "calc":
            if not args:
                return "Usage: calc <expression>"
            expression = " ".join(args)
            result = scientific_calculator(expression)
            return f"{expression} = {result}"
        return "Unknown command. Available: currency, unit, time, split, age, calc."
    except ValueError as exc:
        return str(exc)


if __name__ == "__main__":  # pragma: no cover - manual usage
    while True:
        try:
            user_input = input("Enter command (or 'quit'): ")
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.strip().lower() in {"quit", "exit"}:
            break
        print(dispatch(user_input))
