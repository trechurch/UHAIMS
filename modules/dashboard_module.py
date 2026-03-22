# ==================== UHA TOP NAV FIX v1.0 - FULL REPLACEMENT BLOCK ====================
# Paste this at the VERY TOP of the render() method in dashboard_module.py
# Deletes old buried nav, adds fixed viewport-top bar from handoff spec.
# Commit message: "Fix top nav: fixed position, spec colors, dual toggles"

import streamlit as st

# 1. Hide Streamlit header + inject fixed top nav styling
st.markdown('''
# ==================== UHA TOP NAV FORCE-VISIBLE DEBUG v1.1 - FULL REPLACEMENT ====================
# Paste at TOP of render() — replaces previous nav code.
# No toggle, always on; red border for visibility. Test this, then we add toggle back.

import streamlit as st

st.markdown('''
<style> {display: none !important;}
    #uha-topnav {
        position: fixed; top: 0; left: 0; width: 100%; z-index: 999999;
        background: #001f3f; color: white; padding: 12px 20px;  /* Navy bg, brighter */
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        display: flex; align-items: center; font-size: 16px; font-weight: 600;
        border-bottom: 3px solid red;  /* DEBUG: red line to spot it */
    }
    .nav-menu {
        margin-left: 32px; cursor: pointer; padding: 6px 14px; border-radius: 6px;
    }
    .nav-menu:hover {
        background: #CCE0F5; color: #0066CC;
    }
    .main .block-container, .sidebar .block-container {
        padding-top: 80px !important;  /* Extra space for taller bar */
    }
</style>
''', unsafe_allow_html=True)

# Force visible for debug—no session state mess
st.markdown('''
<div id="uha-topnav">
    <span
''', unsafe_allow_html=True)

# 2. Top nav toggle (sidebar + View menu)
if "topnav_visible" not in st.session_state:
    st.session_state.topnav_visible = True

show_nav = st.checkbox("☰ Top Navigation Bar", 
                       value=st.session_state.topnav_visible, 
                       key="nav_toggle")
if show_nav != st.session_state.topnav_visible:
    st.session_state.topnav_visible = show_nav
    st.rerun()

# 3. Render fixed top bar only if toggled on
if st.session_state.topnav_visible:
    st.markdown('''
    <div id="uha-topnav">
        <span style="font-weight:600; font-size:20px; margin-right:32px;">UHA IMS</span>
        
        <!-- File Menu -->
        <span class="nav-menu" onclick="window.location='?page=dashboard'">File</span>
        
        <!-- Dashboards Menu -->
        <span class="nav-menu" onclick="window.location='?page=dashboard'">Dashboards</span>
        
        <!-- View Menu -->
        <span class="nav-menu" onclick="window.location='?page=inventory'">View</span>
        
        <!-- Help Menu -->
        <span class="nav-menu" onclick="window.location='?page=help'">Help</span>
    </div>
    ''', unsafe_allow_html=True)

# ==================== END OF UHA TOP NAV FIX - DELETE EVERYTHING ABOVE THIS LINE ====================

# (Your original render() code continues here—keep the rest unchanged)ime

from base import Dashboard

# ── end of imports ────────────────────────────────────────────────────────────


class DatabaseDashboard(Dashboard):

    # ──────────────────────────────────────────────────────────────────────────
    #  MANIFEST
    # ──────────────────────────────────────────────────────────────────────────

    MANIFEST = {
        "id":       "dashboard_module",
        "label":    "Dashboard",
        "version":  "1.2.0",
        "icon":     "🏠",
        "status":   "active",
        "page_key": "dashboard",

        "menu": {
            "parent":   "Dashboards",
            "label":    "Database Dashboard",
            "shortcut": "D",
            "position": 10,
        },

        "sidebar": {
            "section":  "",
            "position": 10,
            "show":     True,
        },

        "depends_on":   ["database"],
        "db_tables":    ["items", "inventory_transactions"],
        "session_keys": [],
        "abilities": [
            "Display total item count",
            "Display total inventory value",
            "Display low-stock item list",
            "Display recently updated items",
        ],
        "permissions": {
            "min_role": "any",
        },
    }

    # ── end of MANIFEST ───────────────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  DOCS
    # ──────────────────────────────────────────────────────────────────────────

    DOCS = {
        "summary": (
            "Top-level operational dashboard showing key inventory metrics, "
            "low-stock alerts, and recently updated items."
        ),
        "usage": (
            "Navigate here from the sidebar or Dashboards menu. "
            "All data loads automatically — no user input required."
        ),
        "demo_ready": True,
        "notes": (
            "Metrics pull live from Supabase on every render. "
            "Low-stock threshold uses each item's reorder_point field. "
            "Recently Updated list is capped at 15 rows."
        ),
        "known_issues": [
            "Last Updated metric shows today's date rather than the actual last DB write timestamp.",
        ],
        "changelog": [
            {
                "version": "1.0.1",
                "date":    "2026-03-19",
                "note":    "Added Admin Tools expander with DB importer button.",
            },
            {
                "version": "1.0.0",
                "date":    "2026-03-17",
                "note":    "Initial implementation under SDOA architecture.",
            },
        ],
    }

    # ── end of DOCS ───────────────────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  SIDEBAR
    # ──────────────────────────────────────────────────────────────────────────

    def sidebar(self) -> None:
        """No module-specific sidebar controls for the dashboard."""

    # ── end of sidebar ────────────────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  RENDER
    # ──────────────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.title(f"{self.icon} UHA Inventory — Dashboard")

        # ── Metrics ───────────────────────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        try:
            c1.metric("Total Items",  self.db.count_items("active"))
            c2.metric("Total Value",  f"${self.db.get_inventory_value():,.2f}")
            c3.metric("Low Stock",    len(self.db.get_low_stock_items()))
        except Exception as exc:
            st.error(f"Error loading metrics: {exc}")
        c4.metric("As of", datetime.now().strftime("%m/%d/%Y %H:%M"))

        st.markdown("---")
        col1, col2 = st.columns(2)

        # ── Low stock ─────────────────────────────────────────────────────────
        with col1:
            st.subheader("🔴 Low Stock Items")
            try:
                low = self.db.get_low_stock_items()
                if low:
                    want = ["description", "pack_type",
                            "quantity_on_hand", "reorder_point", "vendor"]
                    cols = [c for c in want if c in low[0]]
                    st.dataframe(
                        pd.DataFrame(low)[cols],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.success("All items are stocked above reorder points.")
            except Exception as exc:
                st.warning(f"Could not load low-stock items: {exc}")

        # ── Recently updated ──────────────────────────────────────────────────
        with col2:
            st.subheader("📋 Recently Updated")
            try:
                items = self.db.get_all_items()
                if items:
                    df = pd.DataFrame(items)
                    if "last_updated" in df.columns:
                        df = df.sort_values("last_updated", ascending=False).head(15)
                    want = ["description", "pack_type", "cost",
                            "vendor", "last_updated", "status_tag"]
                    disp = [c for c in want if c in df.columns]
                    st.dataframe(df[disp], use_container_width=True, hide_index=True)
                else:
                    st.info("No inventory items found.")
            except Exception as exc:
                st.warning(f"Could not load recent items: {exc}")

        # ── Admin tools ───────────────────────────────────────────────────────
            #- st.markdown("---")
                 #- swith st.expander("🔧 Admin Tools"):
                    #- sif st.button("📋 Open Database Sheet Importer"):
                     #- sst.session_state.page_key = "db_import"
                 #- sst.rerun()    
        # ── end of Admin tools ─────────────────────────────────────────────

    # ── end of render ─────────────────────────────────────────────────────────

# ── end of DatabaseDashboard ──────────────────────────────────────────────────
