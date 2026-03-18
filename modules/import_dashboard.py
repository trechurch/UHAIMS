# ──────────────────────────────────────────────────────────────────────────────
#  modules/import_dashboard.py  —  Import Dashboard
#  Vendor invoice ingestion UI — wraps InventoryImporter service
#
#  v1.0.0
# ──────────────────────────────────────────────────────────────────────────────

import os
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from base import Dashboard
from importer import InventoryImporter

# ── end of imports ────────────────────────────────────────────────────────────


class ImportDashboard(Dashboard):

    # ──────────────────────────────────────────────────────────────────────────
    #  MANIFEST
    # ──────────────────────────────────────────────────────────────────────────

    MANIFEST = {
        "id":       "import_dashboard",
        "label":    "Importer",
        "version":  "1.0.0",
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
        "permissions": {
            "min_role": "user",
        },
    }

    # ── end of MANIFEST ───────────────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  DOCS
    # ──────────────────────────────────────────────────────────────────────────

    DOCS = {
        "summary": (
            "Upload and ingest vendor invoice files (CSV/XLSX). "
            "Shows a preview of new items and updates before any DB writes."
        ),
        "usage": (
            "Navigate to Importer from the sidebar. "
            "Upload one or more invoice files. "
            "Review the preview — new items, updates, skipped rows. "
            "Click Confirm Import to write to the database."
        ),
        "demo_ready": True,
        "notes": (
            "Uses InventoryImporter service for all parsing logic. "
            "Encoding errors and duplicate-column bugs from previous version are fixed. "
            "Count sheet import is a separate module — coming soon."
        ),
        "known_issues": [
            "Count sheet import not yet wired into this dashboard.",
            "OneDrive import tab disabled pending IT approval.",
        ],
        "changelog": [
            {
                "version": "1.0.0",
                "date":    "2026-03-18",
                "note":    "Initial SDOA implementation with fixed importer service.",
            },
        ],
    }

    # ── end of DOCS ───────────────────────────────────────────────────────────


    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        self._importer = InventoryImporter(self.db)

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**📥 Importer**")
            st.caption("Vendor invoices · CSV / XLSX")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.title(f"{self.icon} Import Dashboard")
        st.caption("Vendor invoice ingestion — CSV and XLSX supported.")

        if not hasattr(self, '_importer'):
            self._importer = InventoryImporter(self.db)

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

    # ── Per-file processor ────────────────────────────────────────────────────

    def _process_file(self, f) -> None:
        st.markdown(f"---\n### 📄 {f.name}")

        try:
            content = f.read()
            suffix  = Path(f.name).suffix.lower()

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                df = self._importer.read_file(tmp_path)
            finally:
                os.unlink(tmp_path)

            if df is None:
                st.error(f"Could not read: {self._importer.errors}")
                return

            analysis = self._importer.analyze_import(df)

            # ── Metrics ───────────────────────────────────────────────────────
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Rows",  analysis["total_rows"])
            c2.metric("New Items",   len(analysis["new_items"]))
            c3.metric("Updates",     len(analysis["updates"]))
            c4.metric("Skipped/Err", len(analysis["skipped"]) + len(analysis["errors"]))

            # ── New items preview ─────────────────────────────────────────────
            if analysis["new_items"]:
                with st.expander(f"📋 {len(analysis['new_items'])} New Items"):
                    st.dataframe(
                        pd.DataFrame([
                            {"Key": i["key"], "Description": i["description"]}
                            for i in analysis["new_items"]
                        ]),
                        use_container_width=True,
                        hide_index=True,
                    )

            # ── Updates preview ───────────────────────────────────────────────
            if analysis["updates"]:
                with st.expander(f"🔄 {len(analysis['updates'])} Updates"):
                    st.dataframe(
                        pd.DataFrame([
                            {
                                "Key":            i["key"],
                                "Description":    i["description"],
                                "Fields Changed": ", ".join(i["changes"].keys()),
                            }
                            for i in analysis["updates"]
                        ]),
                        use_container_width=True,
                        hide_index=True,
                    )

            # ── Errors ────────────────────────────────────────────────────────
            if analysis["errors"]:
                with st.expander(f"⚠️ {len(analysis['errors'])} Errors"):
                    for e in analysis["errors"]:
                        st.caption(e)

            # ── Nothing to import ─────────────────────────────────────────────
            if not analysis["new_items"] and not analysis["updates"]:
                st.warning("Nothing to import from this file.")
                return

            # ── Confirm button ────────────────────────────────────────────────
            if st.button(
                f"✅ Confirm Import — {f.name}",
                key=f"confirm_{f.name}",
                type="primary",
            ):
                with st.spinner("Writing to database…"):
                    results = self._importer.execute_import(
                        analysis,
                        changed_by="web_import",
                        source_document=f.name,
                        doc_date=datetime.now().strftime("%Y-%m-%d"),
                    )

                st.success(
                    f"✅ Done — "
                    f"**{results['new_items_added']}** added, "
                    f"**{results['items_updated']}** updated."
                )
                if results.get("errors"):
                    with st.expander(f"⚠️ {len(results['errors'])} write error(s)"):
                        for e in results["errors"]:
                            st.caption(e)

        except Exception as exc:
            st.error(f"Error processing {f.name}: {exc}")

    # ── end of render ─────────────────────────────────────────────────────────

# ── end of ImportDashboard ────────────────────────────────────────────────────
