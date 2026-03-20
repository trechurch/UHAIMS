# ──────────────────────────────────────────────────────────────────────────────
#  modules/dashboard_module.py  —  Database Dashboard
#
#  GOLD STANDARD — this is the reference every new module copies.
#  Pattern: MANIFEST → DOCS → sidebar() → on_load() → render()
#
#  v1.0.0
# ──────────────────────────────────────────────────────────────────────────────

import pandas as pd
import streamlit as st
from datetime import datetime

from base import Dashboard

# ── end of imports ────────────────────────────────────────────────────────────


class DatabaseDashboard(Dashboard):

    # ──────────────────────────────────────────────────────────────────────────
    #  MANIFEST
    # ──────────────────────────────────────────────────────────────────────────

    MANIFEST = {
        "id":       "dashboard_module",
        "label":    "Dashboard",
        "version":  "1.0.0",
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
                st.markdown("---")
        with st.expander("🔧 Admin Tools"):
            if st.button("📋 Open Database Sheet Importer"):
                st.session_state.page_key = "db_import"
                st.rerun()

    # ── end of render ─────────────────────────────────────────────────────────

# ── end of DatabaseDashboard ──────────────────────────────────────────────────
