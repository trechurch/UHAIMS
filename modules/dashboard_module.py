# ──────────────────────────────────────────────────────────────────────────────
#  modules/dashboard_module.py  —  Main Dashboard (SDOA gold-standard module)
#  v1.1.0  —  Rebuilt from SDOA reference. Was accidentally overwritten with
#              a sidebar nav snippet.
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
from base import Dashboard


class DatabaseDashboard(Dashboard):

    MANIFEST = {
        "id":       "dashboard_module",
        "label":    "Dashboard",
        "version":  "1.2.0",
        "icon":     "🏠",
        "status":   "active",
        "page_key": "dashboard",
        "menu": {
            "parent":   "Dashboards",
            "label":    "Dashboard",
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
            "Display total active item count",
            "Display total inventory value",
            "Display low-stock item list",
            "Display recently updated items",
        ],
        "permissions": {"min_role": "any"},
    }

    DOCS = {
        "summary": "Top-level dashboard showing key inventory metrics and activity.",
        "usage":   "Navigate here from sidebar or menu. Data loads automatically on every visit.",
        "demo_ready": True,
        "notes":   "Metrics pull live from Supabase on every render. v1.1.0 rebuilt after accidental overwrite.",
        "known_issues": [],
        "changelog": [
            {"version": "1.2.0", "date": "2026-03-25", "note": "Last Updated metric now reads MAX(last_updated) from DB instead of today's date."},
            {"version": "1.1.0", "date": "2026-03-23", "note": "Rebuilt — was accidentally overwritten with sidebar nav snippet."},
            {"version": "1.0.0", "date": "2026-03-17", "note": "Initial implementation under SDOA architecture."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        pass  # No expensive one-time setup needed

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**🏠 Dashboard**")
            st.caption("UHA TDECU Stadium · Compass Group")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.title("🏟️ UHA Inventory — Dashboard")

        # ── Top metrics ───────────────────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        try:
            c1.metric("Total Items",  self.db.count_items("active"))
        except Exception:
            c1.metric("Total Items",  "—")
        try:
            c2.metric("Total Value",  f"${self.db.get_inventory_value():,.2f}")
        except Exception:
            c2.metric("Total Value",  "—")
        try:
            low = self.db.get_low_stock_items()
            c3.metric("Low Stock", len(low))
        except Exception:
            low = []
            c3.metric("Low Stock", "—")
        try:
            last_ts = self.db.get_last_updated()
            c4.metric("Last Updated", last_ts.strftime("%m/%d/%Y") if last_ts else "—")
        except Exception:
            c4.metric("Last Updated", "—")

        st.markdown("---")

        col1, col2 = st.columns(2)

        # ── Low stock ─────────────────────────────────────────────────────────
        with col1:
            st.subheader("🔴 Low Stock Items")
            if low:
                display_cols = [
                    c for c in
                    ["description", "pack_type", "quantity_on_hand", "reorder_point", "vendor"]
                    if c in pd.DataFrame(low).columns
                ]
                st.dataframe(
                    pd.DataFrame(low)[display_cols],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.success("All items are stocked above reorder points.")

        # ── Recently updated ──────────────────────────────────────────────────
        with col2:
            st.subheader("📋 Recently Updated")
            try:
                items = self.db.get_all_items()
                if items:
                    df = pd.DataFrame(items)
                    if "last_updated" in df.columns:
                        df = df.sort_values("last_updated", ascending=False).head(15)
                    show_cols = [
                        c for c in
                        ["description", "pack_type", "cost", "vendor", "last_updated", "status_tag"]
                        if c in df.columns
                    ]
                    st.dataframe(df[show_cols], use_container_width=True, hide_index=True)
                else:
                    st.info("No items in database yet.")
            except Exception as exc:
                st.error(f"Could not load items: {exc}")

# ── end of DatabaseDashboard ──────────────────────────────────────────────────
