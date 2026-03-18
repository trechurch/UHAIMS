# ──────────────────────────────────────────────────────────────────────────────
#  modules/import_dashboard.py  —  Import Dashboard
#  v1.0.3  —  Extra diagnostic caption after DB load to isolate hang location.
# ──────────────────────────────────────────────────────────────────────────────

import os
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from base import Dashboard


class ImportDashboard(Dashboard):

    MANIFEST = {
        "id":       "import_dashboard",
        "label":    "Importer",
        "version":  "1.0.3",
        "icon":     "📥",
        "status":   "active",
        "page_key": "import",
        "menu": {
            "parent":   "Dashboards",
            "label":    "Import Dashboard",
            "shortcut": "M",
            "position": 40,
        },
        "sidebar": {
            "section":  "",
            "position": 40,
            "show":     True,
        },
        "depends_on":   ["database", "importer"],
        "db_tables":    ["items", "item_history", "price_history"],
        "session_keys": ["pending_files", "last_analysis"],
        "abilities": [
            "Upload vendor invoice CSV or XLSX",
            "Auto-detect CSV encoding via chardet",
            "Auto-detect Excel header row",
            "Preview new items and updates before committing",
            "Execute import with full field-level history tracking",
        ],
        "permissions": {"min_role": "user"},
    }

    DOCS = {
        "summary": "Upload and ingest vendor invoice files (CSV/XLSX).",
        "usage":   "Upload files, review preview, click Confirm Import.",
        "demo_ready": True,
        "notes":   "v1.0.3 adds diagnostic caption after DB load step.",
        "known_issues": ["Count sheet import not yet wired."],
        "changelog": [
            {"version": "1.0.3", "date": "2026-03-18", "note": "Extra diagnostic caption after DB load."},
            {"version": "1.0.2", "date": "2026-03-18", "note": "Explicit error surfacing."},
            {"version": "1.0.1", "date": "2026-03-18", "note": "Lazy import."},
            {"version": "1.0.0", "date": "2026-03-18", "note": "Initial implementation."},
        ],
    }

    def on_load(self) -> None:
        self._init_importer()

    def _init_importer(self):
        if not hasattr(self, '_importer'):
            try:
                from importer import InventoryImporter
                self._importer = InventoryImporter(self.db)
                self._importer_error = None
            except Exception as exc:
                self._importer = None
                self._importer_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**📥 Importer**")
            st.caption("Vendor invoices · CSV / XLSX")

    def render(self) -> None:
        st.title(f"{self.icon} Import Dashboard")
        st.caption("Vendor invoice ingestion — CSV and XLSX supported.")
        self._init_importer()
        if self._importer is None:
            st.error(f"**Importer failed to load:**\n```\n{self._importer_error}\n```")
            return
        uploaded = st.file_uploader(
            "Drop vendor invoice files here",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if not uploaded:
            st.info("Upload one or more invoice files to begin.")
            return
        for f in uploaded:
            self._process_file(f)

    def _process_file(self, f) -> None:
        st.markdown(f"---\n### 📄 {f.name}")

        # Step 1
        try:
            content = f.read()
            st.caption(f"✓ Read {len(content):,} bytes")
        except Exception as exc:
            st.error(f"**Step 1 failed:** {exc}")
            return

        # Step 2
        tmp_path = None
        try:
            suffix = Path(f.name).suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            st.caption("✓ Temp file written")
        except Exception as exc:
            st.error(f"**Step 2 failed:** {exc}")
            return

        # Step 3
        df = None
        try:
            df = self._importer.read_file(tmp_path)
            if df is None:
                st.error(f"**Step 3 failed (None):** {self._importer.errors}")
                return
            st.caption(f"✓ Parsed {len(df)} rows · cols: {list(df.columns[:8])}")
        except Exception as exc:
            st.error(f"**Step 3 failed:** {exc}")
            st.code(traceback.format_exc())
            return
        finally:
            if tmp_path:
                try: os.unlink(tmp_path)
                except Exception: pass

        # Step 4a — DB load (isolated)
        try:
            existing = self._importer._load_all_items()
            st.caption(f"✓ DB loaded — {len(existing)} existing items in memory")
        except Exception as exc:
            st.error(f"**Step 4a failed (DB load):** {exc}")
            st.code(traceback.format_exc())
            return

        # Step 4b — analyze
        try:
            analysis = self._importer.analyze_import_with_cache(df, existing)
            st.caption(f"✓ Analysis complete")
        except Exception as exc:
            st.error(f"**Step 4b failed (analyze):** {exc}")
            st.code(traceback.format_exc())
            return

        # Metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Rows",  analysis["total_rows"])
        c2.metric("New Items",   len(analysis["new_items"]))
        c3.metric("Updates",     len(analysis["updates"]))
        c4.metric("Skipped/Err", len(analysis["skipped"]) + len(analysis["errors"]))

        if analysis["new_items"]:
            with st.expander(f"📋 {len(analysis['new_items'])} New Items"):
                st.dataframe(pd.DataFrame([{"Key": i["key"], "Description": i["description"]} for i in analysis["new_items"]]), use_container_width=True, hide_index=True)

        if analysis["updates"]:
            with st.expander(f"🔄 {len(analysis['updates'])} Updates"):
                st.dataframe(pd.DataFrame([{"Key": i["key"], "Description": i["description"], "Fields Changed": ", ".join(i["changes"].keys())} for i in analysis["updates"]]), use_container_width=True, hide_index=True)

        if analysis["errors"]:
            with st.expander(f"⚠️ {len(analysis['errors'])} Row Errors"):
                for e in analysis["errors"]: st.caption(e)

        if not analysis["new_items"] and not analysis["updates"]:
            st.warning("Nothing to import from this file.")
            return

        if st.button(f"✅ Confirm Import — {f.name}", key=f"confirm_{f.name}", type="primary"):
            try:
                with st.spinner("Writing to database…"):
                    results = self._importer.execute_import(analysis, changed_by="web_import", source_document=f.name, doc_date=datetime.now().strftime("%Y-%m-%d"))
                st.success(f"✅ Done — **{results['new_items_added']}** added, **{results['items_updated']}** updated.")
                if results.get("errors"):
                    with st.expander(f"⚠️ {len(results['errors'])} write error(s)"):
                        for e in results["errors"]: st.caption(e)
            except Exception as exc:
                st.error(f"**Commit failed:** {exc}")
                st.code(traceback.format_exc())
