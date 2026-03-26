# ──────────────────────────────────────────────────────────────────────────────
#  modules/history_dashboard.py  —  Change History Dashboard
#  v1.0.0  —  Migrated from inventory_logic.page_history()
# ──────────────────────────────────────────────────────────────────────────────

import pandas as pd
import streamlit as st
from base import Dashboard


class HistoryDashboard(Dashboard):

    MANIFEST = {
        "id":       "history_dashboard",
        "label":    "History",
        "version":  "1.0.0",
        "icon":     "📜",
        "status":   "active",
        "page_key": "history",
        "menu": {
            "parent":   "Tools",
            "label":    "Change History",
            "shortcut": "H",
            "position": 20,
        },
        "sidebar": {
            "section":  "Tools",
            "position": 20,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["items", "item_history"],
        "session_keys": ["history_search"],
        "abilities": [
            "Search change history by item key or description",
            "Show field-level change log with old/new values",
            "Filter by change source, user, or date",
        ],
        "permissions": {"min_role": "any"},
    }

    DOCS = {
        "summary": "View full field-level change history for any inventory item.",
        "usage":   "Enter an item key or search term. Click a result to view its history.",
        "demo_ready": True,
        "notes":   "History is written on every import, manual edit, and override operation.",
        "known_issues": [],
        "changelog": [
            {"version": "1.0.0", "date": "2026-03-25", "note": "Migrated from inventory_logic.page_history() to SDOA module."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        pass

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**📜 History**")
            st.caption("Field-level change log")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.title("📜 Change History")

        key_input = st.text_input(
            "Enter item key or search term",
            value=self.state("search") or "",
            key="history_search_input",
        )

        if not key_input:
            st.info("Type an item key (e.g. `HOT DOG 8/1||CASE`) or any search term.")
            return

        self.set_state("search", key_input)

        history = self.db.get_item_history(key_input)

        if not history:
            # Try fuzzy search — find matching items first
            items = self.db.search_items(key_input)
            if items:
                keys = [i["key"] for i in items]
                selected = st.selectbox(
                    f"No exact match — select from {len(keys)} results:",
                    keys,
                    format_func=lambda k: k.split("||")[0],
                    key="history_selectbox",
                )
                history = self.db.get_item_history(selected)

        if history:
            df   = pd.DataFrame(history)
            cols = [
                c for c in [
                    "change_date", "change_type", "field_changed",
                    "old_value", "new_value", "change_source",
                    "changed_by", "source_document",
                ]
                if c in df.columns
            ]
            st.caption(f"{len(df)} history records")
            st.dataframe(df[cols], use_container_width=True, hide_index=True)
        else:
            st.info("No history found.")

# ── end of HistoryDashboard ───────────────────────────────────────────────────
