"""
UHA Inventory Management System — Streamlit entry point
v5.2.0

Architecture: SDOA (Self-Describing Object Architecture)

Responsibilities of this file (and ONLY this file):
  - Page config  (must be first Streamlit call)
  - DB + Registry singletons
  - Auth gate
  - Top nav bar  (HTML/CSS dropdown, driven by ui_skeleton.MenuBar)
  - Sidebar      (user badge · registry nav · version syncer · admin toggles)
  - Query-param routing → registry.dispatch(page_key)
  - Settings page  (admin only — feature toggles + user management)
  - Fallback pages for gl_codes / history / export  (no module yet)

Adding a new dashboard module:
  Drop a .py file in modules/ — registry auto-discovers it on next boot.
  Zero changes required here.

Changelog v5.2.0:
  - Multi-database support added
  - Database switcher in sidebar (top, below cost center branding)
  - Dynamic database factory replaces singleton pattern
  - Cost center info derived from selected database
  - Registry cleared on database switch to reload modules

Changelog v5.1.0:
  - Login section moved to bottom of sidebar
  - "✏️ Name" button moved from user badge to Settings→User Management
  - "Compass Group · Inventory IMS" branding removed
  - Stadium icon/info now based on Cost Center
  - Sidebar collapse/expand chevron logic improved
"""

__version__ = "5.4.0"

import os
import importlib
import streamlit as st

# ── Page config (must be FIRST Streamlit call) ───────────────────────
st.set_page_config(
    page_title="UHA Inventory",
    page_icon="🏟️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Core service imports ──────────────────────────────────────────────
from database import InventoryDatabase
import auth

# ── SDOA registry ────────────────────────────────────────────────────
from registry import get_registry

# ── Top nav skeleton ─────────────────────────────────────────────────
from ui_skeleton import build_default_registry, FeatureRegistry, MenuBar, MenuItem

# ── Version syncer ────────────────────────────────────────────────────
from version_syncer import VersionSyncer

# ── Hidden admin tools ────────────────────────────────────────────────
# database_sheet_importer accessed via ?page=db_import (admin only)


# ────────────────────────────────────────────────────────────────────
# MULTI-DATABASE CONFIGURATION
# ────────────────────────────────────────────────────────────────────

# Cost center metadata
COST_CENTERS = {
    "57230": {
        "code":    "57230",
        "icon":    "🏢",
        "label":   "Overhead",
        "caption": "Compass Group · UHA",
        "secret_key": "DB_57230",
    },
    "57231": {
        "code":    "57231",
        "icon":    "🏟️",
        "label":   "TDECU Concessions",
        "caption": "TDECU Stadium · Houston, TX",
        "secret_key": "DB_57231",
    },
    "57232": {
        "code":    "57232",
        "icon":    "📦",
        "label":   "Warehouse",
        "caption": "Fertitta Center",
        "secret_key": "DB_57232",
    },
    "57233": {
        "code":    "57233",
        "icon":    "⚾",
        "label":   "Schroeder Park",
        "caption": "UH Baseball",
        "secret_key": "DB_57233",
    },
    "57234": {
        "code":    "57234",
        "icon":    "🥎",
        "label":   "Softball Stadium",
        "caption": "UH Softball",
        "secret_key": "DB_57234",
    },
    "57235": {
        "code":    "57235",
        "icon":    "🍽️",
        "label":   "Team Dining",
        "caption": "UH Athletics",
        "secret_key": "DB_57235",
    },
    "57236": {
        "code":    "57236",
        "icon":    "🎉",
        "label":   "Catering",
        "caption": "Special Events",
        "secret_key": "DB_57236",
    },
}


def get_available_databases() -> dict:
    """
    Return dict of cost_center_code -> db_url.
    All cost centers share one Supabase instance; cost_center column handles filtering.
    """
    try:
        db_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL", "")
    except Exception:
        db_url = os.environ.get("SUPABASE_DB_URL", "")
    if not db_url:
        return {}
    return {code: db_url for code in COST_CENTERS}


def get_default_database() -> str:
    """Return the default cost center code."""
    return "57231"


def get_current_database() -> str:
    """Get the currently selected database from session state."""
    if "selected_database" not in st.session_state:
        st.session_state["selected_database"] = get_default_database()
    return st.session_state["selected_database"]


def set_current_database(code: str) -> None:
    """Switch to a different database and clear cached resources."""
    if code != st.session_state.get("selected_database"):
        st.session_state["selected_database"] = code
        # Clear registry cache to force module reload with new DB
        try:
            get_registry.clear()
        except Exception:
            pass
        # Clear database cache
        try:
            get_db.clear()
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────────
# RESOURCE FACTORIES
# ────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_db(_db_code: str = None) -> InventoryDatabase:
    """
    Database factory — single Supabase instance, filtered by cost_center.
    Cached per cost_center code so switching cost centers creates a fresh instance.
    """
    try:
        db_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL", "")
    except Exception:
        db_url = os.environ.get("SUPABASE_DB_URL", "")
    if not db_url:
        raise RuntimeError(
            "No database configured. Add SUPABASE_DB_URL to Streamlit secrets."
        )
    return InventoryDatabase(db_url=db_url, cost_center=_db_code)


@st.cache_resource
def get_feature_registry() -> FeatureRegistry:
    """Feature toggle registry — separate from the module registry."""
    return build_default_registry()


# ────────────────────────────────────────────────────────────────────
# PAGE ROUTING HELPERS
# ────────────────────────────────────────────────────────────────────

def get_current_page() -> str:
    try:
        return st.query_params.get("page", "dashboard")
    except Exception:
        return "dashboard"


def set_page(key: str) -> None:
    try:
        st.query_params["page"] = key
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────
# TOP NAV BAR
# ────────────────────────────────────────────────────────────────────

_NAV_CSS = """
<style>
#uha-topnav-root {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1000000;
}

/* Push sidebar below the nav bar */
section[data-testid="stSidebar"] {
    top: 46px !important;
    height: calc(100vh - 46px) !important;
    z-index: 999 !important;
}
/* Sidebar collapse/expand toggle button */
button[data-testid="collapsedControl"] {
    top: 56px !important;
}
.uha-nav {
    display: flex;
    flex-direction: row;
    align-items: stretch;
    background: #1a1a2e;
    padding: 0 4px;
    margin: 0;
}
.uha-nav-title {
    color: #e63946;
    font-weight: 700;
    font-size: 13px;
    padding: 10px 16px 10px 8px;
    letter-spacing: 0.5px;
    white-space: nowrap;
    align-self: center;
    border-right: 1px solid #2d3748;
    margin-right: 4px;
}
.uha-nav-menu { position: relative; display: inline-block; }
.uha-nav-btn {
    display: inline-block;
    color: #adb5bd;
    padding: 10px 14px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    text-decoration: none;
    border-radius: 4px;
    white-space: nowrap;
    transition: background 0.12s, color 0.12s;
}
.uha-nav-menu:hover > .uha-nav-btn { background: #16213e; color: #ffffff; }
.uha-nav-dropdown {
    display: none;
    position: absolute;
    top: 100%;
    left: 0;
    background: #16213e;
    min-width: 235px;
    z-index: 99999;
    border-radius: 0 4px 4px 4px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.55);
    border: 1px solid #0f3460;
    padding: 4px 0;
}
.uha-nav-menu:hover .uha-nav-dropdown { display: block; }
.uha-nav-item {
    display: block;
    padding: 7px 16px;
    color: #adb5bd;
    text-decoration: none !important;
    font-size: 12.5px;
    white-space: nowrap;
    transition: background 0.1s, color 0.1s;
}
.uha-nav-item:hover { background: #0f3460; color: #ffffff; text-decoration: none !important; }
.uha-nav-item.uha-active { color: #e63946; font-weight: 600; }
.uha-nav-sep { border: none; border-top: 1px solid #2d3748; margin: 4px 8px; }
</style>
"""


def render_top_nav(feat_registry: FeatureRegistry) -> None:
    """HTML/CSS dropdown fixed to absolute top of browser via MutationObserver."""
    menu_bar = MenuBar(feat_registry)
    cur_page = get_current_page()
    cur_db   = get_current_database()

    def item_html(item: MenuItem) -> str:
        if item.separator:
            return '<hr class="uha-nav-sep"/>'
        if not menu_bar.is_item_enabled(item):
            return ""
        lbl = item.full_label
        if item.page_key:
            active = " uha-active" if cur_page == item.page_key else ""
            return f'<a class="uha-nav-item{active}" href="?page={item.page_key}">{lbl}</a>'
        if item.db_key:
            # Cost center switcher — plain ?db= URL, handled by ?db= param handler
            active = " uha-active" if item.db_key == cur_db else ""
            return f'<a class="uha-nav-item{active}" href="?db={item.db_key}">{lbl}</a>'
        if item.js_action:
            # Browser-native actions (window.open, print, share, etc.)
            # Safe because nav is injected into parent DOM, so onclick runs in page context
            safe = item.js_action.replace('"', "&quot;")
            return f'<a class="uha-nav-item" href="#" onclick="{safe}; return false;">{lbl}</a>'
        return ""

    # Skip menus whose entire dropdown is empty
    _sep = '<hr class="uha-nav-sep"/>'
    menu_parts = []
    for m in menu_bar.menus:
        children_html = "".join(item_html(c) for c in m.children)
        if not children_html.replace(_sep, "").strip():
            continue
        menu_parts.append(
            f'<div class="uha-nav-menu">'
            f'<span class="uha-nav-btn">{m.label}</span>'
            f'<div class="uha-nav-dropdown">{children_html}</div>'
            f'</div>'
        )
    menus_html = "".join(menu_parts)

    nav_inner = (
        f'<div class="uha-nav">'
        f'<span class="uha-nav-title">🏟️ UHA IMS</span>'
        f'{menus_html}'
        f'</div>'
    )

    # Extract raw CSS text from the _NAV_CSS <style> block
    _css_text = _NAV_CSS.replace("<style>", "").replace("</style>", "").strip()

    # Escape backticks and template-literal markers for JS template string
    _css_js  = _css_text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    _nav_js  = nav_inner.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    # Inject nav + CSS directly into parent document body via components iframe.
    # st.components.v1.html() runs in a same-origin iframe; window.parent gives
    # access to the real page DOM, so position:fixed pins to the actual viewport.
    import streamlit.components.v1 as _cv1
    _cv1.html(f"""
<script>
(function() {{
  try {{
    var pd = window.parent.document;

    // Inject CSS into <head>
    var s = pd.getElementById('uha-nav-css');
    if (!s) {{ s = pd.createElement('style'); s.id = 'uha-nav-css'; pd.head.appendChild(s); }}
    s.textContent = `{_css_js}`;

    // Inject nav div into <body>
    var n = pd.getElementById('uha-topnav-root');
    if (!n) {{ n = pd.createElement('div'); n.id = 'uha-topnav-root'; pd.body.appendChild(n); }}
    n.innerHTML = `{_nav_js}`;

    // Hide Streamlit's built-in header so it doesn't overlap
    var hdr = pd.querySelector('header[data-testid="stHeader"]');
    if (hdr) hdr.style.display = 'none';
  }} catch(e) {{ console.warn('UHA nav inject failed:', e); }}
}})();
</script>
""", height=1, scrolling=False)

    # Spacer so page content doesn't hide under the fixed bar
    st.markdown('<div style="height:46px"></div>', unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────
# SIDEBAR
# ────────────────────────────────────────────────────────────────────

def render_sidebar(db, registry, feat_registry: FeatureRegistry,
                   syncer: VersionSyncer) -> None:
    with st.sidebar:
        # ── Cost Center branding (based on current database) ─────────
        current_db = get_current_database()
        cc_meta = COST_CENTERS.get(current_db, COST_CENTERS["57231"])
        
        st.image("https://img.icons8.com/emoji/96/stadium.png", width=52)
        st.markdown(f"**{cc_meta['label']}**")
        st.caption(cc_meta['caption'])
        st.markdown("---")

        # ── Database Switcher ─────────────────────────────────────────
        available = get_available_databases()
        if len(available) > 1:
            db_options = {code: f"{COST_CENTERS[code]['icon']} {COST_CENTERS[code]['label']}"
                          for code in sorted(available.keys())}
            chosen_db = st.selectbox(
                "Cost Center",
                options=list(db_options.keys()),
                format_func=lambda x: db_options[x],
                index=list(db_options.keys()).index(current_db)
                      if current_db in db_options else 0,
                key="db_selector",
            )
            if chosen_db != current_db:
                set_current_database(chosen_db)
                st.rerun()
            st.markdown("---")

        # ── Module nav (from registry) ────────────────────────────────
        cur = get_current_page()
        items = registry.sidebar_items()

        # Supplement with fallback pages if modules don't cover them
        fallback_items = []
        registered_keys = {i["page_key"] for i in items}
        for pk, lbl, icon in [
            ("gl_codes", "GL Codes",  "🏷️"),
            ("history",  "History",   "📜"),
            ("export",   "Export",    "📤"),
            ("settings", "Settings",  "⚙️"),
        ]:
            if pk not in registered_keys:
                fallback_items.append({
                    "page_key": pk, "label": lbl, "icon": icon, "position": 200,
                })

        all_nav = items + fallback_items
        nav_keys   = [i["page_key"] for i in all_nav]
        nav_labels = {i["page_key"]: f"{i['icon']} {i['label']}" for i in all_nav}

        idx = nav_keys.index(cur) if cur in nav_keys else 0
        chosen = st.radio(
            "Navigate",
            options=nav_keys,
            format_func=lambda k: nav_labels.get(k, k),
            index=idx,
            key="sidebar_nav_radio",
        )
        if chosen != cur:
            set_page(chosen)
            st.rerun()

        st.markdown("---")

        # ── Registry diagnostics (admin) ──────────────────────────────
        if auth.is_admin() and registry.has_errors():
            with st.expander(f"⚠️ {len(registry.errors())} Registry Error(s)", expanded=True):
                for err in registry.errors():
                    st.caption(f"• {err}")

        # ── Version syncer badge ──────────────────────────────────────
        with st.expander("🔀 Version Sync", expanded=False):
            records = syncer.check()
            out_of_sync = [r for r in records if not r.in_sync
                           and r.live != "?" and r.repo != "?"]
            if out_of_sync:
                st.warning(f"{len(out_of_sync)} component(s) out of sync")
                if st.button("🔄 Hot Reload", key="syncer_hot_reload_sb",
                             use_container_width=True):
                    VersionSyncer.hot_reload()
            else:
                st.caption("✅ All in sync")
                if st.button("🔄 Force Reload", key="syncer_force_sb",
                             use_container_width=True):
                    VersionSyncer.hot_reload()
            if st.button("↻ Recheck", key="syncer_recheck_sb",
                         use_container_width=True):
                syncer.clear_cache()
                st.rerun()

        # ── Admin: feature toggles ────────────────────────────────────
        if auth.is_admin():
            with st.expander("⚙️ Feature Toggles (Admin)", expanded=False):
                for feat in feat_registry.all_features():
                    new_val = st.checkbox(
                        feat.description or feat.name,
                        value=feat.option_available,
                        key=f"feat_sb_{feat.name}",
                    )
                    if new_val != feat.option_available:
                        feat_registry.set(feat.name, new_val)
                        st.rerun()

        # ── Version panel ─────────────────────────────────────────────
        _render_version_panel(registry)

        st.markdown("---")

        # ── Dev Tools (localhost only) ────────────────────────────────
        _render_dev_tools()

        # ── User badge (moved to bottom) ──────────────────────────────
        auth.render_user_badge()


def _render_dev_tools() -> None:
    """Push-to-GitHub button — only rendered when running on localhost."""
    import socket
    try:
        host = socket.gethostname()
        is_local = host in ("localhost", "127.0.0.1") or not host.startswith("ip-")
    except Exception:
        is_local = False
    if not is_local:
        return

    with st.expander("🛠 Dev Tools", expanded=False):
        commit_msg = st.text_input(
            "Commit message",
            placeholder="leave blank for auto-timestamp",
            key="dev_commit_msg",
            label_visibility="collapsed",
        )
        if st.button("🚀 Push to GitHub", use_container_width=True, key="dev_push_btn"):
            import subprocess, os
            repo = os.path.dirname(os.path.abspath(__file__))
            msg  = commit_msg.strip() or f"Update {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}"

            with st.spinner("Pushing…"):
                add   = subprocess.run(["git", "-C", repo, "add", "."],
                                       capture_output=True, text=True)
                diff  = subprocess.run(["git", "-C", repo, "diff", "--cached", "--quiet"],
                                       capture_output=True)
                if diff.returncode == 0:
                    st.info("Nothing to commit — working tree is clean.")
                else:
                    commit = subprocess.run(
                        ["git", "-C", repo, "commit", "-m", msg],
                        capture_output=True, text=True,
                    )
                    push = subprocess.run(
                        ["git", "-C", repo, "push", "origin", "main"],
                        capture_output=True, text=True,
                    )
                    if push.returncode == 0:
                        st.success(f"✓ Pushed: {msg}")
                    else:
                        st.error("Push failed")
                        st.code(push.stderr or commit.stderr)


def _render_version_panel(registry) -> None:
    """Module version table pulled from registry + service manifests."""
    rows = [("app", __version__)]

    for mod_name, import_path in [
        ("base",          "base"),
        ("registry",      "registry"),
        ("database",      "database"),
        ("importer",      "importer"),
        ("auth",          "auth"),
        ("ui_skeleton",   "ui_skeleton"),
        ("version_syncer","version_syncer"),
        ("count_importer","count_importer"),
        ("pca_engine",    "pca_engine"),
        ("gl_manager",    "gl_manager"),
    ]:
        try:
            mod = importlib.import_module(import_path)
            ver = getattr(mod, "__version__", None)
            if ver is None:
                # Try SERVICE_MANIFEST
                for cls_name in dir(mod):
                    cls = getattr(mod, cls_name)
                    if isinstance(cls, type):
                        sm = getattr(cls, "SERVICE_MANIFEST", {})
                        ver = sm.get("version")
                        if ver:
                            break
            rows.append((mod_name, ver or "—"))
        except Exception:
            rows.append((mod_name, "n/a"))

    # Add SDOA modules from registry
    for m in registry.all():
        rows.append((m.id, m.version))

    with st.sidebar.expander("📦 Module Versions", expanded=False):
        for name, ver in rows:
            st.caption(f"`{name}` — v{ver}")


# ────────────────────────────────────────────────────────────────────
# SETTINGS PAGE  (admin only)
# ────────────────────────────────────────────────────────────────────

def _page_settings(db, feat_registry: FeatureRegistry, syncer: VersionSyncer) -> None:
    st.title("⚙️ Settings")

    if not auth.is_admin():
        st.warning("🔒 Admin access required.")
        st.info(
            "The first user to sign in is automatically granted admin. "
            "Ask your admin to promote your account via User Management."
        )
        return

    tab1, tab2, tab3 = st.tabs(
        ["🔧 Feature Toggles", "👥 User Management", "🔀 Version Sync"]
    )

    with tab1:
        st.subheader("Feature Toggles")
        st.caption("Persist while the server is running. Reset to defaults on next deploy.")
        cols = st.columns(2)
        for i, feat in enumerate(feat_registry.all_features()):
            with cols[i % 2]:
                new_val = st.toggle(
                    feat.description or feat.name,
                    value=feat.option_available,
                    key=f"settings_feat_{feat.name}",
                    help=feat.name,
                )
                if new_val != feat.option_available:
                    feat_registry.set(feat.name, new_val)
                    st.rerun()

    with tab2:
        auth.render_user_management(db)

    with tab3:
        syncer.render_panel()


# ────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────

def main() -> None:
    feat_registry = get_feature_registry()

    # ── Cost center switch from nav ?db= param ────────────────────────
    # Top nav items inject ?db=57231 into the URL via JS to switch cost
    # centers. Handle it here before auth so DB factory stays in sync.
    _db_switch = st.query_params.get("db")
    if _db_switch and _db_switch in COST_CENTERS:
        set_current_database(_db_switch)
        del st.query_params["db"]
        st.rerun()
        return

    # ── Auth gate ─────────────────────────────────────────────────────
    # Note: Auth happens before database connection
    # Use a temporary DB instance just for user table
    try:
        auth_db = get_db(_db_code=get_current_database())
        if not auth.require_auth(auth_db):
            return
    except Exception as exc:
        st.error(f"Database connection failed: {exc}")
        st.info(
            "Check that your database secrets are configured correctly. "
            "Each cost center needs a secret key (e.g., DB_57231)."
        )
        return

    # ── Get current database ──────────────────────────────────────────
    current_db_code = get_current_database()
    db = get_db(_db_code=current_db_code)

    # ── SDOA registry (discovers modules/ on first call) ──────────────
    registry = get_registry(_db=db)

    # ── Version syncer ────────────────────────────────────────────────
    syncer = VersionSyncer(registry=registry, repo="trechurch/UHAIMS")

    # ── Top nav ───────────────────────────────────────────────────────
    render_top_nav(feat_registry)

    # ── Sidebar ───────────────────────────────────────────────────────
    render_sidebar(db, registry, feat_registry, syncer)

    # ── Page dispatch ─────────────────────────────────────────────────
    page = get_current_page()

    # Registry handles all module pages
    if page in registry.page_keys():
        registry.dispatch(page)

    # Settings (app-level, not a module)
    elif page in ("settings", "settings_sidebar", "settings_prefs"):
        _page_settings(db, feat_registry, syncer)

    # Hidden admin import tool
    elif page == "db_import":
        if not auth.is_admin():
            st.warning("🔒 Admin access required for this page.")
        else:
            from database_sheet_importer import render as _render_db_import
            _render_db_import()

    else:
        st.info(
            f"Page `{page}` is not yet implemented.  \n"
            f"Registered pages: {sorted(registry.page_keys())}"
        )


if __name__ == "__main__":
    main()
