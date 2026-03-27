"""
utils.py — Shared UI + formatting helpers
"""

__version__ = "1.1.0"

import time as _time
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


# ──────────────────────────────────────────────────────────────────────────────
#  BACKGROUND PROCESS PROGRESS INDICATOR
# ──────────────────────────────────────────────────────────────────────────────

def _fmt_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    return f"{m}m {s:02d}s"


def _rate_label(done: int, elapsed: float) -> str:
    if elapsed < 0.5 or done < 2:
        return ""
    rate = done / elapsed
    if rate >= 1:
        return f"{rate:.0f}/s"
    return f"{1/rate:.1f}s each"


def render_bg_progress(task_id: str, *, compact: bool = False,
                       auto_refresh: bool = True,
                       refresh_interval: float = 1.5) -> bool:
    """
    Render a live progress indicator for a background task.

    task_id         — matches the ProgressTracker task_id
    compact         — True = one-line sidebar-friendly version
    auto_refresh    — rerun Streamlit while the task is still running
    refresh_interval— seconds between auto-reruns

    Returns True if the task is still running (caller can act accordingly).
    """
    from progress_tracker import read_progress

    data = read_progress(task_id)
    if data is None:
        return False

    finished = data.get("finished", False)
    errored  = data.get("errored",  False)
    stalled  = data.get("stalled",  False)
    pct      = float(data.get("pct",     0))
    done     = int(  data.get("done",    0))
    total    = int(  data.get("total",   1))
    label    = str(  data.get("label",  "Background Process"))
    status   = str(  data.get("status", ""))
    elapsed  = float(data.get("elapsed", 0))
    eta      = data.get("eta")          # seconds remaining, or None
    pct_int  = int(pct * 100)

    still_running = not finished and not stalled and not errored

    # ── Pick colours ──────────────────────────────────────────────────────────
    if errored:
        bar_color = "#ef4444"; icon = "❌"
    elif stalled:
        bar_color = "#f59e0b"; icon = "⚠️"
    elif finished:
        bar_color = "#22c55e"; icon = "✅"
    else:
        bar_color = "#3b82f6"; icon = "⚙️"

    # ── Spinning dot (CSS keyframe) injected once per session ─────────────────
    if still_running and "bg_progress_css_injected" not in st.session_state:
        st.markdown(
            "<style>"
            "@keyframes uha-pulse{0%,100%{opacity:1}50%{opacity:.3}}"
            ".uha-pulse{animation:uha-pulse 1.2s ease-in-out infinite;"
            "display:inline-block;}"
            "</style>",
            unsafe_allow_html=True,
        )
        st.session_state["bg_progress_css_injected"] = True

    pulse = '<span class="uha-pulse">●</span> ' if still_running else ""

    if compact:
        # ── One-liner for sidebar ─────────────────────────────────────────────
        eta_str = f" · ETA {_fmt_time(eta)}" if eta and still_running else ""
        st.markdown(
            f"<div style='font-size:12px;padding:4px 0'>"
            f"{pulse}<strong>{icon} {label}</strong> "
            f"<span style='color:{bar_color};font-weight:700'>{pct_int}%</span>"
            f"{eta_str}</div>",
            unsafe_allow_html=True,
        )
        st.progress(pct)
        if status:
            st.caption(f"↳ {status}")
    else:
        # ── Full card ─────────────────────────────────────────────────────────
        # Header row
        hc1, hc2 = st.columns([3, 1])
        hc1.markdown(
            f"<div style='font-size:14px;font-weight:700;color:#1e293b'>"
            f"{pulse}{icon} {label}</div>",
            unsafe_allow_html=True,
        )
        hc2.markdown(
            f"<div style='text-align:right;font-size:26px;font-weight:800;"
            f"color:{bar_color};line-height:1'>{pct_int}%</div>",
            unsafe_allow_html=True,
        )

        # Progress bar with custom colour
        st.markdown(
            f"<div style='background:#e2e8f0;border-radius:6px;height:12px;"
            f"overflow:hidden;margin:6px 0'>"
            f"<div style='width:{pct_int}%;background:{bar_color};height:100%;"
            f"border-radius:6px;transition:width 0.4s ease'></div></div>",
            unsafe_allow_html=True,
        )

        # Counters row
        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric("Done",    f"{done:,}")
        cc2.metric("Total",   f"{total:,}")
        cc3.metric("Elapsed", _fmt_time(elapsed))
        cc4.metric("ETA",
                   _fmt_time(eta) if still_running else ("Done" if finished else "—"),
                   help="Estimated time to completion based on current rate")

        # Throughput + status
        rate = _rate_label(done, elapsed)
        if rate or status:
            parts = []
            if rate:         parts.append(f"⚡ {rate}")
            if status:       parts.append(f"↳ {status}")
            st.caption("  ·  ".join(parts))

        if errored:
            st.error(status or "Process ended with an error.")
        elif stalled:
            st.warning(status or "Process may have stalled — no recent update.")
        elif finished:
            st.success(f"Completed in {_fmt_time(elapsed)}")

    # ── Auto-refresh while running ────────────────────────────────────────────
    if auto_refresh and still_running:
        _time.sleep(refresh_interval)
        st.rerun()

    return still_running


def render_all_active_progress(compact: bool = False) -> int:
    """
    Render progress cards for every currently-running task.
    Returns count of active tasks.
    """
    from progress_tracker import list_active_tasks
    tasks = list_active_tasks()
    for t in tasks:
        render_bg_progress(t["task_id"], compact=compact, auto_refresh=False)
    # Only trigger one rerun at the end if anything is still live
    running = [t for t in tasks if not t.get("stalled")]
    if running:
        _time.sleep(1.5)
        st.rerun()
    return len(running)
