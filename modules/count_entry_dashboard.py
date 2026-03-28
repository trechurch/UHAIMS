# ──────────────────────────────────────────────────────────────────────────────
#  modules/count_entry_dashboard.py  —  Physical Inventory Count
#  v2.0.0  —  Complete retool: Print / Enter Manual / Scan tabs
# ──────────────────────────────────────────────────────────────────────────────

import io
import json
import streamlit as st
import pandas as pd
from collections import defaultdict
from datetime import date, datetime
from base import Dashboard
from utils import num_input, fmt_currency, fmt_num

try:
    import auth as _auth
    def _get_changed_by(): return _auth.get_changed_by()
except Exception:
    def _get_changed_by(): return "web_user"

# ── Column catalogue ──────────────────────────────────────────────────────────

COLUMNS = [
    {"key": "gl_code",     "label": "GL Code",     "width": 10, "default": True,  "editable": False},
    {"key": "description", "label": "Description", "width": 40, "default": True,  "editable": False},
    {"key": "pack_type",   "label": "Pack / Unit", "width": 14, "default": True,  "editable": False},
    {"key": "vendor",      "label": "Vendor",      "width": 16, "default": False, "editable": False},
    {"key": "unit_cost",   "label": "Unit Cost",   "width": 10, "default": True,  "editable": False},
    {"key": "last_count",  "label": "Last Count",  "width": 10, "default": False, "editable": False},
    {"key": "last_value",  "label": "Last Value",  "width": 10, "default": False, "editable": False},
    {"key": "case_count",  "label": "CASE",        "width": 8,  "default": True,  "editable": True},
    {"key": "unit_count",  "label": "UNIT",        "width": 8,  "default": True,  "editable": True},
    {"key": "notes",       "label": "NOTES",       "width": 18, "default": True,  "editable": True},
]

COL_KEYS    = [c["key"]   for c in COLUMNS]
COL_LABELS  = {c["key"]: c["label"] for c in COLUMNS}
COL_WIDTHS  = {c["key"]: c["width"] for c in COLUMNS}

SORT_OPTIONS = {
    "GL Code → Description": "gl_desc",
    "Description (A–Z)":     "desc_az",
    "Pack Type":              "pack",
    "Vendor → Description":  "vendor_desc",
}

CC_OPTIONS = {
    "57230 — Overhead":             "57230",
    "57231 — TDECU Concessions":    "57231",
    "57232 — Warehouse / Fertitta": "57232",
    "57233 — Schroeder Park":       "57233",
    "57234 — Softball Stadium":     "57234",
    "57235 — Team Dining":          "57235",
    "57236 — Catering":             "57236",
}

CC_LABELS = {v: k for k, v in CC_OPTIONS.items()}


def _default_cols():
    return [c["key"] for c in COLUMNS if c["default"]]


def _sort_items(items, sort_key):
    if sort_key == "desc_az":
        return sorted(items, key=lambda x: x.get("description") or "")
    if sort_key == "pack":
        return sorted(items, key=lambda x: (x.get("pack_type") or "", x.get("description") or ""))
    if sort_key == "vendor_desc":
        return sorted(items, key=lambda x: (x.get("vendor") or "", x.get("description") or ""))
    # default: gl_desc
    return sorted(items, key=lambda x: (x.get("gl_code") or "ZZZ", x.get("description") or ""))


def _group_by_gl(items):
    groups = defaultdict(list)
    for item in items:
        gl_key = f"{item.get('gl_code') or ''} — {item.get('gl_name') or 'No GL'}"
        groups[gl_key].append(item)
    return dict(sorted(groups.items()))


def _encode_config(config: dict) -> str:
    return json.dumps(config, separators=(",", ":"))


def _decode_config(s: str) -> dict:
    try:
        return json.loads(s)
    except Exception:
        return {}


class CountEntryDashboard(Dashboard):

    MANIFEST = {
        "id":       "count_entry_dashboard",
        "label":    "Count",
        "version":  "2.0.0",
        "icon":     "📋",
        "status":   "active",
        "page_key": "count_entry",
        "menu": {
            "parent":   "Dashboards",
            "label":    "Count",
            "shortcut": "C",
            "position": 40,
        },
        "sidebar": {
            "section":  "",
            "position": 40,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["items", "count_sessions", "count_lines", "item_history"],
        "session_keys": ["ce_session_id", "ce_counts", "ce_config"],
        "abilities": [
            "Print formatted count sheets (Excel) for any location",
            "Configurable columns, sort order, and orientation per sheet",
            "QR code embedded in sheet encodes exact print configuration",
            "Enter manual counts with GL-grouped layout matching printed sheet",
            "Ten-key friendly data-editor with case + unit entry columns",
            "Scan / upload a filled count sheet (Excel) to auto-load counts",
            "QR code on scanned sheet auto-restores print configuration",
            "Save progress and resume sessions; commit updates QOH",
        ],
        "permissions": {"min_role": "user"},
    }

    DOCS = {
        "summary": "Full physical inventory count workflow: Print → Enter → Scan.",
        "usage": (
            "1. Print tab: configure and download a count sheet for each stand.  "
            "2. Enter tab: key in counts using the same layout as your printed sheet.  "
            "3. Scan tab: upload a filled-in Excel count sheet to auto-load counts."
        ),
        "demo_ready": True,
        "notes": "QR code on printed sheet encodes column/sort config for auto-recognition.",
        "known_issues": [],
        "changelog": [
            {"version": "2.0.0", "date": "2026-03-28",
             "note": "Complete retool: Print/Enter/Scan tabs, column selector, QR code, data-editor."},
            {"version": "1.1.0", "date": "2026-03-28", "note": "Label rename to 'Count'."},
            {"version": "1.0.0", "date": "2026-03-26", "note": "Initial implementation."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        defaults = {
            "ce_session_id": None,
            "ce_counts":     {},
            "ce_config": {
                "cols":    _default_cols(),
                "sort":    "gl_desc",
                "orient":  "portrait",
                "date":    str(date.today()),
            },
        }
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**📋 Count**")
            st.caption("Print · Enter · Scan")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.markdown("### 📋 Physical Inventory Count")
        tab_print, tab_enter, tab_scan, tab_history = st.tabs([
            "🖨️ Print Count Sheets",
            "✏️ Enter Manual Counts",
            "📷 Scan Count Sheets",
            "📂 Session History",
        ])
        with tab_print:
            self._render_print()
        with tab_enter:
            self._render_enter()
        with tab_scan:
            self._render_scan()
        with tab_history:
            self._render_history()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — PRINT COUNT SHEETS
    # ══════════════════════════════════════════════════════════════════════════

    def _render_print(self) -> None:
        st.markdown("#### Configure & Download")
        st.caption(
            "Select stands, choose columns, pick sort order. "
            "Generated Excel embeds a QR code encoding the exact configuration — "
            "upload the scanned sheet and it will auto-configure the intake form."
        )

        # ── Stand selector ────────────────────────────────────────────────────
        current_cc = None
        try:
            from app import get_current_database
            current_cc = get_current_database()
        except Exception:
            current_cc = "57231"

        all_stands = self.db.get_stands(cost_center=current_cc)

        if all_stands:
            stand_options = {s["stand_name"]: s["stand_id"] for s in all_stands}
            selected_names = st.multiselect(
                "Stands",
                list(stand_options.keys()),
                default=list(stand_options.keys())[:1],
                key="ps_stands",
            )
            use_stands = True
        else:
            # Fallback: cost center level
            st.caption("No stands configured — selecting by location.")
            selected_labels = st.multiselect(
                "Locations",
                list(CC_OPTIONS.keys()),
                default=["57231 — TDECU Concessions"],
                key="ps_locs",
            )
            stand_options  = {}
            selected_names = []
            use_stands     = False

        # ── Options row ───────────────────────────────────────────────────────
        oa, ob, oc = st.columns(3)
        count_date = oa.date_input("Count Date", value=date.today(), key="ps_date")
        orient     = ob.radio("Orientation", ["Portrait", "Landscape"],
                              horizontal=True, key="ps_orient")
        sort_label = oc.selectbox("Sort Order", list(SORT_OPTIONS.keys()), key="ps_sort")
        sort_key   = SORT_OPTIONS[sort_label]

        # ── Column selector ───────────────────────────────────────────────────
        st.markdown("**Columns to include** (drag to reorder — pick order left to right)")
        all_col_labels = [COL_LABELS[k] for k in COL_KEYS]
        default_labels = [COL_LABELS[k] for k in _default_cols()]
        chosen_labels  = st.multiselect(
            "", all_col_labels, default=default_labels,
            key="ps_cols", label_visibility="collapsed",
        )
        chosen_keys = [k for k in COL_KEYS if COL_LABELS[k] in chosen_labels]

        # Ensure at least description is included
        if "description" not in chosen_keys:
            chosen_keys = ["description"] + chosen_keys

        # Save config to session state (shared with Enter tab)
        cfg = {
            "cols":   chosen_keys,
            "sort":   sort_key,
            "orient": orient.lower(),
            "date":   str(count_date),
        }
        st.session_state["ce_config"] = cfg

        # ── Preview ───────────────────────────────────────────────────────────
        if use_stands:
            if not selected_names:
                st.info("Select at least one stand.")
                return
            total_items = sum(
                self.db.get_stand_item_count(stand_options[n])
                for n in selected_names
            )
            st.caption(
                f"📋 {len(selected_names)} stand(s) · ~{total_items:,} items · "
                f"{len(chosen_keys)} columns · {orient}"
            )
        else:
            if not selected_labels:
                st.info("Select at least one location.")
                return
            total_items = sum(
                len(self.db.get_items_by_cost_center(CC_OPTIONS[lbl]) or [])
                for lbl in selected_labels
            )
            st.caption(
                f"📋 {len(selected_labels)} location(s) · ~{total_items:,} items · "
                f"{len(chosen_keys)} columns · {orient}"
            )

        if st.button("📥 Generate Count Sheets", type="primary", key="ps_gen"):
            with st.spinner("Building workbook…"):
                if use_stands:
                    wb = self._build_workbook_stands(
                        selected_names, stand_options, count_date,
                        chosen_keys, sort_key, orient.lower(), cfg
                    )
                else:
                    wb = self._build_workbook(
                        selected_labels, count_date, chosen_keys, sort_key,
                        orient.lower(), cfg
                    )
            if wb:
                buf = io.BytesIO()
                wb.save(buf)
                buf.seek(0)
                fname = f"count_sheet_{count_date.strftime('%Y%m%d')}.xlsx"
                st.download_button(
                    f"⬇️ Download {fname}",
                    data=buf, file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="ps_dl",
                )
                n_sheets = len(selected_names) if use_stands else len(selected_labels)
                st.success(
                    f"Workbook ready — {n_sheets} sheet(s). "
                    "QR code embedded on each sheet encodes the column configuration."
                )

    # ── Workbook builder ──────────────────────────────────────────────────────

    def _build_workbook(self, labels, count_date, col_keys, sort_key,
                        orient, cfg):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
            from openpyxl.drawing.image import Image as XLImage
        except ImportError:
            st.error("openpyxl is required — run: pip install openpyxl")
            return None

        wb = Workbook()
        wb.remove(wb.active)

        thin        = Side(style="thin",   color="BBBBBB")
        thick       = Side(style="medium", color="888888")
        cell_border = Border(left=thin, right=thin, top=thin, bottom=thin)
        hdr_border  = Border(left=thick, right=thick, top=thick, bottom=thick)

        hdr_fill  = PatternFill("solid", fgColor="1A1A2E")
        gl_fill   = PatternFill("solid", fgColor="16213E")
        alt_fill  = PatternFill("solid", fgColor="F0F4F8")
        wht_fill  = PatternFill("solid", fgColor="FFFFFF")
        hdr_font  = Font(bold=True, color="FFFFFF", size=10)
        gl_font   = Font(bold=True, color="E63946", size=9)
        body_font = Font(size=9)
        center    = Alignment(horizontal="center", vertical="center")
        left_al   = Alignment(horizontal="left",   vertical="center")

        # ── QR code image (encode the config) ─────────────────────────────────
        qr_img_buf = None
        try:
            import qrcode as _qr
            qr = _qr.QRCode(box_size=4, border=2)
            qr.add_data(_encode_config(cfg))
            qr.make(fit=True)
            pil_img = qr.make_image(fill_color="black", back_color="white")
            qr_img_buf = io.BytesIO()
            pil_img.save(qr_img_buf, format="PNG")
            qr_img_buf.seek(0)
        except Exception:
            pass  # qrcode not installed — skip silently

        for label in labels:
            cc_code = CC_OPTIONS[label]
            short   = label.split("—")[1].strip()[:28]
            items   = self.db.get_items_by_cost_center(cc_code) or []
            if not items:
                items = self.db.get_all_items("active") or []

            items = _sort_items(items, sort_key)
            ws    = wb.create_sheet(title=short[:31])

            # ── Title ─────────────────────────────────────────────────────────
            n_cols = len(col_keys)
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
            t = ws.cell(1, 1, f"UHA INVENTORY COUNT — {short.upper()}")
            t.font      = Font(bold=True, color="FFFFFF", size=12)
            t.fill      = hdr_fill
            t.alignment = center
            ws.row_dimensions[1].height = 22

            ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
            d = ws.cell(2, 1, f"Count Date: {count_date.strftime('%A, %B %d, %Y')}    Stand: {label}")
            d.font      = Font(italic=True, size=9, color="444444")
            d.alignment = left_al
            ws.row_dimensions[2].height = 14

            # ── Column headers ─────────────────────────────────────────────────
            for ci, ck in enumerate(col_keys, 1):
                c = ws.cell(3, ci, COL_LABELS[ck])
                c.font      = hdr_font
                c.fill      = hdr_fill
                c.alignment = left_al if ci <= 2 else center
                c.border    = hdr_border
                ws.column_dimensions[get_column_letter(ci)].width = COL_WIDTHS.get(ck, 12)
            ws.row_dimensions[3].height = 16

            # ── Data rows grouped by GL ────────────────────────────────────────
            if sort_key == "gl_desc":
                groups = _group_by_gl(items)
                rows_to_write = []
                for gl_label, grp in groups.items():
                    rows_to_write.append(("group_header", gl_label))
                    for item in grp:
                        rows_to_write.append(("item", item))
            else:
                rows_to_write = [("item", i) for i in items]

            row = 4
            item_idx = 0
            for rtype, rdata in rows_to_write:
                if rtype == "group_header":
                    ws.merge_cells(start_row=row, start_column=1,
                                   end_row=row, end_column=n_cols)
                    gh = ws.cell(row, 1, rdata)
                    gh.font = gl_font; gh.fill = gl_fill
                    gh.alignment = left_al; gh.border = cell_border
                    ws.row_dimensions[row].height = 13
                else:
                    item  = rdata
                    fill  = wht_fill if item_idx % 2 == 0 else alt_fill
                    cost  = float(item.get("cost") or 0)
                    conv  = float(item.get("conv_ratio") or 1)
                    uc    = cost / conv if conv > 1 else cost

                    for ci, ck in enumerate(col_keys, 1):
                        if   ck == "gl_code":    val = item.get("gl_code") or ""
                        elif ck == "description":val = item.get("description") or ""
                        elif ck == "pack_type":  val = item.get("pack_type") or ""
                        elif ck == "vendor":     val = item.get("vendor") or ""
                        elif ck == "unit_cost":  val = uc
                        elif ck == "last_count": val = float(item.get("quantity_on_hand") or 0)
                        elif ck == "last_value": val = float(item.get("quantity_on_hand") or 0) * uc
                        else:                    val = ""   # entry columns left blank

                        c = ws.cell(row, ci, val)
                        c.font = body_font; c.fill = fill; c.border = cell_border
                        if ck in ("unit_cost", "last_value"):
                            c.number_format = '"$"#,##0.00'
                            c.alignment = center
                        elif ck in ("case_count", "unit_count", "last_count"):
                            c.number_format = "#,##0.##"
                            c.alignment = center
                        elif ci > 2:
                            c.alignment = center
                        else:
                            c.alignment = left_al

                    ws.row_dimensions[row].height = 13
                    item_idx += 1

                row += 1

            ws.freeze_panes = "A4"

            # Print settings
            ws.page_setup.orientation = (
                "landscape" if orient == "landscape" else "portrait"
            )
            ws.page_setup.paperSize    = ws.PAPERSIZE_LETTER
            ws.page_setup.fitToPage    = True
            ws.page_setup.fitToWidth   = 1
            ws.page_setup.fitToHeight  = 0
            ws.print_title_rows        = "1:3"
            ws.sheet_properties.pageSetUpPr.fitToPage = True

            # ── Embed QR code ─────────────────────────────────────────────────
            if qr_img_buf:
                try:
                    qr_img_buf.seek(0)
                    img = XLImage(io.BytesIO(qr_img_buf.read()))
                    img.width  = 72
                    img.height = 72
                    # Place in top-right corner (column after last data col)
                    qr_col = get_column_letter(n_cols + 1)
                    ws.column_dimensions[qr_col].width = 11
                    ws.add_image(img, f"{qr_col}1")
                except Exception:
                    pass

        return wb

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — ENTER MANUAL COUNTS
    # ── Stand-aware workbook builder ──────────────────────────────────────────

    def _build_workbook_stands(self, stand_names, stand_options, count_date,
                               col_keys, sort_key, orient, cfg):
        """Build workbook using stand_items (ordered, par-qty aware)."""
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
            from openpyxl.drawing.image import Image as XLImage
        except ImportError:
            st.error("openpyxl required")
            return None

        wb = Workbook()
        wb.remove(wb.active)

        thin       = Side(style="thin",   color="BBBBBB")
        thick      = Side(style="medium", color="888888")
        cb         = Border(left=thin, right=thin, top=thin, bottom=thin)
        hb         = Border(left=thick, right=thick, top=thick, bottom=thick)
        hdr_fill   = PatternFill("solid", fgColor="1A1A2E")
        gl_fill    = PatternFill("solid", fgColor="16213E")
        alt_fill   = PatternFill("solid", fgColor="F0F4F8")
        wht_fill   = PatternFill("solid", fgColor="FFFFFF")
        hdr_font   = Font(bold=True, color="FFFFFF", size=10)
        gl_font    = Font(bold=True, color="E63946", size=9)
        body_font  = Font(size=9)
        center_al  = Alignment(horizontal="center", vertical="center")
        left_al    = Alignment(horizontal="left",   vertical="center")

        qr_img_buf = None
        try:
            import qrcode as _qr
            qr = _qr.QRCode(box_size=4, border=2)
            qr.add_data(_encode_config(cfg))
            qr.make(fit=True)
            pil_img = qr.make_image(fill_color="black", back_color="white")
            qr_img_buf = io.BytesIO()
            pil_img.save(qr_img_buf, format="PNG")
            qr_img_buf.seek(0)
        except Exception:
            pass

        for stand_name in stand_names:
            stand_id = stand_options[stand_name]
            items    = self.db.get_stand_items(stand_id)
            if not items:
                continue

            # Items already in sort_order from DB; re-sort if user chose different order
            if sort_key != "gl_desc":
                items = _sort_items(items, sort_key)

            n_cols = len(col_keys)
            ws     = wb.create_sheet(title=stand_name[:31])

            # Title
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
            t = ws.cell(1, 1, f"UHA INVENTORY COUNT — {stand_name.upper()}")
            t.font = Font(bold=True, color="FFFFFF", size=12)
            t.fill = hdr_fill; t.alignment = center_al
            ws.row_dimensions[1].height = 22

            ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
            d = ws.cell(2, 1,
                f"Count Date: {count_date.strftime('%A, %B %d, %Y')}    Stand: {stand_name}")
            d.font = Font(italic=True, size=9, color="444444")
            d.alignment = left_al
            ws.row_dimensions[2].height = 14

            # Headers
            for ci, ck in enumerate(col_keys, 1):
                c = ws.cell(3, ci, COL_LABELS[ck])
                c.font = hdr_font; c.fill = hdr_fill; c.border = hb
                c.alignment = left_al if ci <= 2 else center_al
                ws.column_dimensions[get_column_letter(ci)].width = COL_WIDTHS.get(ck, 12)
            ws.row_dimensions[3].height = 16

            # Group by GL if gl_desc sort, else flat list
            if sort_key == "gl_desc":
                rows_to_write = []
                groups = _group_by_gl(items)
                for gl_label, grp in groups.items():
                    rows_to_write.append(("group_header", gl_label))
                    for item in grp:
                        rows_to_write.append(("item", item))
            else:
                rows_to_write = [("item", i) for i in items]

            row = 4; item_idx = 0
            for rtype, rdata in rows_to_write:
                if rtype == "group_header":
                    ws.merge_cells(start_row=row, start_column=1,
                                   end_row=row, end_column=n_cols)
                    gh = ws.cell(row, 1, rdata)
                    gh.font = gl_font; gh.fill = gl_fill
                    gh.alignment = left_al; gh.border = cb
                    ws.row_dimensions[row].height = 13
                else:
                    item = rdata
                    fill = wht_fill if item_idx % 2 == 0 else alt_fill
                    cost = float(item.get("cost") or 0)
                    conv = float(item.get("conv_ratio") or 1)
                    uc   = cost / conv if conv > 1 else cost
                    par  = float(item.get("par_qty") or 0)

                    for ci, ck in enumerate(col_keys, 1):
                        if   ck == "gl_code":    val = item.get("gl_code") or ""
                        elif ck == "description":val = item.get("description") or ""
                        elif ck == "pack_type":  val = item.get("pack_type") or ""
                        elif ck == "vendor":     val = item.get("vendor") or ""
                        elif ck == "unit_cost":  val = uc
                        elif ck == "last_count": val = float(item.get("quantity_on_hand") or 0)
                        elif ck == "last_value": val = float(item.get("quantity_on_hand") or 0) * uc
                        else:                    val = ""

                        c = ws.cell(row, ci, val)
                        c.font = body_font; c.fill = fill; c.border = cb
                        if ck in ("unit_cost", "last_value"):
                            c.number_format = '"$"#,##0.00'; c.alignment = center_al
                        elif ck in ("case_count", "unit_count", "last_count"):
                            c.number_format = "#,##0.##"; c.alignment = center_al
                        elif ci > 2: c.alignment = center_al
                        else: c.alignment = left_al

                    ws.row_dimensions[row].height = 13
                    item_idx += 1
                row += 1

            ws.freeze_panes = "A4"
            ws.page_setup.orientation = ("landscape" if orient == "landscape" else "portrait")
            ws.page_setup.paperSize   = ws.PAPERSIZE_LETTER
            ws.page_setup.fitToPage   = True
            ws.page_setup.fitToWidth  = 1
            ws.page_setup.fitToHeight = 0
            ws.print_title_rows       = "1:3"
            ws.sheet_properties.pageSetUpPr.fitToPage = True

            if qr_img_buf:
                try:
                    qr_img_buf.seek(0)
                    img = XLImage(io.BytesIO(qr_img_buf.read()))
                    img.width = 72; img.height = 72
                    qr_col = get_column_letter(n_cols + 1)
                    ws.column_dimensions[qr_col].width = 11
                    ws.add_image(img, f"{qr_col}1")
                except Exception:
                    pass

        return wb

    # ══════════════════════════════════════════════════════════════════════════

    def _render_enter(self) -> None:
        st.caption(
            "Layout matches your printed sheet. "
            "Use Tab to advance between cells. "
            "Counts auto-save to session as you enter them."
        )

        # ── Config summary + override ─────────────────────────────────────────
        cfg = st.session_state.get("ce_config", {})
        with st.expander(
            f"Sheet config: {len(cfg.get('cols', []))} cols · "
            f"{cfg.get('sort','gl_desc')} · "
            f"{cfg.get('orient','portrait')} "
            "— click to change",
            expanded=False,
        ):
            sort_label = st.selectbox(
                "Sort order", list(SORT_OPTIONS.keys()),
                index=list(SORT_OPTIONS.values()).index(cfg.get("sort","gl_desc")),
                key="en_sort",
            )
            cfg["sort"] = SORT_OPTIONS[sort_label]
            all_labels = [COL_LABELS[k] for k in COL_KEYS]
            sel_labels = st.multiselect(
                "Columns", all_labels,
                default=[COL_LABELS[k] for k in cfg.get("cols", _default_cols())],
                key="en_cols",
            )
            cfg["cols"] = [k for k in COL_KEYS if COL_LABELS[k] in sel_labels] or _default_cols()
            st.session_state["ce_config"] = cfg

        sort_key  = cfg.get("sort", "gl_desc")
        col_keys  = cfg.get("cols", _default_cols())

        # ── Stand selector ────────────────────────────────────────────────────
        current_cc = None
        try:
            from app import get_current_database
            current_cc = get_current_database()
        except Exception:
            current_cc = "57231"

        all_stands   = self.db.get_stands(cost_center=current_cc)
        enter_stand_id   = None
        enter_stand_name = None

        if all_stands:
            stand_opts = {"— All items (no stand filter) —": None}
            stand_opts.update({s["stand_name"]: s["stand_id"] for s in all_stands})
            sel_stand = st.selectbox(
                "Stand", list(stand_opts.keys()), key="en_stand",
            )
            enter_stand_id   = stand_opts[sel_stand]
            enter_stand_name = sel_stand if enter_stand_id else None

        # ── Session management ────────────────────────────────────────────────
        session_id = st.session_state.get("ce_session_id")

        hc1, hc2, hc3 = st.columns([2, 2, 1])
        count_date = hc1.date_input("Count Date", value=date.today(), key="en_date")
        placeholder = f"{enter_stand_name} — counter name, shift…" if enter_stand_name else "Stand, counter name, shift…"
        notes      = hc2.text_input("Notes", placeholder=placeholder,
                                    key="en_notes")

        if not session_id:
            if hc3.button("▶ Start Count", type="primary",
                          use_container_width=True, key="en_start"):
                session_id = self.db.create_count_session(
                    count_date=count_date,
                    created_by=_get_changed_by(),
                    notes=notes,
                )
                st.session_state["ce_session_id"] = session_id
                st.session_state["ce_counts"]     = {}
                st.rerun()
            st.info("Start a count session, or load counts from the Scan tab.")
            return

        session = self.db.get_count_session(session_id)
        if not session:
            st.warning("Session not found.")
            st.session_state["ce_session_id"] = None
            st.rerun()
            return

        if session["status"] == "committed":
            st.success(
                f"✅ Committed {str(session.get('committed_at',''))[:16]} "
                f"· {session.get('committed_by','')} "
                f"· Total: **${float(session.get('total_value',0)):,.2f}**"
            )
            if st.button("Start New Count", key="en_new_after"):
                st.session_state["ce_session_id"] = None
                st.session_state["ce_counts"]     = {}
                st.rerun()
            return

        st.caption(
            f"Session `{session_id[:8]}…` · "
            f"{str(session.get('count_date',''))[:10]} · "
            f"**{session['status']}**"
        )

        # ── Load items + build data-editor dataframe ──────────────────────────
        if enter_stand_id:
            items = self.db.get_stand_items(enter_stand_id) or []
            # Stand items are already in sort_order; only re-sort if user chose different order
            if sort_key != "gl_desc":
                items = _sort_items(items, sort_key)
        else:
            items = self.db.get_all_items("active") or []
            items = _sort_items(items, sort_key)

        if not items:
            st.warning("No items found for the selected stand/location.")
            return
        saved      = st.session_state.get("ce_counts", {})
        entry_cols = [k for k in col_keys if next(
            (c for c in COLUMNS if c["key"] == k and c["editable"]), None
        )]
        # Always include case_count + unit_count even if not in col_keys
        for ec in ("case_count", "unit_count"):
            if ec not in entry_cols:
                entry_cols.append(ec)

        # Build display dataframe
        display_rows = []
        for item in items:
            cost = float(item.get("cost") or 0)
            conv = float(item.get("conv_ratio") or 1)
            uc   = cost / conv if conv > 1 else cost
            key  = item["key"]
            prev = saved.get(key, {})

            row = {}
            for ck in col_keys:
                if   ck == "gl_code":    row["GL"]          = item.get("gl_code") or ""
                elif ck == "description":row["Description"]  = item.get("description") or ""
                elif ck == "pack_type":  row["Pack"]         = item.get("pack_type") or ""
                elif ck == "vendor":     row["Vendor"]       = item.get("vendor") or ""
                elif ck == "unit_cost":  row["Unit Cost"]    = round(uc, 4)
                elif ck == "last_count": row["Last Count"]   = float(item.get("quantity_on_hand") or 0)
                elif ck == "last_value": row["Last Value"]   = round(float(item.get("quantity_on_hand") or 0) * uc, 2)
                elif ck == "case_count": row["CASE"]         = float(prev.get("case", 0))
                elif ck == "unit_count": row["UNIT"]         = float(prev.get("unit", 0))
                elif ck == "notes":      row["Notes"]        = prev.get("notes", "")

            # Ensure CASE / UNIT always present
            if "CASE" not in row: row["CASE"] = float(prev.get("case", 0))
            if "UNIT" not in row: row["UNIT"] = float(prev.get("unit", 0))
            if "Notes" not in row: row["Notes"] = prev.get("notes", "")
            row["_key"] = key
            display_rows.append(row)

        df = pd.DataFrame(display_rows)
        id_col = "_key"

        # Define column config
        col_cfg = {}
        for col in df.columns:
            if col == id_col:
                col_cfg[col] = st.column_config.TextColumn(col, disabled=True)
            elif col in ("CASE", "UNIT"):
                col_cfg[col] = st.column_config.NumberColumn(col, min_value=0, step=1, format="%.2g")
            elif col == "Notes":
                col_cfg[col] = st.column_config.TextColumn(col)
            elif col == "Unit Cost":
                col_cfg[col] = st.column_config.NumberColumn(col, format="$%.4f", disabled=True)
            elif col in ("Last Count", "Last Value"):
                col_cfg[col] = st.column_config.NumberColumn(col, disabled=True)
            else:
                col_cfg[col] = st.column_config.TextColumn(col, disabled=True)

        st.markdown("**Enter counts below — Tab between cells · Enter to confirm row**")
        edited = st.data_editor(
            df.drop(columns=[id_col]),
            use_container_width=True,
            hide_index=True,
            height=560,
            column_config=col_cfg,
            num_rows="fixed",
            key="en_editor",
        )

        # Sync edits back to session state
        counts = {}
        all_lines = []
        total_value = 0.0

        for i, row in edited.iterrows():
            orig      = display_rows[i]
            key       = orig["_key"]
            case_qty  = float(row.get("CASE") or 0)
            unit_qty  = float(row.get("UNIT") or 0)
            notes_val = str(row.get("Notes") or "")

            # Find unit_cost from original data
            uc = 0.0
            for item in items:
                if item["key"] == key:
                    cost = float(item.get("cost") or 0)
                    conv = float(item.get("conv_ratio") or 1)
                    uc   = cost / conv if conv > 1 else cost
                    break

            # Total quantity = case + unit (both in same UOM)
            total_qty = case_qty + unit_qty
            ext       = total_qty * uc
            total_value += ext

            counts[key] = {"case": case_qty, "unit": unit_qty, "notes": notes_val}
            if total_qty > 0:
                all_lines.append({
                    "item_key":         key,
                    "description":      orig.get("Description", ""),
                    "pack_type":        orig.get("Pack", ""),
                    "gl_code":          orig.get("GL", ""),
                    "gl_name":          "",
                    "unit_cost":        uc,
                    "quantity_counted": total_qty,
                    "extended_value":   round(ext, 4),
                    "notes":            notes_val,
                })

        st.session_state["ce_counts"] = counts

        # ── Metrics + action buttons ───────────────────────────────────────────
        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        sheet_label = enter_stand_name or "All Items"
        m1.metric("Items Counted",      sum(1 for v in counts.values()
                                            if v.get("case",0)+v.get("unit",0) > 0))
        m2.metric("Total Count Value",  fmt_currency(total_value))
        m3.metric(f"Items — {sheet_label}", len(items))

        b1, b2, b3 = st.columns(3)
        if b1.button("💾 Save Progress", use_container_width=True, key="en_save"):
            self.db.save_count_lines(session_id, all_lines)
            st.success(f"Saved {len(all_lines)} counted lines.")

        confirm = b2.checkbox(
            f"Confirm commit — ${total_value:,.2f}",
            key="en_confirm",
        )
        if b3.button("✅ Commit Count", type="primary",
                     disabled=not confirm, use_container_width=True, key="en_commit"):
            self.db.save_count_lines(session_id, all_lines)
            result = self.db.commit_count_session(session_id, committed_by=_get_changed_by())
            if result["errors"]:
                st.warning(f"Committed {result['updated']} items, {len(result['errors'])} error(s).")
            else:
                st.success(f"✅ Count committed — {result['updated']} items updated.")
            st.rerun()

        with st.expander("⚠️ Abandon this session"):
            if st.button("🗑️ Void Count Session", key="en_void"):
                st.session_state["ce_session_id"] = None
                st.session_state["ce_counts"]     = {}
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — SCAN COUNT SHEETS
    # ══════════════════════════════════════════════════════════════════════════

    def _render_scan(self) -> None:
        st.markdown("#### Upload a Filled Count Sheet")
        st.caption(
            "Upload the Excel count sheet after counts have been entered. "
            "If the sheet has a QR code (generated by the Print tab), "
            "the column configuration will be restored automatically."
        )

        uploaded = st.file_uploader(
            "Drop count sheet here or click to browse",
            type=["xlsx", "xls", "png", "jpg", "jpeg", "pdf"],
            key="scan_upload",
        )

        if not uploaded:
            st.info("Upload an Excel file (.xlsx) from the Print tab, or an image/scan of a printed sheet.")
            return

        fname = uploaded.name.lower()

        if fname.endswith((".xlsx", ".xls")):
            self._parse_excel_sheet(uploaded)
        elif fname.endswith((".png", ".jpg", ".jpeg", ".pdf")):
            self._parse_image_scan(uploaded)
        else:
            st.error("Unsupported file type.")

    def _parse_excel_sheet(self, uploaded) -> None:
        """Parse a filled-in Excel count sheet."""
        try:
            from openpyxl import load_workbook
        except ImportError:
            st.error("openpyxl required.")
            return

        try:
            wb = load_workbook(io.BytesIO(uploaded.read()), data_only=True)
        except Exception as e:
            st.error(f"Could not read Excel file: {e}")
            return

        sheet_names = wb.sheetnames
        sel_sheet = st.selectbox("Sheet to import", sheet_names, key="scan_sheet_sel")
        ws = wb[sel_sheet]

        # Find header row (row 3) and detect CASE / UNIT columns
        header_row = [
            (ws.cell(3, c).value or "") for c in range(1, ws.max_column + 1)
        ]

        case_col = next((i+1 for i, h in enumerate(header_row)
                         if str(h).upper() in ("CASE", "CASE COUNT")), None)
        unit_col = next((i+1 for i, h in enumerate(header_row)
                         if str(h).upper() in ("UNIT", "UNIT COUNT")), None)
        desc_col = next((i+1 for i, h in enumerate(header_row)
                         if str(h).upper() in ("DESCRIPTION", "ITEM", "ITEM DESCRIPTION")), 2)

        if not case_col and not unit_col:
            # Try generic count column
            count_col = next((i+1 for i, h in enumerate(header_row)
                              if str(h).upper() in ("COUNT", "QTY", "QUANTITY")), None)
            if not count_col:
                st.warning("Could not find CASE, UNIT, or COUNT column in row 3. "
                           "Make sure the sheet was generated by the Print tab.")
                st.write("Headers found:", header_row)
                return
            case_col = count_col

        # Parse counts from data rows (row 4+)
        parsed = []
        for r in range(4, ws.max_row + 1):
            desc = ws.cell(r, desc_col).value
            if not desc or str(desc).strip() == "":
                continue
            # Skip GL group header rows (merged / colored — value in col 1 only)
            if ws.cell(r, 1).value and not ws.cell(r, desc_col).value:
                continue

            case_qty = float(ws.cell(r, case_col).value or 0) if case_col else 0.0
            unit_qty = float(ws.cell(r, unit_col).value or 0) if unit_col else 0.0
            if case_qty == 0 and unit_qty == 0:
                continue
            parsed.append({
                "Description": str(desc).strip(),
                "CASE":  case_qty,
                "UNIT":  unit_qty,
                "Total": case_qty + unit_qty,
            })

        if not parsed:
            st.info("No non-zero counts found in the sheet.")
            return

        st.success(f"Found **{len(parsed)}** counted items.")
        preview_df = pd.DataFrame(parsed)
        st.dataframe(preview_df, use_container_width=True, hide_index=True, height=300)

        st.markdown("---")
        st.markdown("**Load these counts into a count session:**")

        hc1, hc2 = st.columns(2)
        count_date = hc1.date_input("Count Date", value=date.today(), key="scan_date")
        notes      = hc2.text_input("Notes", value=f"Scanned: {uploaded.name}", key="scan_notes")

        if st.button("▶ Load into Count Session", type="primary", key="scan_load"):
            # Match descriptions to DB items
            all_items = {
                item["key"]: item
                for item in (self.db.get_all_items("active") or [])
            }
            desc_map = {
                (item.get("description") or "").upper(): key
                for key, item in all_items.items()
            }

            counts = {}
            matched, unmatched = 0, []
            for row in parsed:
                lookup = row["Description"].upper()
                item_key = desc_map.get(lookup)
                if item_key:
                    counts[item_key] = {
                        "case":  row["CASE"],
                        "unit":  row["UNIT"],
                        "notes": "",
                    }
                    matched += 1
                else:
                    unmatched.append(row["Description"])

            # Create session and store counts
            session_id = self.db.create_count_session(
                count_date=count_date,
                created_by=_get_changed_by(),
                notes=notes,
            )
            st.session_state["ce_session_id"] = session_id
            st.session_state["ce_counts"]     = counts

            st.success(
                f"✅ Session created — {matched} items matched. "
                + (f"{len(unmatched)} unmatched." if unmatched else "")
            )
            if unmatched:
                with st.expander(f"⚠️ {len(unmatched)} unmatched items"):
                    for u in unmatched[:20]:
                        st.caption(f"• {u}")
            st.info("Switch to the **Enter Manual Counts** tab to review and commit.")

    def _parse_image_scan(self, uploaded) -> None:
        """Try QR decode from image; show manual entry with restored config."""
        st.markdown("**Image / Scan uploaded**")

        # Try to display preview
        try:
            st.image(uploaded, caption=uploaded.name, use_container_width=True)
        except Exception:
            pass

        # Try QR decode
        config_restored = {}
        try:
            from pyzbar.pyzbar import decode as pyzbar_decode
            from PIL import Image as PILImage
            uploaded.seek(0)
            img = PILImage.open(uploaded)
            codes = pyzbar_decode(img)
            for code in codes:
                data = code.data.decode("utf-8")
                config_restored = _decode_config(data)
                if config_restored:
                    break
        except ImportError:
            pass
        except Exception:
            pass

        if config_restored:
            st.success(
                f"✅ QR code detected — restoring config: "
                f"{len(config_restored.get('cols',[]))} columns · "
                f"{config_restored.get('sort','?')} sort · "
                f"{config_restored.get('orient','?')}"
            )
            st.session_state["ce_config"] = config_restored
        else:
            st.info(
                "No QR code detected (or `pyzbar` not installed). "
                "Switch to **Enter Manual Counts** and key in counts manually. "
                "The current sheet config will be used."
            )

        st.markdown("→ Switch to **✏️ Enter Manual Counts** to proceed.")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4 — SESSION HISTORY
    # ══════════════════════════════════════════════════════════════════════════

    def _render_history(self) -> None:
        st.subheader("Count Session History")
        sessions = self.db.get_recent_count_sessions(limit=30)
        if not sessions:
            st.info("No count sessions yet.")
            return

        st.dataframe(
            pd.DataFrame([{
                "Date":   str(s.get("count_date", ""))[:10],
                "Status": s["status"],
                "Items":  s.get("item_count", 0),
                "Value":  fmt_currency(s.get("total_value") or 0),
                "By":     s.get("created_by", ""),
                "Notes":  (s.get("notes") or "")[:40],
                "ID":     s["session_id"][:8] + "…",
            } for s in sessions]),
            use_container_width=True, hide_index=True,
        )

        sel = st.selectbox(
            "View session detail",
            [s["session_id"] for s in sessions],
            format_func=lambda sid: next(
                f"{str(s.get('count_date',''))[:10]} — {s['status']} — "
                f"{fmt_currency(s.get('total_value') or 0)}"
                for s in sessions if s["session_id"] == sid
            ),
            key="hist_sel",
        )

        if sel:
            lines = self.db.get_count_lines(sel)
            if lines:
                st.dataframe(
                    pd.DataFrame([{
                        "GL":   l.get("gl_code", ""),
                        "Item": l["description"],
                        "Pack": l.get("pack_type", ""),
                        "$/ea": fmt_currency(l.get("unit_cost") or 0),
                        "Qty":  fmt_num(l.get("quantity_counted") or 0),
                        "Value":fmt_currency(l.get("extended_value") or 0),
                    } for l in lines]),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("No lines saved for this session.")

        # Resume open sessions
        open_sessions = [s for s in sessions if s["status"] == "open"]
        if open_sessions:
            st.markdown("---")
            st.caption(f"{len(open_sessions)} open session(s)")
            resume_id = st.selectbox(
                "Resume a saved session",
                [s["session_id"] for s in open_sessions],
                format_func=lambda sid: next(
                    f"{str(s.get('count_date',''))[:10]} — "
                    f"{s.get('item_count',0)} items"
                    for s in open_sessions if s["session_id"] == sid
                ),
                key="hist_resume_sel",
            )
            if st.button("▶ Resume Session", key="hist_resume_btn"):
                lines = self.db.get_count_lines(resume_id)
                counts = {}
                for l in lines:
                    qty = float(l.get("quantity_counted") or 0)
                    counts[l["item_key"]] = {"case": qty, "unit": 0, "notes": l.get("notes","") or ""}
                st.session_state["ce_session_id"] = resume_id
                st.session_state["ce_counts"]     = counts
                st.rerun()

# ── end of CountEntryDashboard v2.0.0 ────────────────────────────────────────
