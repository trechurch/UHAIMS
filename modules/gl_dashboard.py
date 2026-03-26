# ──────────────────────────────────────────────────────────────────────────────
#  modules/gl_dashboard.py  —  GL Code Manager Dashboard
#  v1.0.0  —  Migrated from inventory_logic.page_gl_codes()
# ──────────────────────────────────────────────────────────────────────────────

import pandas as pd
import streamlit as st
from base import Dashboard


class GLDashboard(Dashboard):

    MANIFEST = {
        "id":       "gl_dashboard",
        "label":    "GL Codes",
        "version":  "1.0.0",
        "icon":     "🏷️",
        "status":   "active",
        "page_key": "gl_codes",
        "menu": {
            "parent":   "Tools",
            "label":    "GL Code Manager",
            "shortcut": "G",
            "position": 10,
        },
        "sidebar": {
            "section":  "Tools",
            "position": 10,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["items", "item_history"],
        "session_keys": [],
        "abilities": [
            "Load GL code lists from OneDrive (if connected)",
            "Auto-assign GL codes to unassigned items via fuzzy matching",
            "Display GL code summary table",
            "Configure minimum confidence threshold",
        ],
        "permissions": {"min_role": "editor"},
    }

    DOCS = {
        "summary": "Manage and auto-assign GL codes to inventory items.",
        "usage":   "Use Auto-Assign to fuzzy-match unassigned items. Load from OneDrive to refresh the GL list.",
        "demo_ready": True,
        "notes":   "OneDrive integration is optional — GL auto-assign works without it.",
        "known_issues": [],
        "changelog": [
            {"version": "1.0.0", "date": "2026-03-25", "note": "Migrated from inventory_logic.page_gl_codes() to SDOA module."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        self._init_gl()

    def _init_gl(self):
        if not hasattr(self, "_gl"):
            try:
                from gl_manager import GLCodeManager
                self._gl = GLCodeManager(self.db)
                self._gl_error = None
            except Exception as exc:
                self._gl = None
                self._gl_error = str(exc)

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**🏷️ GL Codes**")
            st.caption("Auto-assign · fuzzy matching")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.title("🏷️ GL Code Manager")

        self._init_gl()
        if self._gl is None:
            st.error(f"GL Manager failed to load: `{self._gl_error}`")
            return

        # Try optional OneDrive connector
        od = None
        try:
            import onedrive_connector as _od
            od = _od
        except Exception:
            pass

        col1, col2 = st.columns(2)

        with col1:
            if od and od.get_access_token():
                st.subheader("Load GL Lists from OneDrive")
                if st.button("🔄 Reload GL Lists from OneDrive"):
                    with st.spinner("Loading..."):
                        entries = od.load_gl_files_from_onedrive()
                        for gl_code, gl_name, desc in entries:
                            self._gl.add_gl_mapping(gl_code, gl_name, desc)
                    st.success(f"Loaded {len(entries):,} GL entries.")
            else:
                st.info("Connect OneDrive (via sidebar) to load GL lists automatically.")

            st.subheader("Auto-Assign GL Codes")
            confidence = st.slider("Minimum confidence", 0.5, 0.95, 0.70,
                                   key="gl_confidence")
            if st.button("🤖 Auto-Assign to Unassigned Items",
                         key="gl_auto_assign"):
                with st.spinner("Matching..."):
                    results = self._gl.assign_gl_codes_to_items(
                        min_confidence=confidence
                    )
                st.success(
                    f"Assigned: {results['assigned']} | "
                    f"Skipped: {results['skipped']} | "
                    f"Failed: {results['failed']}"
                )
                if results.get("assignments"):
                    adf = pd.DataFrame(results["assignments"])[
                        ["description", "gl_code", "gl_name", "confidence"]
                    ]
                    st.dataframe(adf, use_container_width=True, hide_index=True)

        with col2:
            st.subheader("GL Code Summary")
            try:
                summary = self._gl.get_gl_summary()
                if summary:
                    st.dataframe(pd.DataFrame(summary),
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No GL mappings loaded yet.")
            except Exception as exc:
                st.error(f"Could not load GL summary: {exc}")

# ── end of GLDashboard ────────────────────────────────────────────────────────
