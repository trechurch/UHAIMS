"""
UHA Inventory Management System
Streamlit Community Cloud — app shell

v5.0.2  —  Registry diagnostics added to screen.
            Lazy import fix in import_dashboard.py.
"""

import streamlit as st

st.set_page_config(
    page_title="UHA IMS",
    page_icon="🏟️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from database import InventoryDatabase
from registry import get_registry

__version__ = "5.0.2"

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

# ──────────────────────────────────────────────────────────────────────────────
#  SIDEBAR
# ──────────────────────────────────────────────────────────────────────────────

def _render_sidebar(registry):
    with st.sidebar:
        st.image("https://img.icons8.com/emoji/96/stadium.png", width=48)
        st.markdown("**UHA IMS**")
        st.caption("TDECU Stadium · Compass Group")
        st.markdown("---")

        show_nav = st.checkbox(
            "☰  Top Navigation Bar",
            value=st.session_state.show_top_nav,
        )
        if show_nav != st.session_state.show_top_nav:
            st.session_state.show_top_nav = show_nav
            st.rerun()

        st.markdown("---")

        items  = registry.sidebar_items()
        labels = [f"{i['icon']}  {i['label']}" for i in items]
        keys   = [i["page_key"] for i in items]

        if not items:
            st.warning("No modules registered.")
        else:
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

# ──────────────────────────────────────────────────────────────────────────────
#  DIAGNOSTICS  (remove once all modules confirmed loading)
# ──────────────────────────────────────────────────────────────────────────────

def _show_diagnostics(registry):
    with st.expander("🔧 Registry Diagnostics", expanded=True):
        d = registry.diagnostics()
        st.markdown(
            f"**Modules:** {d['total_modules']} total · "
            f"{d['active']} active · "
            f"{d['stubs']} stubs · "
            f"{d['disabled']} disabled"
        )
        st.markdown("**Registered page keys:**")
        st.code(", ".join(d["registered_pages"]) or "none")
        if d["load_errors"]:
            st.markdown("**❌ Load errors:**")
            for e in d["load_errors"]:
                st.error(e)
        else:
            st.success("✅ No load errors.")

# ──────────────────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    _init()
    db       = get_db()
    registry = get_registry(_db=db)
    _handle_query_params(registry)
    _render_sidebar(registry)
    _show_diagnostics(registry)
    registry.dispatch(st.session_state.page_key)


if __name__ == "__main__":
    main()

# ── end of app.py ─────────────────────────────────────────────────────────────
