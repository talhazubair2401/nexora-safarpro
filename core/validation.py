"""Small, explicit input validation used by every API action."""
import datetime as dt
import re
from decimal import Decimal, InvalidOperation

TWO = Decimal("0.01")


def D(v) -> Decimal:
    if v is None or v == "":
        return Decimal("0.00")
    return Decimal(str(v)).quantize(TWO)


class ActionError(Exception):
    """Raised for user-correctable problems. `errors` maps field -> message."""

    def __init__(self, message="", errors=None, status=400):
        super().__init__(message or "Please correct the highlighted fields.")
        self.message = message or "Please correct the highlighted fields."
        self.errors = errors or {}
        self.status = status


class Form:
    def __init__(self, data):
        self.data = data or {}
        self.errors = {}
        self.v = {}

    def _raw(self, k):
        x = self.data.get(k)
        return x.strip() if isinstance(x, str) else x

    def err(self, k, msg):
        self.errors.setdefault(k, msg)

    def str(self, k, required=False, max_len=250, label=None, pattern=None, pattern_msg=None):
        x = self._raw(k)
        x = "" if x is None else str(x)
        if required and not x:
            self.err(k, "This field is required.")
        elif len(x) > max_len:
            self.err(k, f"Keep this under {max_len} characters.")
        elif x and pattern and not re.fullmatch(pattern, x):
            self.err(k, pattern_msg or "Invalid format.")
        self.v[k] = x
        return x

    def text(self, k, required=False, max_len=4000):
        return self.str(k, required, max_len)

    def money(self, k, required=False, min_value=Decimal("0"), max_value=None, whole=True):
        x = self._raw(k)
        if x in (None, ""):
            if required:
                self.err(k, "This field is required.")
            self.v[k] = Decimal("0.00")
            return self.v[k]
        try:
            d = Decimal(str(x))
        except (InvalidOperation, ValueError):
            self.err(k, "Enter a valid amount.")
            self.v[k] = Decimal("0.00")
            return self.v[k]
        if not d.is_finite():
            self.err(k, "Enter a valid amount.")
        elif whole and d != d.to_integral_value():
            self.err(k, "Enter a whole rupee amount (no paisa).")
        elif d < min_value:
            self.err(k, f"Must be at least {min_value:,.0f}.")
        elif max_value is not None and d > max_value:
            self.err(k, f"Must not exceed {max_value:,.0f}.")
        self.v[k] = d.quantize(TWO) if d.is_finite() else Decimal("0.00")
        return self.v[k]

    def int(self, k, required=False, min_value=0, max_value=None):
        x = self._raw(k)
        if x in (None, ""):
            if required:
                self.err(k, "This field is required.")
            self.v[k] = None
            return None
        try:
            n = int(str(x))
        except ValueError:
            self.err(k, "Enter a whole number.")
            self.v[k] = None
            return None
        if n < min_value:
            self.err(k, f"Must be at least {min_value}.")
        if max_value is not None and n > max_value:
            self.err(k, f"Must not exceed {max_value}.")
        self.v[k] = n
        return n

    def number(self, k, required=False, min_value=0, max_value=None):
        x = self._raw(k)
        if x in (None, ""):
            if required:
                self.err(k, "This field is required.")
            self.v[k] = None
            return None
        try:
            n = Decimal(str(x))
        except (InvalidOperation, ValueError):
            self.err(k, "Enter a number.")
            return None
        if n < min_value or (max_value is not None and n > max_value):
            self.err(k, "Out of range.")
        self.v[k] = n
        return n

    def date(self, k, required=False):
        x = self._raw(k)
        if not x:
            if required:
                self.err(k, "This field is required.")
            self.v[k] = None
            return None
        try:
            d = dt.date.fromisoformat(str(x)[:10])
        except ValueError:
            self.err(k, "Enter a valid date.")
            d = None
        self.v[k] = d
        return d

    def choice(self, k, choices, required=True, default=None):
        x = self._raw(k) or default
        if x in (None, ""):
            if required:
                self.err(k, "This field is required.")
            self.v[k] = None
            return None
        if x not in choices:
            self.err(k, "Choose a valid option.")
        self.v[k] = x
        return x

    def bool(self, k):
        x = self.data.get(k)
        b = x in (True, "true", "1", 1, "on", "yes")
        self.v[k] = b
        return b

    def check(self):
        if self.errors:
            raise ActionError("Please correct the highlighted fields.", self.errors)
        return self.v


PK_MOBILE = r"(\+92|0)3\d{2}-?\s?\d{7}"


def norm_phone(p):
    digits = re.sub(r"\D", "", p or "")
    if digits.startswith("92"):
        digits = "0" + digits[2:]
    return digits
