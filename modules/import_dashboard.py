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

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Rows",  analysis["total_rows"])
        c2.metric("New Items",   len(analysis["new_items"]))
        c3.metric("Updates",     len(analysis["updates"]))
        c4.metric("Flagged",     len(analysis.get("flagged", [])))
        c5.metric("Skipped/Err", len(analysis["skipped"]) + len(analysis["errors"]))

        if analysis["new_items"]:
            with st.expander(f"📋 {len(analysis['new_items'])} New Items"):
                st.dataframe(pd.DataFrame([{
                    "Conf": (
                        "🟢" if i.get("confidence", 1.0) >= 0.90 else
                        "🟡" if i.get("confidence", 1.0) >= 0.70 else "🔴"
                    ),
                    "Key": i["key"],
                    "Description": i["description"],
                } for i in analysis["new_items"]]),
                             use_container_width=True, hide_index=True)

        if analysis["updates"]:
            with st.expander(f"🔄 {len(analysis['updates'])} Updates"):
                st.dataframe(pd.DataFrame([{
                    "Conf": (
                        "🟢" if i.get("confidence", 1.0) >= 0.90 else
                        "🟡" if i.get("confidence", 1.0) >= 0.70 else "🔴"
                    ),
                    "Key": i["key"],
                    "Description": i["description"],
                    "Fields Changed": ", ".join(i["changes"].keys()),
                } for i in analysis["updates"]]),
                             use_container_width=True, hide_index=True)

        if analysis["errors"]:
            with st.expander(f"⚠️ {len(analysis['errors'])} Row Errors"):
                for e in analysis["errors"]: st.caption(e)

        # ── F-003: Flagged Row Review (pre-commit, editable) ──────────────────
        flagged = analysis.get("flagged", [])
        edited_flagged = None
        if flagged:
            with st.expander(
                f"🔍 {len(flagged)} flagged row(s) — low-confidence, review before committing",
                expanded=True,
            ):
                st.caption(
                    "These rows had ambiguous pack types or conv ratios. "
                    "Edit any field, uncheck **Commit** to skip, then confirm below."
                )
                flagged_df = pd.DataFrame([{
                    "Commit":      True,
                    "Description": f["description"],
                    "Pack Type":   f["row_data"].get("pack_type", ""),
                    "Cost":        float(f["row_data"].get("cost") or 0),
                    "Conv Ratio":  float(f["row_data"].get("conv_ratio") or 1.0),
                    "Flag":        f.get("flag_reason", ""),
                } for f in flagged])

                edited_flagged = st.data_editor(
                    flagged_df,
                    key=f"flagged_editor_{filename}",
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Commit":     st.column_config.CheckboxColumn("Commit", default=True),
                        "Cost":       st.column_config.NumberColumn("Cost", format="$%.4f", min_value=0.0),
                        "Conv Ratio": st.column_config.NumberColumn("Conv Ratio", format="%.4f", min_value=0.01),
                        "Flag":       st.column_config.TextColumn("Flag Reason", disabled=True),
                    },
                    disabled=["Flag"],
                )

        # ── F-036: Price Volatility Review (pre-commit, interactive) ─────────
        price_alerts = analysis.get("price_alerts", [])
        excluded_keys: set = set()
        if price_alerts:
            st.warning(
                f"⚠️ **{len(price_alerts)} item(s)** have a cost change > 20%. "
                "Uncheck any row to exclude it from this import."
            )
            alert_df = pd.DataFrame([{
                "Include":     True,
                "Description": a["description"],
                "Old Cost":    f"${a['old_cost']:.2f}",
                "New Cost":    f"${a['new_cost']:.2f}",
                "Change":      f"{'▲' if a['direction'] == 'up' else '▼'} {a['pct_change']}%",
            } for a in price_alerts])

            edited = st.data_editor(
                alert_df,
                key=f"price_alert_editor_{filename}",
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Include": st.column_config.CheckboxColumn("Include", default=True),
                },
                disabled=["Description", "Old Cost", "New Cost", "Change"],
            )
            excluded_keys = {
                price_alerts[i]["key"]
                for i, inc in enumerate(edited["Include"])
                if not inc
            }
            if excluded_keys:
                st.caption(
                    f"🚫 {len(excluded_keys)} item(s) excluded — "
                    "their existing cost will not be changed."
                )

        if not analysis["new_items"] and not analysis["updates"]:
            st.warning("Nothing to import from this file.")
            return

        if st.button(f"✅ Confirm Import — {filename}",
                     key=f"confirm_{filename}", type="primary"):
            doc_date = datetime.now().strftime("%Y-%m-%d")

            # Apply pre-commit exclusions from price review (F-036)
            if excluded_keys:
                analysis["updates"] = [
                    u for u in analysis["updates"] if u["key"] not in excluded_keys
                ]

            # Build corrected flagged items from editor (F-003)
            flagged_to_commit = []
            if flagged and edited_flagged is not None:
                for i, row in edited_flagged.iterrows():
                    if not row["Commit"]:
                        continue
                    item = flagged[i]
                    rd = dict(item["row_data"])
                    rd["pack_type"]  = row["Pack Type"]
                    rd["cost"]       = float(row["Cost"])
                    rd["conv_ratio"] = float(row["Conv Ratio"])
                    flagged_to_commit.append({**item, "row_data": rd})

            try:
                with st.spinner("Writing to database…"):
                    results = self._importer.execute_import(
                        analysis, changed_by="web_import",
                        source_document=filename,
                        doc_date=doc_date,
                    )
                flagged_results = {"added": 0, "updated": 0, "errors": []}
                if flagged_to_commit:
                    flagged_results = self._importer.execute_flagged(
                        flagged_to_commit,
                        changed_by="web_import",
                        source_document=filename,
                        doc_date=doc_date,
                    )

                total_added   = results["new_items_added"] + flagged_results["added"]
                total_updated = results["items_updated"]   + flagged_results["updated"]
                skipped_count = len(flagged) - len(flagged_to_commit) if flagged else 0

                msg = (
                    f"✅ Done — **{total_added}** added, **{total_updated}** updated"
                )
                if skipped_count:
                    msg += f", **{skipped_count}** flagged row(s) skipped"
                if excluded_keys:
                    msg += f", **{len(excluded_keys)}** price alert(s) excluded"
                st.success(msg + ".")

                all_errors = results.get("errors", []) + flagged_results.get("errors", [])
                if all_errors:
                    with st.expander(f"⚠️ {len(all_errors)} write error(s)"):
                        for e in all_errors: st.caption(e)

                # ── F-002: Import Variance Report ──────────────────────────
                try:
                    history = self.db.get_history_by_source_document(filename)
                except Exception:
                    history = []

                if history:
                    with st.expander(
                        f"📊 Variance Report — {len(history)} field change(s)", expanded=True
                    ):
                        # Cost delta summary
                        cost_rows = [
                            h for h in history if h.get("field_changed") == "cost"
                        ]
                        if cost_rows:
                            total_delta = sum(
                                float(h.get("new_value") or 0) - float(h.get("old_value") or 0)
                                for h in cost_rows
                                if h.get("old_value") and h.get("new_value")
                            )
                            direction = "increase" if total_delta >= 0 else "decrease"
                            col_a, col_b = st.columns(2)
                            col_a.metric(
                                "Cost Changes",
                                len(cost_rows),
                                help="Items whose unit cost changed in this import",
                            )
                            col_b.metric(
                                "Total Cost Impact",
                                f"${abs(total_delta):.2f} {direction}",
                                delta=f"{'+' if total_delta >= 0 else ''}{total_delta:.2f}",
                            )

                        variance_rows = []
                        for h in history:
                            old_v = h.get("old_value") or ""
                            new_v = h.get("new_value") or ""
                            delta = ""
                            if h.get("field_changed") == "cost":
                                try:
                                    d = float(new_v) - float(old_v)
                                    delta = f"{'+' if d >= 0 else ''}{d:.2f}"
                                except (ValueError, TypeError):
                                    pass
                            variance_rows.append({
                                "Item Key":   h.get("item_key", ""),
                                "Field":      h.get("field_changed", ""),
                                "Old":        old_v,
                                "New":        new_v,
                                "Δ":          delta,
                            })
                        st.dataframe(pd.DataFrame(variance_rows),
                                     use_container_width=True, hide_index=True)

            except Exception as exc:
                st.error(f"Commit failed: {exc}")
                st.code(traceback.format_exc())
