# ──────────────────────────────────────────────────────────────────────────────
#  modules/count_dashboard.py  —  Count Sheet Import Dashboard
#  Wraps count_importer.py (v5.0.0) — all parsing logic lives there.
#  v1.0.0
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
from base import Dashboard

class CountDashboard(Dashboard):

    MANIFEST = {
        "id":       "count_dashboard",
        "label":    "Count Import",
        "version":  "1.0.0",
        "icon":     "📋",
        "status":   "active",
        "page_key": "count",
        "menu": {
            "parent":   "Dashboards",
            "label":    "Count Sheet Import",
            "shortcut": "C",
            "position": 50,
        },
        "sidebar": {
            "section":  "",
            "position": 50,
            "show":     True,
        },
        "depends_on":   ["database", "count_importer"],
        "db_tables":    ["items", "item_history", "import_jobs"],
        "session_keys": ["count_job_id"],
        "abilities": [
            "Auto-detect count sheet format (FMT_A/B/C/D)",
            "Parse concessions and catering count sheets",
            "Match items to existing DB records",
            "Commit count quantities to inventory",
            "Track import as background job",
        ],
        "permissions": {"min_role": "user"},
    }

    DOCS = {
        "summary": "Import MyOrders count sheets for concessions and catering cost centers.",
        "usage": (
            "Navigate to Count Import. Upload one or more count sheet files. "
            "System auto-detects format. Review parsed items and commit."
        ),
        "demo_ready": True,
        "notes": (
            "Wraps count_importer.py v5.0.0 which supports FMT_A (concessions), "
            "FMT_B/C/D (catering). Format auto-detected with confidence scoring."
        ),
        "known_issues": [
            "FMT_D slash-delimited: one known discrepancy on 20oz Dasani Bottled Water.",
            "PDF count sheets (FMT_E) require OCR — not yet supported.",
        ],
        "changelog": [
            {"version": "1.0.0", "date": "2026-03-18", "note": "Initial SDOA module wrapper."},
        ],
    }

    def on_load(self) -> None:
        self._load_engine()

    def _load_engine(self):
        if not hasattr(self, '_engine_error'):
            try:
                from count_importer import CountImporter
                self._count_importer = CountImporter()
                self._engine_error = None
            except Exception as exc:
                self._count_importer = None
                self._engine_error = str(exc)

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**📋 Count Import**")
            st.caption("MyOrders count sheets · CSV / XLSX")

    def render(self) -> None:
        self._load_engine()

        if self._engine_error:
            st.error(f"Count importer failed to load: `{self._engine_error}`")
            return

        # Delegate to the existing render function in count_importer.py
        try:
            from count_importer import render_count_import_page
            render_count_import_page(
                db=self.db,
                get_changed_by_fn=lambda: "web_user",
            )
        except Exception as exc:
            import traceback
            st.error(f"Count import render error: {exc}")
            st.code(traceback.format_exc())

# ── end of CountDashboard ─────────────────────────────────────────────────────
