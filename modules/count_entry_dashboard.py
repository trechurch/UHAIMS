# ──────────────────────────────────────────────────────────────────────────────
#  modules/count_entry_dashboard.py  —  Physical Inventory Count Entry
#  v1.0.0
#
#  Presents items grouped by GL code (matching the printed count sheet).
#  Counters enter quantities; session is saved and then committed to QOH.
# ──────────────────────────────────────────────────────────────────────────────

import io
import streamlit as st
import pandas as pd
from datetime import date, datetime
from base import Dashboard
from utils import num_input, fmt_currency

try:
    import auth as _auth
    def _get_changed_by():
        return _auth.get_changed_by()
except Exception:
    def _get_changed_by():
        return "web_user"


class CountEntryDashboard(Dashboard):

    MANIFEST = {
        "id":       "count_entry_dashboard",
        "label":    "Count",
        "version":  "1.1.0",
        "icon":     "📝",
        "status":   "active",
        "page_key": "count_entry",
        "menu": {
            "parent":   "Dashboards",
            "label":    "Count",
            "shortcut": "N",
            "position": 55,
        },
        "sidebar": {
            "section":  "",
            "position": 55,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["items", "count_sessions", "count_lines", "item_history"],
        "session_keys": ["ce_session_id", "ce_counts"],
        "abilities": [
            "Enter physical inventory counts grouped by GL code",
            "Matches layout of the printed count sheet",
            "Auto-calculates extended value per line",
            "Save progress without committing",
            "Commit count to update quantity on hand with full history",
            "View previous count sessions",
        ],
        "permissions": {"min_role": "user"},
    }

    DOCS = {
        "summary": "Enter physical inventory counts. Layout matches the printed count sheet.",
        "usage": (
            "Start a new count. Enter quantities for each item. "
            "Save at any time. Commit when done to update inventory QOH."
        ),
        "demo_ready": True,
        "notes": "Items grouped by GL code to match the printed count sheet order.",
        "known_issues": [],
        "changelog": [
            {"version": "1.0.0", "date": "2026-03-26", "note": "Initial implementation."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        if "ce_session_id" not in st.session_state:
            st.session_state["ce_session_id"] = None
        if "ce_counts" not in st.session_state:
            st.session_state["ce_counts"] = {}

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**📝 Count Entry**")
            st.caption("Physical inventory count")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.title("📝 Count Entry")

        tab1, tab2, tab3 = st.tabs(["✏️ Active Count", "📋 Count History", "🖨️ Print Blank Sheet"])
        with tab1:
            self._render_active_count()
        with tab2:
            self._render_history()
        with tab3:
            self._render_print_blank()

    # ── Active Count ──────────────────────────────────────────────────────────

    def _render_active_count(self) -> None:
        session_id = st.session_state.get("ce_session_id")

        # ── Session header ────────────────────────────────────────────────────
        hc1, hc2, hc3 = st.columns([2, 2, 1])

        count_date = hc1.date_input("Count Date", value=date.today(),
                                    key="ce_date")
        notes = hc2.text_input("Notes", placeholder="Shift, counter name, etc.",
                                key="ce_notes")

        if not session_id:
            if hc3.button("▶ Start Count", type="primary",
                           use_container_width=True, key="ce_start"):
                session_id = self.db.create_count_session(
                    count_date=count_date,
                    created_by=_get_changed_by(),
                    notes=notes,
                )
                st.session_state["ce_session_id"] = session_id
                st.session_state["ce_counts"] = {}
                st.rerun()
            st.info("Start a new count session to begin entering quantities.")
            return

        session = self.db.get_count_session(session_id)
        if not session:
            st.warning("Session not found. Start a new count.")
            st.session_state["ce_session_id"] = None
            st.rerun()
            return

        if session["status"] == "committed":
            st.success(
                f"✅ Count committed on "
                f"{str(session.get('committed_at',''))[:16]} "
                f"by {session.get('committed_by','')}. "
                f"Total value: **${float(session.get('total_value',0)):,.2f}**"
            )
            if st.button("Start New Count", key="ce_new_after"):
                st.session_state["ce_session_id"] = None
                st.session_state["ce_counts"] = {}
                st.rerun()
            return

        st.caption(
            f"Session `{session_id[:8]}…`  ·  "
            f"{str(session.get('count_date',''))[:10]}  ·  "
            f"status: **{session['status']}**"
        )

        # ── Load items ────────────────────────────────────────────────────────
        items = self.db.get_all_items("active")
        if not items:
            st.warning("No active items for this cost center.")
            return

        counts = st.session_state.get("ce_counts", {})

        # ── GL group filter ───────────────────────────────────────────────────
        gl_codes = sorted({i.get("gl_code") or "— No GL —" for i in items})
        fc1, fc2 = st.columns([3, 1])
        gl_filter = fc1.multiselect("Filter GL Codes", gl_codes,
                                     default=[], key="ce_gl_filter",
                                     placeholder="All GL codes")
        show_zero = fc2.checkbox("Hide zero counts", key="ce_hide_zero")

        filtered = items
        if gl_filter:
            filtered = [i for i in items
                        if (i.get("gl_code") or "— No GL —") in gl_filter]

        # ── Group by GL code ──────────────────────────────────────────────────
        from collections import defaultdict
        groups: dict = defaultdict(list)
        for item in filtered:
            gl_key = f"{item.get('gl_code') or ''} — {item.get('gl_name') or 'No GL'}"
            groups[gl_key].append(item)

        total_value = 0.0
        all_lines   = []

        for gl_label in sorted(groups.keys()):
            group_items = groups[gl_label]
            st.markdown(f"#### {gl_label}")

            col_heads = st.columns([5, 2, 2, 2, 2])
            col_heads[0].caption("Description")
            col_heads[1].caption("Pack")
            col_heads[2].caption("Unit Cost")
            col_heads[3].caption("Count")
            col_heads[4].caption("Value")
            st.markdown(
                '<hr style="margin:2px 0 6px 0; border-color:#2d3748"/>',
                unsafe_allow_html=True,
            )

            for item in sorted(group_items, key=lambda x: x.get("description") or ""):
                key  = item["key"]
                cost = float(item.get("cost") or 0)
                conv = float(item.get("conv_ratio") or 1)
                uc   = cost / conv if conv > 1 else cost
                prev = float(counts.get(key, 0))

                if show_zero and prev == 0:
                    continue

                r1, r2, r3, r4, r5 = st.columns([5, 2, 2, 2, 2])
                r1.markdown(
                    f"<div style='font-size:13px;padding-top:6px'>"
                    f"{item.get('description','')}</div>",
                    unsafe_allow_html=True,
                )
                r2.markdown(
                    f"<div style='font-size:12px;color:#64748b;padding-top:6px'>"
                    f"{item.get('pack_type','')}</div>",
                    unsafe_allow_html=True,
                )
                r3.markdown(
                    f"<div style='font-size:12px;padding-top:6px'>${uc:.4f}</div>",
                    unsafe_allow_html=True,
                )
                new_qty = num_input(
                    "", value=prev, min_value=0.0, step=1.0,
                    key=f"ce_qty_{key}",
                    label_visibility="collapsed",
                )
                ext = new_qty * uc
                r5.markdown(
                    f"<div style='font-size:12px;padding-top:6px'>${ext:,.2f}</div>",
                    unsafe_allow_html=True,
                )

                if new_qty != prev:
                    counts[key] = new_qty

                total_value += ext
                all_lines.append({
                    "item_key":         key,
                    "description":      item.get("description", ""),
                    "pack_type":        item.get("pack_type", ""),
                    "gl_code":          item.get("gl_code", ""),
                    "gl_name":          item.get("gl_name", ""),
                    "unit_cost":        uc,
                    "quantity_counted": new_qty,
                    "extended_value":   round(ext, 4),
                })

        st.session_state["ce_counts"] = counts

        # ── Footer: totals + actions ──────────────────────────────────────────
        st.markdown("---")
        fc1, fc2, fc3 = st.columns(3)
        fc1.metric("Items with Counts",
                   sum(1 for v in counts.values() if v > 0))
        fc2.metric("Total Count Value", f"${total_value:,.2f}")
        fc3.metric("Total Items on Sheet", len(filtered))

        bc1, bc2, bc3 = st.columns(3)

        if bc1.button("💾 Save Progress", use_container_width=True, key="ce_save"):
            lines = [l for l in all_lines if l["quantity_counted"] > 0]
            self.db.save_count_lines(session_id, lines)
            st.success(f"Saved {len(lines)} counted lines.")

        committed = bc2.checkbox(
            f"Confirm commit of ${total_value:,.2f} count",
            key="ce_confirm_commit",
        )
        if bc3.button("✅ Commit Count", type="primary",
                      disabled=not committed,
                      use_container_width=True, key="ce_commit"):
            lines = [l for l in all_lines if l["quantity_counted"] > 0]
            self.db.save_count_lines(session_id, lines)
            result = self.db.commit_count_session(
                session_id, committed_by=_get_changed_by()
            )
            if result["errors"]:
                st.warning(
                    f"Committed {result['updated']} items with "
                    f"{len(result['errors'])} error(s)."
                )
                for e in result["errors"]:
                    st.caption(f"• {e}")
            else:
                st.success(
                    f"✅ Count committed — {result['updated']} items updated."
                )
            st.rerun()

        # Void / abandon
        with st.expander("⚠️ Abandon Count"):
            if st.button("🗑️ Void This Count Session",
                         key="ce_void", type="secondary"):
                st.session_state["ce_session_id"] = None
                st.session_state["ce_counts"] = {}
                st.rerun()

    # ── History ───────────────────────────────────────────────────────────────

    def _render_history(self) -> None:
        st.subheader("Count History")
        sessions = self.db.get_recent_count_sessions(limit=30)
        if not sessions:
            st.info("No count sessions yet.")
            return

        st.dataframe(pd.DataFrame([{
            "Date":      str(s.get("count_date", ""))[:10],
            "Status":    s["status"],
            "Items":     s.get("item_count", 0),
            "Value":     f"${float(s.get('total_value') or 0):,.2f}",
            "By":        s.get("created_by", ""),
            "Notes":     (s.get("notes") or "")[:40],
            "ID":        s["session_id"][:8] + "…",
        } for s in sessions]), use_container_width=True, hide_index=True)

        sel = st.selectbox(
            "View session detail",
            [s["session_id"] for s in sessions],
            format_func=lambda sid: next(
                f"{str(s.get('count_date',''))[:10]} — "
                f"{s['status']} — ${float(s.get('total_value') or 0):,.2f}"
                for s in sessions if s["session_id"] == sid
            ),
            key="ce_hist_sel",
        )
        if sel:
            lines = self.db.get_count_lines(sel)
            if lines:
                st.dataframe(pd.DataFrame([{
                    "GL":      l.get("gl_code", ""),
                    "Description": l["description"],
                    "Pack":    l.get("pack_type", ""),
                    "Unit $":  f"${float(l.get('unit_cost') or 0):.4f}",
                    "Count":   l.get("quantity_counted", 0),
                    "Value":   f"${float(l.get('extended_value') or 0):,.2f}",
                    "Notes":   l.get("notes", ""),
                } for l in lines]), use_container_width=True, hide_index=True)
            else:
                st.info("No lines saved for this session.")

        # ── Reload previous session ───────────────────────────────────────────
        open_sessions = [s for s in sessions if s["status"] == "open"]
        if open_sessions:
            st.markdown("---")
            st.caption(f"{len(open_sessions)} open session(s) found.")
            resume_id = st.selectbox(
                "Resume a saved session",
                [s["session_id"] for s in open_sessions],
                format_func=lambda sid: next(
                    f"{str(s.get('count_date',''))[:10]} — "
                    f"{s.get('item_count',0)} items"
                    for s in open_sessions if s["session_id"] == sid
                ),
                key="ce_resume_sel",
            )
            if st.button("▶ Resume Session", key="ce_resume_btn"):
                lines = self.db.get_count_lines(resume_id)
                resumed_counts = {
                    l["item_key"]: float(l.get("quantity_counted", 0))
                    for l in lines
                }
                st.session_state["ce_session_id"] = resume_id
                st.session_state["ce_counts"]     = resumed_counts
                st.rerun()

    # ── Print Blank Count Sheet ───────────────────────────────────────────────

    def _render_print_blank(self) -> None:
        st.subheader("🖨️ Print Blank Count Sheet")
        st.caption(
            "Generates a formatted Excel workbook — one sheet per location. "
            "Open in Excel or Google Sheets and print."
        )

        # Cost center map — all UHA locations
        CC_OPTIONS = {
            "57230 — Overhead":            "57230",
            "57231 — TDECU Concessions":   "57231",
            "57232 — Warehouse / Fertitta":"57232",
            "57233 — Schroeder Park":      "57233",
            "57234 — Softball Stadium":    "57234",
            "57235 — Team Dining":         "57235",
            "57236 — Catering":            "57236",
        }

        selected_labels = st.multiselect(
            "Select locations",
            list(CC_OPTIONS.keys()),
            default=["57231 — TDECU Concessions"],
            key="blank_sheet_locs",
        )
        count_date = st.date_input("Count Date", value=date.today(),
                                   key="blank_sheet_date")
        include_cost = st.checkbox("Include unit cost column", value=True,
                                   key="blank_sheet_cost")

        if not selected_labels:
            st.info("Select at least one location.")
            return

        if st.button("📥 Generate Count Sheet", type="primary",
                     key="blank_sheet_gen"):
            wb = self._build_workbook(
                selected_labels, CC_OPTIONS, count_date, include_cost
            )
            if wb is None:
                return
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            fname = f"count_sheet_{count_date.strftime('%Y%m%d')}.xlsx"
            st.download_button(
                f"⬇️ Download {fname}",
                data=buf,
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="blank_sheet_dl",
            )

    def _build_workbook(self, selected_labels, cc_map, count_date, include_cost):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import (Font, PatternFill, Alignment,
                                          Border, Side, numbers)
            from openpyxl.utils import get_column_letter
        except ImportError:
            st.error("openpyxl is required — run: pip install openpyxl")
            return None

        wb = Workbook()
        wb.remove(wb.active)  # remove default blank sheet

        thin = Side(style="thin", color="BBBBBB")
        thick = Side(style="medium", color="888888")
        cell_border = Border(left=thin, right=thin, top=thin, bottom=thin)
        header_border = Border(left=thick, right=thick, top=thick, bottom=thick)

        hdr_fill   = PatternFill("solid", fgColor="1A1A2E")  # nav dark blue
        gl_fill    = PatternFill("solid", fgColor="16213E")
        alt_fill   = PatternFill("solid", fgColor="F8FAFC")
        white_fill = PatternFill("solid", fgColor="FFFFFF")

        hdr_font   = Font(bold=True, color="FFFFFF", size=10)
        gl_font    = Font(bold=True, color="E63946", size=9)   # nav red
        body_font  = Font(size=9)

        center = Alignment(horizontal="center", vertical="center", wrap_text=False)
        left   = Alignment(horizontal="left",   vertical="center")

        for label in selected_labels:
            cc_code = cc_map[label]
            short   = label.split("—")[1].strip()[:28]   # sheet tab name

            # Load items for this cost center
            items = self.db.get_items_by_cost_center(cc_code)
            if not items:
                # Try unfiltered fallback — items may not have cost_center tagged yet
                items = self.db.get_all_items("active")

            ws = wb.create_sheet(title=short[:31])

            # ── Title rows ────────────────────────────────────────────────────
            ws.merge_cells("A1:G1")
            t = ws["A1"]
            t.value       = f"UHA INVENTORY COUNT SHEET — {short.upper()}"
            t.font        = Font(bold=True, color="FFFFFF", size=12)
            t.fill        = PatternFill("solid", fgColor="1A1A2E")
            t.alignment   = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[1].height = 22

            ws.merge_cells("A2:G2")
            d = ws["A2"]
            d.value     = f"Count Date: {count_date.strftime('%A, %B %d, %Y')}          Location: {label}"
            d.font      = Font(italic=True, size=9, color="444444")
            d.alignment = Alignment(horizontal="left", vertical="center")
            ws.row_dimensions[2].height = 14

            # ── Column headers ────────────────────────────────────────────────
            if include_cost:
                col_headers = ["GL Code", "Description", "Pack Type",
                               "Unit Cost", "COUNT", "UNIT", "NOTES"]
                col_widths  = [10, 42, 14, 11, 9, 8, 18]
            else:
                col_headers = ["GL Code", "Description", "Pack Type",
                               "COUNT", "UNIT", "NOTES"]
                col_widths  = [10, 46, 14, 9, 8, 20]

            for ci, (hdr, w) in enumerate(zip(col_headers, col_widths), start=1):
                c = ws.cell(row=3, column=ci, value=hdr)
                c.font      = hdr_font
                c.fill      = hdr_fill
                c.alignment = center if ci > 2 else left
                c.border    = header_border
                ws.column_dimensions[get_column_letter(ci)].width = w
            ws.row_dimensions[3].height = 16

            # ── Sort items by GL code → description ───────────────────────────
            from collections import defaultdict
            groups: dict = defaultdict(list)
            for item in items:
                gl_key = item.get("gl_code") or "ZZZ"
                groups[gl_key].append(item)

            row = 4
            for gl_code in sorted(groups.keys()):
                group_items = groups[gl_code]
                gl_name     = (group_items[0].get("gl_name") or "").upper()
                gl_label    = f"{gl_code}  —  {gl_name}" if gl_name else gl_code

                # GL group header row
                last_col = len(col_headers)
                ws.merge_cells(
                    start_row=row, start_column=1,
                    end_row=row,   end_column=last_col
                )
                gh = ws.cell(row=row, column=1, value=gl_label)
                gh.font      = gl_font
                gh.fill      = gl_fill
                gh.alignment = left
                gh.border    = cell_border
                ws.row_dimensions[row].height = 13
                row += 1

                for i, item in enumerate(
                    sorted(group_items, key=lambda x: x.get("description") or "")
                ):
                    fill = white_fill if i % 2 == 0 else alt_fill
                    cost = float(item.get("cost") or 0)
                    conv = float(item.get("conv_ratio") or 1)
                    uc   = cost / conv if conv > 1 else cost

                    if include_cost:
                        row_vals = [
                            item.get("gl_code") or "",
                            item.get("description") or "",
                            item.get("pack_type") or "",
                            uc,
                            "",   # COUNT — blank for writing
                            "",   # UNIT
                            "",   # NOTES
                        ]
                    else:
                        row_vals = [
                            item.get("gl_code") or "",
                            item.get("description") or "",
                            item.get("pack_type") or "",
                            "",   # COUNT
                            "",   # UNIT
                            "",   # NOTES
                        ]

                    for ci, val in enumerate(row_vals, start=1):
                        c = ws.cell(row=row, column=ci, value=val)
                        c.font      = body_font
                        c.fill      = fill
                        c.border    = cell_border
                        # Cost column — currency format
                        if include_cost and ci == 4 and isinstance(val, float):
                            c.number_format = '"$"#,##0.0000'
                            c.alignment = center
                        elif ci > (3 if not include_cost else 4):
                            c.alignment = center
                        else:
                            c.alignment = left

                    ws.row_dimensions[row].height = 13
                    row += 1

            # Freeze top 3 rows
            ws.freeze_panes = "A4"

            # Print settings
            ws.page_setup.orientation      = "portrait"
            ws.page_setup.paperSize        = ws.PAPERSIZE_LETTER
            ws.page_setup.fitToPage        = True
            ws.page_setup.fitToWidth       = 1
            ws.page_setup.fitToHeight      = 0
            ws.print_title_rows            = "1:3"
            ws.sheet_properties.pageSetUpPr.fitToPage = True

        return wb

# ── end of CountEntryDashboard ────────────────────────────────────────────────
