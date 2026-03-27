# ──────────────────────────────────────────────────────────────────────────────
#  ui_helpers.py  —  Shared UI building blocks
#  v1.0.0
# ──────────────────────────────────────────────────────────────────────────────

__version__ = "1.0.0"

import streamlit as st


def render_empty_state(
    icon:         str,
    title:        str,
    message:      str,
    action_label: str = None,
    action_key:   str = None,
) -> bool:
    """
    Render a consistent, centered empty-state block.

    Args:
        icon:         Large emoji or symbol (e.g. "🔍", "📭")
        title:        Short heading line
        message:      Descriptive sentence
        action_label: Optional CTA button label
        action_key:   Unique Streamlit key for the button

    Returns:
        True if the action button was clicked, False otherwise.
    """
    st.markdown(
        f"""
        <div style="text-align:center;padding:3rem 1.5rem;opacity:0.7;">
            <div style="font-size:2.8rem;margin-bottom:0.6rem;line-height:1">{icon}</div>
            <div style="font-size:1.05rem;font-weight:600;margin-bottom:0.4rem">{title}</div>
            <div style="font-size:0.88rem;color:#718096;">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if action_label and action_key:
        cols = st.columns([1, 2, 1])
        return cols[1].button(action_label, key=action_key, use_container_width=True)
    return False


def confidence_badge(score: float) -> str:
    """
    Return a colored emoji badge string for a 0.0–1.0 confidence score.
    Intended for use in dataframe cells.
    """
    if score >= 0.90:
        return f"🟢 {score:.0%}"
    if score >= 0.70:
        return f"🟡 {score:.0%}"
    return f"🔴 {score:.0%}"
