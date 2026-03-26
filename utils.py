"""
utils.py — Shared UI + formatting helpers
"""

__version__ = "1.0.0"

import streamlit as st
from typing import Any, Optional


# ──────────────────────────────────────────────────────────────────────────────
#  SMART NUMBER INPUT
# ──────────────────────────────────────────────────────────────────────────────

def _smart_fmt(value: float) -> str:
    """
    Return a C-style format string based on the value:
      whole number  → "%.0f"   (no decimal point)
      real number   → "%.2f"   (2 decimal places in view, full precision stored)
    """
    try:
        if float(value) == int(float(value)):
            return "%.0f"
    except (TypeError, ValueError, OverflowError):
        pass
    return "%.2f"


def num_input(
    label: str,
    value: Any = 0,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    step: float = 1.0,
    key: Optional[str] = None,
    help: Optional[str] = None,
    label_visibility: str = "visible",
    **kwargs,
) -> float:
    """
    Drop-in replacement for st.number_input with smart formatting:
    - Whole numbers display without a decimal point (1, 5, 42)
    - Non-whole numbers display to 2 decimal places (1.50, 3.25)
    - Full precision is always stored
    - step=1 means +/- increments whole numbers, but typing any decimal works
    - Direct keyboard entry is the primary interaction model
    """
    v = float(value) if value is not None else 0.0
    fmt = _smart_fmt(v)

    return st.number_input(
        label,
        value=v,
        min_value=float(min_value) if min_value is not None else None,
        max_value=float(max_value) if max_value is not None else None,
        step=step,
        format=fmt,
        key=key,
        help=help,
        label_visibility=label_visibility,
        **kwargs,
    )


# ──────────────────────────────────────────────────────────────────────────────
#  SMART NUMBER DISPLAY  (for markdown / dataframe cells)
# ──────────────────────────────────────────────────────────────────────────────

def fmt_num(value: Any, prefix: str = "", suffix: str = "") -> str:
    """
    Format a number for display:
      whole  → "42"
      real   → "42.25"   (2 decimal places, trailing zero kept for alignment)
    """
    try:
        v = float(value)
        if v == int(v):
            return f"{prefix}{int(v):,}{suffix}"
        return f"{prefix}{v:,.2f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def fmt_currency(value: Any) -> str:
    """$42  or  $42.25"""
    return fmt_num(value, prefix="$")
