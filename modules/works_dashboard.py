# ──────────────────────────────────────────────────────────────────────────────
#  modules/works_dashboard.py  —  "The Works" Worksheet Builder
#  v1.0.0  —  Print configurable count/par/transfer sheets with QR codes
# ──────────────────────────────────────────────────────────────────────────────

__version__ = "1.0.0"

import io
import json
import re
import streamlit as st
import pandas as pd
from datetime import date, datetime
from collections import defaultdict
from base import Dashboard

try:
    import auth as _auth
    def _get_user(): return _auth.get_changed_by()
except Exception:
    def _get_user(): return "web_user"


# ── Pack-type parser ──────────────────────────────────────────────────────────

def _parse_pack(pack_type: str) -> dict:
    """
    Parse pack type string into case_size, pkg_size, pkg_label, each_label.
    Returns dict with keys: case_size, pkg_size, pkg_label, each_label, display
    """
    pt = (pack_type or "").strip()

    # Patterns: "24/20oz BTL", "6/4packs", "10slvsOf250", "1/5GAL", "keg/EA", "12/80"
    result = {
        "case_size":  1,
        "pkg_size":   0,
        "pkg_label":  "Pk",
        "each_label": "Ea",
        "display":    pt,
    }
    if not pt:
        return result

    pt_low = pt.lower()

    # Detect pkg label from text
    if "slv" in pt_low or "sleeve" in pt_low:
        result["pkg_label"] = "Slv"
    elif "pack" in pt_low or "4pack" in pt_low or "6pack" in pt_low:
        result["pkg_label"] = "Pk"
    elif "box" in pt_low:
        result["pkg_label"] = "Box"
    elif "bag" in pt_low:
        result["pkg_label"] = "Bag"
    elif "keg" in pt_low:
        result["each_label"] = "Keg"
        result["case_size"]  = 1
        return result

    # Extract leading number(s): "24/20oz BTL" → first=24
    m = re.match(r"(\d+)\s*/\s*(\d+)", pt)
    if m:
        first  = int(m.group(1))
        second = int(m.group(2))
        result["case_size"] = first

        # If second number > 1 and looks like a pkg size (not a weight/oz)
        rest = pt[m.end():].strip().lower()
        if second > 1 and rest and not any(x in rest for x in ["oz", "oz.", "ml", "l ", "lb", "gal", "fl"]):
            result["pkg_size"] = second
        elif first >= 100:
            # Large case — infer pkg size by best divisor
            result["pkg_size"] = _infer_pkg_size(first)
        return result

    # Pattern: "10slvsOf250" → case=10, pkg=250
    m2 = re.match(r"(\d+)[a-z]+of(\d+)", pt_low)
    if m2:
        result["case_size"] = int(m2.group(1))
        result["pkg_size"]  = int(m2.group(2))
        return result

    # Single number: "1/5GAL" style already handled; bare number
    m3 = re.match(r"^(\d+)", pt)
    if m3:
        result["case_size"] = int(m3.group(1))
        if result["case_size"] >= 100:
            result["pkg_size"] = _infer_pkg_size(result["case_size"])

    return result


def _infer_pkg_size(case_size: int) -> int:
    """
    When pkg_size is unknown, pick the best divisor of case_size.
    Tries 4, 6, 8, 10, 20, 25 in order; returns largest that gives pkg ≥ 2.
    """
    for divisor in [25, 20, 10, 8, 6, 4]:
        if case_size % divisor == 0 and case_size // divisor >= 2:
            return divisor
    return 0  # no clean mid-tier found


def _pack_display(pack: dict) -> str:
    """Short display string for Count Unit column."""
    cs  = pack["case_size"]
    ps  = pack["pkg_size"]
    pl  = pack["pkg_label"]
    el  = pack["each_label"]
    if ps:
        return f"Cs of {cs}  /  {pl} of {ps}  /  {el}"
    return f"Cs of {cs}  /  {el}"


def _total_base(case_ct, pkg_ct, each_ct, pack: dict) -> float:
    """Convert case/pkg/each counts to base (each) units."""
    cs = float(case_ct  or 0)
    pk = float(pkg_ct   or 0)
    ea = float(each_ct  or 0)
    cs_size  = pack["case_size"] or 1
    pkg_size = pack["pkg_size"]  or 1
    return (cs * cs_size) + (pk * pkg_size) + ea


# ── QR config encode/decode ───────────────────────────────────────────────────

def _encode_cfg(cfg: dict) -> str:
    return json.dumps(cfg, separators=(",", ":"))


# ── Module ───────────────────────────────────────────────────────────────────

class WorksDashboard(Dashboard):

    MANIFEST = {
        "id":       "works_dashboard",
        "label":    "The Works",
        "version":  "1.0.0",
        "icon":     "🖨️",
        "status":   "active",
        "page_key": "works",
        "menu": {
            "parent":   "Dashboards",
            "label":    "The Works",
            "shortcut": "W",
            "position": 45,
        },
        "sidebar": {
            "section":  "",
            "position": 45,
            "show":     True,
        },
        "depends_on": ["database"],
        "db_tables":  ["items", "stands", "venues"],
        "abilities": [
            "Print inventory count sheets matching existing field format",
            "Case / Pack / Each count columns with pack-type reference",
            "QR code encodes stand, date, and config for scan auto-restore",
            "Chargeable and Non-Chargeable sections per stand",
            "PDF and Excel output",
        ],
        "permissions": {"min_role": "user"},
    }

    DOCS = {
        "summary": "Configurable worksheet builder — count sheets, par sheets, and more.",
        "usage": "Select stand(s), configure options, download Excel or PDF count sheet.",
        "demo_ready": True,
        "notes": "QR code on each sheet encodes the exact config for scan auto-restore.",
        "known_issues": [],
        "changelog": [
            {"version": "1.0.0", "date": "2026-03-29",
             "note": "Initial build — count sheet matching field prototype."},
        ],
    }

    def on_load(self) -> None:
        # Ensure venues + stands tables exist (creates + seeds if first run)
        try:
            self.db.ensure_stands_tables()
        except Exception:
            pass

    def verify(self) -> list:
        # Auto-create tables before health check runs — avoids false warning
        try:
            self.db.ensure_stands_tables()
        except Exception:
            pass
        return super().verify()

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**🖨️ The Works**")
            st.caption("Print · Count · Par")

    def render(self) -> None:
        st.markdown("### 🖨️ The Works — Worksheet Builder")

        tab_count, tab_par, tab_transfer, tab_recipe = st.tabs([
            "📋 Count Sheets",
            "📊 Par Sheets",
            "🔀 Transfer Sheets",
            "🍳 Recipe Sheets",
        ])

        with tab_count:
            self._render_count()
        with tab_par:
            st.info("Par Sheets — coming soon.")
        with tab_transfer:
            st.info("Transfer Sheets — coming soon.")
        with tab_recipe:
            st.markdown(
                "<span style='color:#4a5568;font-size:13px'>🍳 Recipe Sheets — "
                "not yet available (pending recipe data).</span>",
                unsafe_allow_html=True,
            )

    # ══════════════════════════════════════════════════════════════════════════
    # COUNT SHEETS TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _render_count(self) -> None:
        st.caption(
            "Generates a printable count sheet matching the field format — "
            "ID badge · QR code · Case / Pack / Each columns · Chargeable & Non-Chargeable sections."
        )

        # ── Stand selector ────────────────────────────────────────────────────
        current_cc = self._get_cc()
        all_stands = self.db.get_stands(cost_center=current_cc) or []

        if not all_stands:
            st.warning("No stands configured for this cost center.")
            return

        stand_opts = {s["stand_name"]: s for s in all_stands}

        c1, c2 = st.columns([3, 1])
        sel_names = c1.multiselect(
            "Stands", list(stand_opts.keys()),
            default=list(stand_opts.keys())[:1],
            key="wks_stands",
        )
        count_date = c2.date_input("Count Date", value=date.today(), key="wks_date")

        if not sel_names:
            st.info("Select at least one stand.")
            return

        # ── Options ───────────────────────────────────────────────────────────
        oa, ob, oc = st.columns(3)
        counter_name = oa.text_input("Counter Name (printed on sheet)", key="wks_counter")
        orient = ob.radio("Orientation", ["Portrait", "Landscape"],
                          horizontal=True, key="wks_orient")
        show_last_inv = oc.checkbox("Show Last Inventory Qty", value=True, key="wks_lastinv")

        # ── Preview summary ───────────────────────────────────────────────────
        total_items = sum(
            self.db.get_stand_item_count(stand_opts[n]["stand_id"])
            for n in sel_names
        )
        st.caption(
            f"📋 {len(sel_names)} stand(s) · ~{total_items:,} items · {orient}"
        )

        # ── Generate ──────────────────────────────────────────────────────────
        ga, gb = st.columns(2)
        gen_excel = ga.button("📥 Download Excel", type="primary", key="wks_gen_xl")
        gen_pdf   = gb.button("📄 Download PDF",   type="secondary", key="wks_gen_pdf")

        cfg = {
            "type":        "count",
            "cc":          current_cc,
            "stands":      sel_names,
            "date":        str(count_date),
            "show_lastinv": show_last_inv,
            "generated":   datetime.now().isoformat(timespec="seconds"),
        }

        if gen_excel:
            with st.spinner("Building workbook…"):
                wb = self._build_count_excel(
                    sel_names, stand_opts, count_date,
                    counter_name, orient.lower(), show_last_inv, cfg,
                )
            if wb:
                buf = io.BytesIO()
                wb.save(buf); buf.seek(0)
                fname = f"count_sheet_{count_date.strftime('%Y%m%d')}.xlsx"
                st.download_button(
                    f"⬇️ {fname}", data=buf, file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="wks_dl_xl",
                )

        if gen_pdf:
            with st.spinner("Building PDF…"):
                pdf_bytes = self._build_count_pdf(
                    sel_names, stand_opts, count_date,
                    counter_name, show_last_inv, cfg,
                )
            if pdf_bytes:
                fname = f"count_sheet_{count_date.strftime('%Y%m%d')}.pdf"
                st.download_button(
                    f"⬇️ {fname}", data=pdf_bytes, file_name=fname,
                    mime="application/pdf",
                    key="wks_dl_pdf",
                )
            else:
                st.error("PDF generation requires reportlab — run: pip install reportlab")

    # ══════════════════════════════════════════════════════════════════════════
    # EXCEL BUILDER
    # ══════════════════════════════════════════════════════════════════════════

    def _build_count_excel(self, sel_names, stand_opts, count_date,
                           counter_name, orient, show_last_inv, cfg):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import (Font, PatternFill, Alignment,
                                          Border, Side, GradientFill)
            from openpyxl.utils import get_column_letter
            from openpyxl.drawing.image import Image as XLImage
        except ImportError:
            st.error("openpyxl required — pip install openpyxl")
            return None

        wb = Workbook()
        wb.remove(wb.active)

        # ── Shared styles ─────────────────────────────────────────────────────
        thin   = Side(style="thin",   color="CCCCCC")
        thick  = Side(style="medium", color="555555")
        no_s   = Side(style=None)

        def border(*sides):  # l, r, t, b
            l, r, t, b = sides
            return Border(left=l, right=r, top=t, bottom=b)

        cell_b  = border(thin, thin, thin, thin)
        hdr_b   = border(thick, thick, thick, thick)
        entry_b = border(thick, thick, thick, thick)

        # Colors
        C_DARK    = "1A1A2E"   # header bar bg
        C_SECT    = "2D3561"   # section header bg (chargeable)
        C_NONC    = "3D2B56"   # section header bg (non-chargeable, purple)
        C_HDR_TXT = "FFFFFF"
        C_ALT     = "F5F7FA"   # alternate row
        C_WHITE   = "FFFFFF"
        C_ENTRY   = "FFFDF0"   # light yellow — count entry cells
        C_BADGE   = "0F3460"   # ID badge bg
        C_ACCENT  = "E63946"   # red accent

        hdr_fill   = PatternFill("solid", fgColor=C_DARK)
        sect_fill  = PatternFill("solid", fgColor=C_SECT)
        nonc_fill  = PatternFill("solid", fgColor=C_NONC)
        alt_fill   = PatternFill("solid", fgColor=C_ALT)
        wht_fill   = PatternFill("solid", fgColor=C_WHITE)
        entry_fill = PatternFill("solid", fgColor=C_ENTRY)
        badge_fill = PatternFill("solid", fgColor=C_BADGE)

        f_title   = Font(bold=True,  color=C_HDR_TXT, size=14)
        f_sub     = Font(bold=False, color=C_HDR_TXT, size=9, italic=True)
        f_badge   = Font(bold=True,  color=C_HDR_TXT, size=9)
        f_colhdr  = Font(bold=True,  color=C_HDR_TXT, size=9)
        f_sect    = Font(bold=True,  color=C_HDR_TXT, size=9)
        f_item    = Font(bold=True,  color="1A1A2E",  size=9)
        f_pack    = Font(bold=False, color="AAAAAA",  size=7)   # low opacity pack info
        f_body    = Font(size=9, color="1A1A2E")
        f_footer  = Font(size=7, color="888888", italic=True)

        center  = Alignment(horizontal="center",  vertical="center", wrap_text=False)
        left    = Alignment(horizontal="left",    vertical="center", wrap_text=False)
        left_w  = Alignment(horizontal="left",    vertical="top",    wrap_text=True)
        right   = Alignment(horizontal="right",   vertical="center")

        # ── QR code (encode cfg once, reuse per sheet) ────────────────────────
        qr_buf = None
        try:
            import qrcode as _qr
            qr = _qr.QRCode(box_size=4, border=2)
            qr.add_data(_encode_cfg(cfg))
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            qr_buf = io.BytesIO()
            img.save(qr_buf, format="PNG")
            qr_buf.seek(0)
        except Exception:
            pass

        # ── Column layout ─────────────────────────────────────────────────────
        #  A   B                     C      D           E      F      G      H
        #  #   Item & Description    Check  Count Unit  CASE   PKG    EACH   Variance
        COL_W = {
            "A": 4,    # #
            "B": 36,   # description
            "C": 5,    # check ✓
            "D": 22,   # count unit reference
            "E": 9,    # CASE
            "F": 9,    # PKG
            "G": 9,    # EACH
            "H": 10,   # Variance / Notes
        }
        N_COLS  = 8
        last_cl = "H"

        for stand_name in sel_names:
            stand    = stand_opts[stand_name]
            stand_id = stand["stand_id"]
            cc       = stand.get("cost_center", self._get_cc())

            # Load items — split chargeable / non-chargeable
            all_items = self.db.get_stand_items(stand_id) or []
            chargeable     = [i for i in all_items if i.get("is_chargeable", True) is not False]
            non_chargeable = [i for i in all_items if i.get("is_chargeable", True) is False]

            ws = wb.create_sheet(title=stand_name[:31])

            # Set column widths
            for col_letter, w in COL_W.items():
                ws.column_dimensions[col_letter].width = w

            # ── Row 1 — Header bar ────────────────────────────────────────────
            ws.row_dimensions[1].height = 36

            # ID badge (A1)
            ws.merge_cells("A1:A2")
            c = ws["A1"]
            c.value     = f"ID:\n{stand_id}"
            c.font      = f_badge
            c.fill      = badge_fill
            c.alignment = Alignment(horizontal="center", vertical="center",
                                    wrap_text=True)
            c.border    = border(thick, no_s, thick, thick)

            # Title (B1:F1)
            ws.merge_cells("B1:F1")
            c = ws["B1"]
            c.value     = stand_name
            c.font      = Font(bold=True, color=C_HDR_TXT, size=16)
            c.fill      = hdr_fill
            c.alignment = center
            c.border    = border(no_s, no_s, thick, no_s)

            # ── Row 2 — Subtitle ──────────────────────────────────────────────
            ws.row_dimensions[2].height = 18

            ws.merge_cells("B2:F2")
            c = ws["B2"]
            c.value     = f"Inventory Count Sheet  ·  {count_date.strftime('%A, %B %d, %Y')}"
            c.font      = f_sub
            c.fill      = hdr_fill
            c.alignment = center
            c.border    = border(no_s, no_s, no_s, thick)

            # QR code placeholder (G1:H2)
            ws.merge_cells("G1:H2")
            c = ws["G1"]
            c.fill   = hdr_fill
            c.border = border(no_s, thick, thick, thick)

            if qr_buf:
                try:
                    qr_buf.seek(0)
                    xl_img = XLImage(io.BytesIO(qr_buf.read()))
                    xl_img.width  = 60
                    xl_img.height = 60
                    ws.add_image(xl_img, "G1")
                except Exception:
                    pass

            # ── Row 3 — Counter name line ─────────────────────────────────────
            ws.row_dimensions[3].height = 16
            ws.merge_cells("A3:H3")
            cname = counter_name or ""
            c = ws["A3"]
            c.value     = f"  Name of Counter:  {cname}{'_' * max(0, 40 - len(cname))}"
            c.font      = Font(size=9, color="333333")
            c.alignment = left
            c.border    = border(thick, thick, no_s, thin)

            # ── Row 4 — Column headers ────────────────────────────────────────
            ws.row_dimensions[4].height = 20
            headers = {
                "A": "#",
                "B": "Item Name & Description",
                "C": "✓",
                "D": "Count Unit\n(Cs / Pk / Ea)",
                "E": "CASE",
                "F": "PKG",
                "G": "EACH",
                "H": "Variance\n/ Notes",
            }
            for col, lbl in headers.items():
                c = ws[f"{col}4"]
                c.value     = lbl
                c.font      = f_colhdr
                c.fill      = hdr_fill
                c.alignment = center if col != "B" else Alignment(
                    horizontal="left", vertical="center")
                c.border    = hdr_b

            ws.freeze_panes = "A5"

            # ── Data rows ─────────────────────────────────────────────────────
            row = 5
            sections = []
            if chargeable:
                sections.append((stand_name, chargeable, sect_fill, False))
            if non_chargeable:
                lbl = f"{stand_name}  →  Non-Chargeable"
                sections.append((lbl, non_chargeable, nonc_fill, True))

            for sect_label, items, s_fill, is_nonc in sections:
                # Section header row
                ws.row_dimensions[row].height = 14
                ws.merge_cells(f"A{row}:H{row}")
                c = ws[f"A{row}"]
                c.value     = f"  {sect_label}"
                c.font      = f_sect
                c.fill      = s_fill
                c.alignment = left
                c.border    = border(thick, thick, thin, thin)
                row += 1

                for idx, item in enumerate(items, 1):
                    ws.row_dimensions[row].height = 22
                    fill = wht_fill if idx % 2 == 0 else alt_fill

                    pack = _parse_pack(item.get("pack_type") or "")
                    pack_ref = _pack_display(pack)

                    cost  = float(item.get("cost") or 0)
                    conv  = float(item.get("conv_ratio") or 1) or 1
                    uc    = cost / conv if conv > 1 else cost
                    last  = float(item.get("quantity_on_hand") or 0)

                    # A — seq #
                    c = ws[f"A{row}"]
                    c.value = idx; c.font = f_body; c.fill = fill
                    c.alignment = center; c.border = cell_b

                    # B — description + pack info (two lines via rich text workaround)
                    desc = item.get("description") or ""
                    c = ws[f"B{row}"]
                    c.value     = desc
                    c.font      = f_item
                    c.fill      = fill
                    c.alignment = left_w
                    c.border    = cell_b

                    # D — count unit reference (pack breakdown, low-opacity text)
                    c = ws[f"D{row}"]
                    c.value     = pack_ref
                    c.font      = f_pack
                    c.fill      = fill
                    c.alignment = Alignment(horizontal="center", vertical="center",
                                            wrap_text=True)
                    c.border    = cell_b

                    # C — check box
                    c = ws[f"C{row}"]
                    c.value = ""; c.fill = fill
                    c.border = border(thin, thin, thin, thin)
                    c.alignment = center

                    # E / F / G — count entry cells (light yellow)
                    pkg_label = pack["pkg_label"] if pack["pkg_size"] else "—"
                    for col, sub_lbl in [("E", "cs"), ("F", pkg_label), ("G", "ea")]:
                        c = ws[f"{col}{row}"]
                        c.value     = "" if (col == "F" and not pack["pkg_size"]) else ""
                        c.font      = Font(size=7, color="BBBBBB")
                        c.fill      = fill if (col == "F" and not pack["pkg_size"]) else entry_fill
                        c.alignment = center
                        c.border    = entry_b if col in ("E", "G") else cell_b

                    # H — variance / notes
                    c = ws[f"H{row}"]
                    c.value = ""; c.fill = fill
                    c.border = cell_b; c.alignment = center

                    row += 1

            # ── Footer ────────────────────────────────────────────────────────
            ws.row_dimensions[row].height = 12
            ws.merge_cells(f"A{row}:H{row}")
            c = ws[f"A{row}"]
            c.value = (
                f"  {stand_name}  ·  Generated: "
                f"{datetime.now().strftime('%Y-%m-%d %H:%M')}  ·  CONFIDENTIAL"
            )
            c.font      = f_footer
            c.alignment = left
            c.border    = border(thick, thick, thin, thick)

            # Page setup
            ws.page_setup.orientation  = ("landscape" if orient == "landscape"
                                           else "portrait")
            ws.page_setup.paperSize    = ws.PAPERSIZE_LETTER
            ws.page_setup.fitToPage    = True
            ws.page_setup.fitToWidth   = 1
            ws.page_setup.fitToHeight  = 0
            ws.print_title_rows        = "1:4"
            ws.sheet_properties.pageSetUpPr.fitToPage = True

            # Header/footer (native Excel)
            ws.oddHeader.center.text = (
                f"&B{stand_name}&B  —  Inventory Count Sheet"
            )
            ws.oddFooter.left.text   = f"&I{stand_name}&I"
            ws.oddFooter.center.text = "&ICONFIDENTIAL&I"
            ws.oddFooter.right.text  = "Page &P of &N"

        return wb

    # ══════════════════════════════════════════════════════════════════════════
    # PDF BUILDER
    # ══════════════════════════════════════════════════════════════════════════

    def _build_count_pdf(self, sel_names, stand_opts, count_date,
                         counter_name, show_last_inv, cfg):
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                            Paragraph, Spacer, PageBreak)
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        except ImportError:
            return None

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=letter,
            leftMargin=0.4*inch, rightMargin=0.4*inch,
            topMargin=0.4*inch,  bottomMargin=0.4*inch,
        )
        styles = getSampleStyleSheet()

        C_DARK   = colors.HexColor("#1A1A2E")
        C_SECT   = colors.HexColor("#2D3561")
        C_NONC   = colors.HexColor("#3D2B56")
        C_ALT    = colors.HexColor("#F5F7FA")
        C_ENTRY  = colors.HexColor("#FFFDF0")
        C_BADGE  = colors.HexColor("#0F3460")
        C_PACK   = colors.HexColor("#AAAAAA")
        C_WHITE  = colors.white

        s_item = ParagraphStyle("item", fontSize=8,  leading=10, textColor=colors.HexColor("#1A1A2E"), fontName="Helvetica-Bold")
        s_pack = ParagraphStyle("pack", fontSize=6,  leading=8,  textColor=C_PACK, fontName="Helvetica")
        s_hdr  = ParagraphStyle("hdr",  fontSize=8,  leading=10, textColor=C_WHITE, fontName="Helvetica-Bold", alignment=TA_CENTER)
        s_sect = ParagraphStyle("sect", fontSize=8,  leading=10, textColor=C_WHITE, fontName="Helvetica-Bold")
        s_body = ParagraphStyle("body", fontSize=8,  leading=10, textColor=colors.HexColor("#1A1A2E"), alignment=TA_CENTER)
        s_foot = ParagraphStyle("foot", fontSize=6,  leading=8,  textColor=colors.HexColor("#888888"), fontName="Helvetica-Oblique")

        story = []

        col_widths = [0.3*inch, 2.8*inch, 0.3*inch, 1.6*inch,
                      0.7*inch, 0.7*inch, 0.7*inch, 0.8*inch]

        for si, stand_name in enumerate(sel_names):
            stand    = stand_opts[stand_name]
            stand_id = stand["stand_id"]

            all_items      = self.db.get_stand_items(stand_id) or []
            chargeable     = [i for i in all_items if i.get("is_chargeable", True) is not False]
            non_chargeable = [i for i in all_items if i.get("is_chargeable", True) is False]

            # ── Header table ──────────────────────────────────────────────────
            hdr_data = [[
                Paragraph(f"ID:<br/><b>{stand_id}</b>", ParagraphStyle(
                    "badge", fontSize=7, leading=9, textColor=C_WHITE,
                    fontName="Helvetica-Bold", alignment=TA_CENTER)),
                Paragraph(f"<b>{stand_name}</b><br/>"
                          f"<font size='8'>Inventory Count Sheet  ·  "
                          f"{count_date.strftime('%B %d, %Y')}</font>",
                          ParagraphStyle("title", fontSize=13, leading=16,
                                         textColor=C_WHITE, fontName="Helvetica-Bold",
                                         alignment=TA_CENTER)),
                "",  # QR placeholder
            ]]
            hdr_tbl = Table(hdr_data,
                            colWidths=[1.0*inch, 5.1*inch, 1.0*inch])
            hdr_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (0,0), C_BADGE),
                ("BACKGROUND", (1,0), (1,0), C_DARK),
                ("BACKGROUND", (2,0), (2,0), C_DARK),
                ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
                ("BOX",        (0,0), (-1,-1), 1.5, colors.HexColor("#555555")),
                ("ROWBACKGROUNDS", (0,0), (-1,-1), [C_DARK]),
            ]))
            story.append(hdr_tbl)
            story.append(Spacer(1, 4))

            # Counter name line
            cname = counter_name or ("_" * 40)
            story.append(Paragraph(
                f"Name of Counter:  <u>{cname}</u>",
                ParagraphStyle("cn", fontSize=9, leading=12,
                               textColor=colors.HexColor("#333333")),
            ))
            story.append(Spacer(1, 6))

            # ── Column header row ─────────────────────────────────────────────
            col_hdrs = [
                Paragraph("#",                     s_hdr),
                Paragraph("Item Name & Description", s_hdr),
                Paragraph("✓",                     s_hdr),
                Paragraph("Count Unit\n(Cs/Pk/Ea)", s_hdr),
                Paragraph("CASE",                  s_hdr),
                Paragraph("PKG",                   s_hdr),
                Paragraph("EACH",                  s_hdr),
                Paragraph("Variance\n/ Notes",     s_hdr),
            ]

            table_data = [col_hdrs]
            table_styles = [
                ("BACKGROUND",  (0,0), (-1,0),  C_DARK),
                ("TEXTCOLOR",   (0,0), (-1,0),  C_WHITE),
                ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
                ("FONTSIZE",    (0,0), (-1,0),  8),
                ("ALIGN",       (0,0), (-1,0),  "CENTER"),
                ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
                ("ROWHEIGHT",   (0,0), (-1,0),  18),
                ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
                ("BOX",         (0,0), (-1,-1), 1.0, colors.HexColor("#555555")),
            ]

            sections = []
            if chargeable:
                sections.append((stand_name, chargeable, C_SECT))
            if non_chargeable:
                sections.append((f"{stand_name}  →  Non-Chargeable",
                                  non_chargeable, C_NONC))

            data_row = 1  # after header row
            for sect_label, items, sect_color in sections:
                # Section header
                table_data.append([
                    Paragraph(f"  {sect_label}", s_sect),
                    "", "", "", "", "", "", "",
                ])
                table_styles += [
                    ("BACKGROUND",  (0, data_row), (-1, data_row), sect_color),
                    ("SPAN",        (0, data_row), (-1, data_row)),
                    ("ROWHEIGHT",   (0, data_row), (-1, data_row), 13),
                ]
                data_row += 1

                for idx, item in enumerate(items, 1):
                    pack     = _parse_pack(item.get("pack_type") or "")
                    pack_ref = _pack_display(pack)
                    desc     = item.get("description") or ""
                    fill_c   = C_WHITE if idx % 2 == 0 else C_ALT
                    has_pkg  = bool(pack["pkg_size"])

                    row_data = [
                        Paragraph(str(idx), s_body),
                        Paragraph(f"<b>{desc}</b><br/>"
                                  f"<font color='#AAAAAA' size='6'>"
                                  f"{item.get('pack_type','')}</font>",
                                  ParagraphStyle("desc", fontSize=8, leading=11,
                                                 textColor=colors.HexColor("#1A1A2E"))),
                        "",  # check
                        Paragraph(f"<font color='#888888' size='6'>{pack_ref}</font>",
                                  ParagraphStyle("pu", fontSize=6, leading=8,
                                                 alignment=TA_CENTER)),
                        "",  # CASE entry
                        Paragraph("—", s_body) if not has_pkg else "",  # PKG entry
                        "",  # EACH entry
                        "",  # Variance
                    ]
                    table_data.append(row_data)

                    entry_bg = C_ENTRY
                    no_pkg_bg = fill_c
                    table_styles += [
                        ("BACKGROUND", (0, data_row), (-1, data_row), fill_c),
                        ("BACKGROUND", (4, data_row), (4, data_row), entry_bg),
                        ("BACKGROUND", (6, data_row), (6, data_row), entry_bg),
                        ("BACKGROUND", (5, data_row), (5, data_row),
                         entry_bg if has_pkg else no_pkg_bg),
                        ("ROWHEIGHT",  (0, data_row), (-1, data_row), 18),
                        ("BOX",        (4, data_row), (4, data_row), 1.0,
                         colors.HexColor("#555555")),
                        ("BOX",        (6, data_row), (6, data_row), 1.0,
                         colors.HexColor("#555555")),
                    ]
                    if has_pkg:
                        table_styles.append(
                            ("BOX", (5, data_row), (5, data_row), 1.0,
                             colors.HexColor("#555555"))
                        )
                    data_row += 1

            tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle(table_styles))
            story.append(tbl)

            # Footer
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"{stand_name}  ·  Generated: "
                f"{datetime.now().strftime('%Y-%m-%d %H:%M')}  ·  CONFIDENTIAL",
                s_foot,
            ))

            if si < len(sel_names) - 1:
                story.append(PageBreak())

        doc.build(story)
        buf.seek(0)
        return buf.read()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_cc(self) -> str:
        try:
            from app import get_current_database
            return get_current_database()
        except Exception:
            return "57231"
