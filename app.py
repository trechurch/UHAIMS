"""
UHA Inventory Management System
Streamlit Community Cloud — app shell

v5.0.0 — Self-Describing Object Architecture (SDOA).
         This file is a pure shell. All logic lives in modules/.
         Adding a module = drop one file in modules/. Nothing here changes.
"""

import streamlit as st

# ── Page config — must be first Streamlit call ───────────────────────────────
st.set_page_config(
    page_title="UHA IMS",
    page_icon="🏟️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Imports ───────────────────────────────────────────────────────────────────
from database import InventoryDatabase
from registry import get_registry

__version__ = "5.0.0"

# ── end of imports ────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  BOOTSTRAP
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_db():
    return InventoryDatabase()


def _init():
    if "page_key"      not in st.session_state: st.session_state.page_key      = "dashboard"
    if "prev_page_key" not in st.session_state: st.session_state.prev_page_key = None
    if "show_top_nav"  not in st.session_state: st.session_state.show_top_nav  = True

# ── end of bootstrap ─────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  QUERY PARAM ROUTING
# ──────────────────────────────────────────────────────────────────────────────

def _handle_query_params(registry):
    params = st.query_params
    if "toggle_nav" in params:
        st.session_state.show_top_nav = not st.session_state.show_top_nav
        st.query_params.clear()
        st.rerun()
    if "page" in params:
        key = params["page"]
        if key in registry.page_keys():
            registry.on_navigate_away(st.session_state.page_key)
            st.session_state.prev_page_key = st.session_state.page_key
            st.session_state.page_key = key
        st.query_params.clear()
        st.rerun()

# ── end of query param routing ────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  SIDEBAR  — built entirely from registry manifests, nothing hardcoded
# ──────────────────────────────────────────────────────────────────────────────

def _render_sidebar(registry):
    with st.sidebar:
        st.image("https://img.icons8.com/emoji/96/stadium.png", width=48)
        st.markdown("**UHA IMS**")
        st.caption("TDECU Stadium · Compass Group")
        st.markdown("---")

        # Top nav toggle
        show_nav = st.checkbox(
            "☰  Top Navigation Bar",
            value=st.session_state.show_top_nav,
        )
        if show_nav != st.session_state.show_top_nav:
            st.session_state.show_top_nav = show_nav
            st.rerun()

        st.markdown("---")

        # Nav built from registry — zero hardcoded page names
        items  = registry.sidebar_items()
        labels = [f"{i['icon']}  {i['label']}" for i in items]
        keys   = [i["page_key"] for i in items]

        if not items:
            st.warning("No modules registered yet.")
            return

        cur_idx = keys.index(st.session_state.page_key) \
                  if st.session_state.page_key in keys else 0

        chosen     = st.radio("Navigate", labels, index=cur_idx)
        chosen_key = keys[labels.index(chosen)]

        if chosen_key != st.session_state.page_key:
            registry.on_navigate_away(st.session_state.page_key)
            st.session_state.prev_page_key = st.session_state.page_key
            st.session_state.page_key = chosen_key
            st.rerun()

        st.markdown("---")
        st.caption("☁️ OneDrive — pending IT approval")

# ── end of sidebar ────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    _init()
    db       = get_db()
    registry = get_registry(db=db)
    _handle_query_params(registry)
    _render_sidebar(registry)
    registry.dispatch(st.session_state.page_key)


if __name__ == "__main__":
    main()

# ── end of app.py ─────────────────────────────────────────────────────────────
