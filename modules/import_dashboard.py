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
        "known_issues": ["Count sheet imports are handled by the dedicated Count Import dashboard (?page=count)."],
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

    # ── File type detection ───────────────────────────────────────────────────

    @staticmethod
    def _detect_file_type(filename: str, content: bytes) -> str:
        """
        Returns 'count_sheet' or 'vendor_invoice'.
        Sniffs the first few rows for count-sheet column signatures.
        """
        name_lower = filename.lower()

        # Name-based hints
        if any(k in name_lower for k in ("count", "myorders", "physical", "sheet")):
            return "count_sheet"
        if any(k in name_lower for k in ("invoice", "order", "price", "vendor")):
            return "vendor_invoice"

        # Content sniff — try to read column headers
        try:
            import io
            suffix = Path(filename).suffix.lower()
            if suffix in (".xlsx", ".xls"):
                df_sniff = pd.read_excel(io.BytesIO(content), nrows=5)
            else:
                import chardet
                enc = chardet.detect(content)["encoding"] or "utf-8"
                df_sniff = pd.read_csv(io.BytesIO(content), encoding=enc, nrows=5)

            cols = " ".join(str(c).lower() for c in df_sniff.columns)
            count_signals  = sum(1 for k in ("count", "qty", "quantity", "on hand",
                                              "physical", "par") if k in cols)
            invoice_signals = sum(1 for k in ("price", "cost", "invoice", "unit",
                                               "pack size", "uom", "total") if k in cols)
            if count_signals > invoice_signals:
                return "count_sheet"
        except Exception:
            pass

        return "vendor_invoice"

    def render(self) -> None:
        st.title(f"{self.icon} Import")
        st.caption("Drop any file — vendor invoice or count sheet — auto-detected.")
        self._init_importer()

        uploaded = st.file_uploader(
            "Drop files here (CSV, XLSX)",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if not uploaded:
            st.info("Upload vendor invoice or count sheet files to begin.")
            return

        for f in uploaded:
            content = f.read()
            file_type = self._detect_file_type(f.name, content)
            st.markdown(f"---\n### 📄 {f.name}  "
                        f"<span style='font-size:12px;color:#64748b'>"
                        f"detected: **{file_type.replace('_',' ')}**</span>",
                        unsafe_allow_html=True)

            if file_type == "count_sheet":
                self._process_count_sheet(f.name, content)
            else:
                if self._importer is None:
                    st.error(f"**Importer failed to load:**\n```\n{self._importer_error}\n```")
                else:
                    self._process_file_from_content(f.name, content)

    def _process_count_sheet(self, filename: str, content: bytes) -> None:
        """Route count sheet files to the count_importer engine."""
        try:
            from count_importer import CountImporter, render_count_import_page
            ci = CountImporter()
            st.info(
                "Count sheet detected. Opening in Count Import mode.  \n"
                "To enter counts manually, use **Count Entry** from the sidebar."
            )
            render_count_import_page(db=self.db, get_changed_by_fn=lambda: "web_import")
        except Exception as exc:
            st.error(f"Count sheet processing failed: {exc}")
            st.code(traceback.format_exc())

    def _process_file_from_content(self, filename: str, content: bytes) -> None:
        st.caption(f"✓ Read {len(content):,} bytes")

        tmp_path = None
        try:
            suffix = Path(filename).suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            st.caption("✓ Temp file written")
        except Exception as exc:
            st.error(f"Temp file failed: {exc}")
            return

        df = None
        try:
            df = self._importer.read_file(tmp_path)
            if df is None:
                st.error(f"Parse failed: {self._importer.errors}")
                return
            st.caption(f"✓ Parsed {len(df)} rows · cols: {list(df.columns[:8])}")
        except Exception as exc:
            st.error(f"Parse failed: {exc}")
            st.code(traceback.format_exc())
            return
        finally:
            if tmp_path:
                try: os.unlink(tmp_path)
                except Exception: pass

        try:
            existing = self._importer._load_all_items()
            st.caption(f"✓ DB loaded — {len(existing)} existing items")
        except Exception as exc:
            st.error(f"DB load failed: {exc}")
            st.code(traceback.format_exc())
            return

        try:
            analysis = self._importer.analyze_import_with_cache(df, existing)
            st.caption("✓ Analysis complete")
        except Exception as exc:
            st.error(f"Analysis failed: {exc}")
            st.code(traceback.format_exc())
            return

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Rows",  analysis["total_rows"])
        c2.metric("New Items",   len(analysis["new_items"]))
        c3.metric("Updates",     len(analysis["updates"]))
        c4.metric("Skipped/Err", len(analysis["skipped"]) + len(analysis["errors"]))

        if analysis["new_items"]:
            with st.expander(f"📋 {len(analysis['new_items'])} New Items"):
                st.dataframe(pd.DataFrame([{"Key": i["key"], "Description": i["description"]}
                              for i in analysis["new_items"]]),
                             use_container_width=True, hide_index=True)

        if analysis["updates"]:
            with st.expander(f"🔄 {len(analysis['updates'])} Updates"):
                st.dataframe(pd.DataFrame([{"Key": i["key"], "Description": i["description"],
                              "Fields Changed": ", ".join(i["changes"].keys())}
                              for i in analysis["updates"]]),
                             use_container_width=True, hide_index=True)

        if analysis["errors"]:
            with st.expander(f"⚠️ {len(analysis['errors'])} Row Errors"):
                for e in analysis["errors"]: st.caption(e)

        if not analysis["new_items"] and not analysis["updates"]:
            st.warning("Nothing to import from this file.")
            return

        if st.button(f"✅ Confirm Import — {filename}",
                     key=f"confirm_{filename}", type="primary"):
            try:
                with st.spinner("Writing to database…"):
                    results = self._importer.execute_import(
                        analysis, changed_by="web_import",
                        source_document=filename,
                        doc_date=datetime.now().strftime("%Y-%m-%d"),
                    )
                st.success(
                    f"✅ Done — **{results['new_items_added']}** added, "
                    f"**{results['items_updated']}** updated."
                )
                if results.get("errors"):
                    with st.expander(f"⚠️ {len(results['errors'])} write error(s)"):
                        for e in results["errors"]: st.caption(e)
            except Exception as exc:
                st.error(f"Commit failed: {exc}")
                st.code(traceback.format_exc())
