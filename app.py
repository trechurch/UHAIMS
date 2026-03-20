"""
UHA Inventory Management System
Streamlit Community Cloud — app shell

v5.2.3  —  Fix: sidebar radio no longer overwrites admin page_key.
            Admin pages bypass the radio selection entirely.
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
from version_syncer import VersionSyncer

__version__ = "5.2.3"

ADMIN_PAGES = {"db_import"}

# ──────────────────────────────────────────────────────────────────────────────
#  BOOTSTRAP
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_db():
    return InventoryDatabase()


def _init():
    if "page_key"      not in st.session_state:
        url_page = st.query_params.get("page", "dashboard")
        st.session_state.page_key = url_page if url_page else "dashboard"
    if "prev_page_key" not in st.session_state:
        st.session_state.prev_page_key = None
    if "show_top_nav"  not in st.session_state:
        st.session_state.show_top_nav  = True


def _read_query_params():
    params = st.query_params
    if not params:
        return
    if "page" in params:
        st.session_state.page_key = params["page"]
        st.query_params.clear()

# ──────────────────────────────────────────────────────────────────────────────
#  VERSION BADGE
# ──────────────────────────────────────────────────────────────────────────────

def _render_version_badge(registry):
    with st.sidebar:
        st.markdown("---")
        with st.expander("📦 Versions", expanded=False):
            try:
                from database import InventoryDatabase as _IDB
                db_ver = _IDB.SERVICE_MANIFEST.get("version", "?")
            except Exception:
                db_ver = "err"
            try:
                from importer import InventoryImporter as _IMP
                imp_ver = _IMP.SERVICE_MANIFEST.get("version", "?")
            except Exception:
                imp_ver = "err"
            try:
                import base as _base
                base_ver = getattr(_base, "__version__", "?")
            except Exception:
                base_ver = "err"
            try:
                import registry as _reg
                reg_ver = getattr(_reg, "__version__", "?")
            except Exception:
                reg_ver = "err"

            lines = [
                ("app.py",      __version__),
                ("base.py",     base_ver),
                ("registry.py", reg_ver),
                ("database.py", db_ver),
                ("importer.py", imp_ver),
            ]
            rows = "".join(
                f"<b style='color:#4A4E55'>{n}</b>&nbsp;&nbsp;v{v}<br>"
                for n, v in lines
            )
            module_rows = "".join(
                f"<b style='color:#4A4E55'>{m.id}</b>&nbsp;&nbsp;v{m.version}<br>"
                for m in sorted(registry.all(), key=lambda x: x.id)
            )
            st.markdown(
                f"<div style='font-size:11px;color:#6E737A;"
                f"font-family:monospace;line-height:1.8'>"
                f"{rows}{module_rows}</div>",
                unsafe_allow_html=True,
            )
            if registry.has_errors():
                st.markdown(
                    f"<div style='font-size:11px;color:#D64545'>"
                    f"⚠️ {len(registry.errors())} load error(s)</div>",
                    unsafe_allow_html=True,
                )

# ──────────────────────────────────────────────────────────────────────────────
#  SIDEBAR
# ──────────────────────────────────────────────────────────────────────────────

def _render_sidebar(registry, syncer):
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

        # ── Key fix: if we're on an admin page, show nav but don't
        #    let the radio overwrite the current page_key ────────────────────
        if st.session_state.page_key in ADMIN_PAGES:
            # Show nav as read-only context, default to first item
            st.radio("Navigate", labels, index=0, disabled=True)
            st.markdown("---")
            st.warning("🔧 Admin mode")
            if st.button("← Back to App"):
                st.session_state.page_key = "dashboard"
                st.rerun()
        else:
            current = st.session_state.page_key
            cur_idx = keys.index(current) if current in keys else 0
            chosen     = st.radio("Navigate", labels, index=cur_idx)
            chosen_key = keys[labels.index(chosen)]
            if chosen_key != st.session_state.page_key:
                registry.on_navigate_away(st.session_state.page_key)
                st.session_state.prev_page_key = st.session_state.page_key
                st.session_state.page_key = chosen_key
                st.rerun()

    _render_version_badge(registry)
    syncer.render_badge()

# ──────────────────────────────────────────────────────────────────────────────
#  DIAGNOSTICS
# ──────────────────────────────────────────────────────────────────────────────

def _show_diagnostics(registry, syncer):
    with st.expander("🔧 Registry Diagnostics", expanded=False):
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
            for e in d["load_errors"]:
                st.error(e)
        else:
            st.success("✅ No load errors.")

    with st.expander("🔀 Version Sync", expanded=False):
        syncer.render_panel()

# ──────────────────────────────────────────────────────────────────────────────
#  ADMIN PAGES
# ──────────────────────────────────────────────────────────────────────────────

def _render_admin_page(page_key: str):
    if page_key == "db_import":
        try:
            import database_sheet_importer
            database_sheet_importer.render()
        except Exception as exc:
            import traceback
            st.error(f"DB importer failed to load: {exc}")
            st.code(traceback.format_exc())

# ──────────────────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    _read_query_params()
    _init()

    db       = get_db()
    registry = get_registry(_db=db)
    syncer   = VersionSyncer(registry=registry, repo="trechurch/UHAIMS")

    _render_sidebar(registry, syncer)

    if st.session_state.page_key in ADMIN_PAGES:
        _render_admin_page(st.session_state.page_key)
    else:
        _show_diagnostics(registry, syncer)
        registry.dispatch(st.session_state.page_key)


if __name__ == "__main__":
    main()

# ── end of app.py ─────────────────────────────────────────────────────────────
