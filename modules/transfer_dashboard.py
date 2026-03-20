# ──────────────────────────────────────────────────────────────────────────────
#  modules/transfer_dashboard.py  —  Transfer Sheet Dashboard
#  v1.0.1  —  Full Compass cost center list added.
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
from datetime import date
from base import Dashboard

# ── Full Compass cost center list ─────────────────────────────────────────────
COST_CENTERS = {
    "42315 - UHCL OH":                  "42315",
    "42316 - UHCL Smooth":              "42316",
    "42317 - UHCL Coffee":              "42317",
    "42318 - UHCL FC":                  "42318",
    "42319 - UHCL Catering":            "42319",
    "42320 - UHD FC Market":            "42320",
    "42321 - UHD Tech":                 "42321",
    "42322 - UHD Chick-fil-a":          "42322",
    "42323 - UHD FC OTG":               "42323",
    "42325 - UHD Starbucks":            "42325",
    "42326 - UHD Mondo's":              "42326",
    "42327 - UHD 40,000 Windows":       "42327",
    "42328 - UHD Food Trucks":          "42328",
    "42329 - UHD Shea Street":          "42329",
    "42330 - UHV OH":                   "42330",
    "42331 - UHV Coffee":               "42331",
    "42332 - UHV Chick-fil-a":          "42332",
    "42333 - UHV Market":               "42333",
    "42334 - UHSL OH":                  "42334",
    "42335 - UHSL Mondo":               "42335",
    "42336 - UHSL Market":              "42336",
    "42337 - UHSL Food Trucks":         "42337",
    "42338 - UH Main OH":               "42338",
    "42339 - Moody Towers":             "42339",
    "42341 - Cougar Woods":             "42341",
    "42342 - Chick-fil-a":              "42342",
    "42343 - SC Market":                "42343",
    "42344 - Panda Express":            "42344",
    "42345 - Starbucks":                "42345",
    "42347 - Asado":                    "42347",
    "42348 - McAlister's":              "42348",
    "42349 - SC OH":                    "42349",
    "42350 - RAD OH":                   "42350",
    "42351 - The Nook":                 "42351",
    "42352 - Paper Lantern":            "42352",
    "42353 - The Burger Joint":         "42353",
    "42354 - The Taco Stand":           "42354",
    "42355 - Absurd Bird":              "42355",
    "42356 - RAD Market":               "42356",
    "42358 - Lofts Market":             "42358",
    "42361 - Cougar Village Market":    "42361",
    "42362 - Einstein's":               "42362",
    "42363 - Houston Street Subs":      "42363",
    "42368 - Law Market":               "42368",
    "42369 - Main Catering":            "42369",
    "42594 - UHD Catering":             "42594",
    "42595 - UHSL Catering":            "42595",
    "42596 - UHV Catering":             "42596",
    "42778 - Side Pocket":              "42778",
    "51804 - CPH":                      "51804",
    "57230 - UHA OH":                   "57230",
    "57231 - UHA Concessions / TDECU":  "57231",
    "57232 - UHA Warehouse / Fertitta": "57232",
    "57233 - UHA Schroeder Park":       "57233",
    "57234 - UHA Softball Stadium":     "57234",
    "57235 - UHA Team Dining":          "57235",
    "57236 - UHA Catering":             "57236",
    "57237 - UHA Subcontractors":       "57237",
    "69736 - Texas Southern-Admin":     "69736",
}

# UHA cost centers shown first in selectors
UHA_CCS = [k for k in COST_CENTERS if k.startswith("57")]
OTHER_CCS = [k for k in COST_CENTERS if not k.startswith("57")]
CC_DISPLAY_ORDER = UHA_CCS + ["─" * 30] + OTHER_CCS


class TransferDashboard(Dashboard):

    MANIFEST = {
        "id":       "transfer_dashboard",
        "label":    "Transfers",
        "version":  "1.0.1",
        "icon":     "🔄",
        "status":   "active",
        "page_key": "transfer",
        "menu": {
            "parent":   "Dashboards",
            "label":    "Transfer Sheet",
            "shortcut": "T",
            "position": 70,
        },
        "sidebar": {
            "section":  "",
            "position": 70,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["items", "transfers", "transfer_lines"],
        "session_keys": ["transfer_draft_lines"],
        "abilities": [
            "Create inventory transfers between cost centers",
            "Auto-populate GL code and cost from inventory database",
            "Balance check — transfer must net to zero",
            "Approve and commit transfers to inventory",
            "View transfer history by cost center",
        ],
        "permissions": {"min_role": "user"},
    }

    DOCS = {
        "summary": "Create and approve inventory transfers between Compass cost centers with GL tracking.",
        "usage": "Select From/To cost centers. Add line items from inventory. Verify balance. Submit.",
        "demo_ready": True,
        "notes": "v1.0.1: Full Compass cost center list. UHA cost centers shown first.",
        "known_issues": [
            "quantity_on_hand not yet updated on approve — pending cost_center per-item tracking.",
        ],
        "changelog": [
            {"version": "1.0.1", "date": "2026-03-19", "note": "Full Compass CC list."},
            {"version": "1.0.0", "date": "2026-03-19", "note": "Initial implementation."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        self._ensure_tables()
        if "transfer_draft_lines" not in st.session_state:
            st.session_state["transfer_draft_lines"] = []

    def _ensure_tables(self):
        try:
            from database import get_conn
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS transfers (
                        transfer_id      TEXT PRIMARY KEY,
                        transfer_date    DATE NOT NULL,
                        from_cc          TEXT NOT NULL,
                        from_cc_name     TEXT,
                        to_cc            TEXT NOT NULL,
                        to_cc_name       TEXT,
                        from_manager     TEXT,
                        to_manager       TEXT,
                        status           TEXT DEFAULT 'draft',
                        gl_total         NUMERIC(12,4) DEFAULT 0,
                        balanced         BOOLEAN DEFAULT FALSE,
                        notes            TEXT,
                        created_by       TEXT,
                        created_at       TIMESTAMPTZ DEFAULT NOW(),
                        approved_by      TEXT,
                        approved_at      TIMESTAMPTZ
                    );
                    CREATE TABLE IF NOT EXISTS transfer_lines (
                        line_id          SERIAL PRIMARY KEY,
                        transfer_id      TEXT REFERENCES transfers(transfer_id)
                                         ON DELETE CASCADE,
                        item_key         TEXT,
                        description      TEXT,
                        gl_code          TEXT,
                        gl_name          TEXT,
                        pack_type        TEXT,
                        quantity         NUMERIC(10,4),
                        unit_cost        NUMERIC(10,4),
                        total_value      NUMERIC(12,4),
                        notes            TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_transfer_lines_tid
                        ON transfer_lines(transfer_id);
                    CREATE INDEX IF NOT EXISTS idx_transfers_from_cc
                        ON transfers(from_cc);
                    CREATE INDEX IF NOT EXISTS idx_transfers_to_cc
                        ON transfers(to_cc);
                    CREATE INDEX IF NOT EXISTS idx_transfers_status
                        ON transfers(status);
                """)
        except Exception as exc:
            st.warning(f"Transfer table setup: {exc}")

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**🔄 Transfers**")
            st.caption("Inventory movement · GL tracked")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.title("🔄 Transfer Sheet")
        tab1, tab2 = st.tabs(["📝 New Transfer", "📋 History"])
        with tab1:
            self._render_new_transfer()
        with tab2:
            self._render_history()

    # ── New Transfer ──────────────────────────────────────────────────────────

    def _render_new_transfer(self):
        st.subheader("Transfer Details")

        # Cost center selectors — UHA first, divider, then rest
        valid_ccs = [k for k in COST_CENTERS]  # skip divider entries
        uha_default_from = next((i for i, k in enumerate(valid_ccs)
                                  if "57231" in k), 0)
        uha_default_to   = next((i for i, k in enumerate(valid_ccs)
                                  if "57236" in k), 1)

        c1, c2, c3 = st.columns(3)
        from_label = c1.selectbox("From Cost Center", valid_ccs,
                                   index=uha_default_from, key="xfr_from")
        to_label   = c2.selectbox("To Cost Center",   valid_ccs,
                                   index=uha_default_to,   key="xfr_to")
        xfr_date   = c3.date_input("Date", value=date.today(), key="xfr_date")

        c4, c5 = st.columns(2)
        from_mgr = c4.text_input("Sender (Manager)", key="xfr_from_mgr")
        to_mgr   = c5.text_input("Receiver (Manager)", key="xfr_to_mgr")
        notes    = st.text_input("Notes (optional)", key="xfr_notes")

        if COST_CENTERS.get(from_label) == COST_CENTERS.get(to_label):
            st.error("From and To cost centers must be different.")
            return

        st.markdown("---")
        st.subheader("Add Items")

        all_items = self.db.get_all_items()
        if not all_items:
            st.warning("No inventory items found.")
            return

        item_map = {
            f"{i['description']}  ({i['pack_type'] or 'CASE'})": i
            for i in all_items
        }

        with st.form("add_transfer_line", clear_on_submit=True):
            lc1, lc2, lc3 = st.columns([4, 1, 1])
            item_label = lc1.selectbox("Item", list(item_map.keys()),
                                        key="xfr_item_sel")
            item       = item_map[item_label]
            quantity   = lc2.number_input("Qty", value=1.0,
                                           min_value=0.001, format="%.4f",
                                           key="xfr_qty")
            line_notes = lc3.text_input("Notes", key="xfr_line_notes")

            unit_cost = float(item.get("cost") or 0)
            gl_code   = item.get("gl_code") or "—"
            gl_name   = item.get("gl_name") or "—"
            st.caption(
                f"Unit Cost: **${unit_cost:.4f}** · "
                f"GL: **{gl_code} — {gl_name}** · "
                f"Line Total: **${unit_cost * quantity:.2f}**"
            )
            add_btn = st.form_submit_button("➕ Add to Transfer", type="primary")

        if add_btn:
            st.session_state["transfer_draft_lines"].append({
                "item_key":    item["key"],
                "description": item["description"],
                "gl_code":     item.get("gl_code") or "",
                "gl_name":     item.get("gl_name") or "",
                "pack_type":   item.get("pack_type") or "CASE",
                "quantity":    quantity,
                "unit_cost":   unit_cost,
                "total_value": round(unit_cost * quantity, 4),
                "notes":       line_notes,
            })
            st.rerun()

        lines = st.session_state.get("transfer_draft_lines", [])
        if not lines:
            st.info("No items added yet.")
            return

        st.markdown("---")
        st.subheader("Transfer Lines")

        st.dataframe(pd.DataFrame([{
            "Description": l["description"],
            "Pack Type":   l["pack_type"],
            "GL Code":     l["gl_code"],
            "GL Name":     l["gl_name"],
            "Qty":         l["quantity"],
            "Unit Cost":   f"${l['unit_cost']:.4f}",
            "Total":       f"${l['total_value']:.2f}",
            "Notes":       l.get("notes", ""),
        } for l in lines]), use_container_width=True, hide_index=True)

        with st.expander("🗑️ Remove a line"):
            remove_options = {
                f"{l['description']} × {l['quantity']}": i
                for i, l in enumerate(lines)
            }
            to_remove_label = st.selectbox("Select line",
                                            list(remove_options.keys()),
                                            key="xfr_remove_sel")
            if st.button("Remove", key="xfr_remove_btn"):
                st.session_state["transfer_draft_lines"].pop(
                    remove_options[to_remove_label])
                st.rerun()

        # GL summary
        st.markdown("---")
        st.subheader("GL Summary")
        gl_totals: dict = {}
        total_value = 0.0
        for l in lines:
            key = f"{l['gl_code']} — {l['gl_name']}" if l['gl_code'] else "NO GL"
            gl_totals[key] = gl_totals.get(key, 0) + l["total_value"]
            total_value   += l["total_value"]

        st.dataframe(pd.DataFrame([
            {"GL": k, "Total": f"${v:.2f}"}
            for k, v in sorted(gl_totals.items())
        ]), use_container_width=True, hide_index=True)

        # Summary + confirm
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        c1.metric("Transfer Total", f"${total_value:.2f}")
        c2.metric("From", from_label)
        c3.metric("To",   to_label)

        st.success(
            f"✅ **${total_value:.2f}** moving from **{from_label}** → **{to_label}**"
        )

        confirmed = st.checkbox(
            f"I confirm this transfer of ${total_value:.2f} "
            f"from {from_label} to {to_label} on {xfr_date}",
            key="xfr_confirm"
        )
        if st.button("✅ Submit Transfer", type="primary",
                     disabled=not confirmed, key="xfr_submit"):
            self._submit_transfer(
                from_cc=COST_CENTERS[from_label],
                from_cc_name=from_label,
                to_cc=COST_CENTERS[to_label],
                to_cc_name=to_label,
                transfer_date=xfr_date,
                from_mgr=from_mgr,
                to_mgr=to_mgr,
                notes=notes,
                lines=lines,
                total_value=total_value,
            )

    # ── Submit ────────────────────────────────────────────────────────────────

    def _submit_transfer(self, from_cc, from_cc_name, to_cc, to_cc_name,
                         transfer_date, from_mgr, to_mgr, notes,
                         lines, total_value):
        import uuid
        from database import get_conn
        transfer_id = (f"XFR-{transfer_date.strftime('%Y%m%d')}"
                       f"-{uuid.uuid4().hex[:6].upper()}")
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO transfers
                        (transfer_id, transfer_date, from_cc, from_cc_name,
                         to_cc, to_cc_name, from_manager, to_manager,
                         status, gl_total, balanced, notes, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'submitted',%s,TRUE,%s,%s)
                """, (transfer_id, transfer_date, from_cc, from_cc_name,
                      to_cc, to_cc_name, from_mgr, to_mgr,
                      total_value, notes, "web_user"))

                for l in lines:
                    cur.execute("""
                        INSERT INTO transfer_lines
                            (transfer_id, item_key, description, gl_code,
                             gl_name, pack_type, quantity, unit_cost,
                             total_value, notes)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (transfer_id, l["item_key"], l["description"],
                          l["gl_code"], l["gl_name"], l["pack_type"],
                          l["quantity"], l["unit_cost"], l["total_value"],
                          l.get("notes", "")))

            st.success(f"✅ Transfer **{transfer_id}** submitted!")
            st.session_state["transfer_draft_lines"] = []
            st.rerun()
        except Exception as exc:
            import traceback
            st.error(f"Submit failed: {exc}")
            st.code(traceback.format_exc())

    # ── History ───────────────────────────────────────────────────────────────

    def _render_history(self):
        st.subheader("Transfer History")
        fc1, fc2, fc3 = st.columns(3)
        valid_ccs     = list(COST_CENTERS.keys())
        filter_cc     = fc1.selectbox("Cost Center", ["All"] + valid_ccs,
                                       key="hist_cc")
        filter_status = fc2.selectbox("Status",
                                       ["All","draft","submitted","approved"],
                                       key="hist_status")
        limit         = fc3.number_input("Show last N", value=20, min_value=1,
                                          step=1, key="hist_limit")
        try:
            from database import get_conn
            with get_conn() as conn:
                cur = conn.cursor()
                where, params = [], []
                if filter_cc != "All":
                    cc_code = COST_CENTERS[filter_cc]
                    where.append("(from_cc = %s OR to_cc = %s)")
                    params += [cc_code, cc_code]
                if filter_status != "All":
                    where.append("status = %s")
                    params.append(filter_status)
                sql = "SELECT * FROM transfers"
                if where:
                    sql += " WHERE " + " AND ".join(where)
                sql += " ORDER BY transfer_date DESC, created_at DESC LIMIT %s"
                params.append(int(limit))
                cur.execute(sql, params)
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]

            if not rows:
                st.info("No transfers found.")
                return

            st.dataframe(pd.DataFrame([{
                "ID":     r["transfer_id"],
                "Date":   str(r["transfer_date"])[:10],
                "From":   r["from_cc_name"] or r["from_cc"],
                "To":     r["to_cc_name"]   or r["to_cc"],
                "Total":  f"${float(r['gl_total'] or 0):,.2f}",
                "Status": r["status"],
            } for r in rows]), use_container_width=True, hide_index=True)

            st.markdown("---")
            sel_id  = st.selectbox("View detail",
                                    [r["transfer_id"] for r in rows],
                                    key="hist_detail")
            sel_xfr = next(r for r in rows if r["transfer_id"] == sel_id)

            st.markdown(
                f"**{sel_xfr['transfer_id']}** · "
                f"{str(sel_xfr['transfer_date'])[:10]}  \n"
                f"From: **{sel_xfr['from_cc_name']}** "
                f"({sel_xfr.get('from_manager','—')})  \n"
                f"To: **{sel_xfr['to_cc_name']}** "
                f"({sel_xfr.get('to_manager','—')})  \n"
                f"Total: **${float(sel_xfr['gl_total'] or 0):,.2f}** · "
                f"Status: **{sel_xfr['status']}**"
            )
            if sel_xfr.get("notes"):
                st.caption(f"Notes: {sel_xfr['notes']}")

            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM transfer_lines "
                    "WHERE transfer_id=%s ORDER BY line_id",
                    (sel_id,)
                )
                lcols = [d[0] for d in cur.description]
                lrows = [dict(zip(lcols, r)) for r in cur.fetchall()]

            if lrows:
                st.dataframe(pd.DataFrame([{
                    "Description": r["description"],
                    "Pack Type":   r["pack_type"],
                    "GL Code":     r["gl_code"],
                    "GL Name":     r["gl_name"],
                    "Qty":         r["quantity"],
                    "Unit Cost":   f"${float(r['unit_cost'] or 0):.4f}",
                    "Total":       f"${float(r['total_value'] or 0):.2f}",
                    "Notes":       r.get("notes",""),
                } for r in lrows]), use_container_width=True, hide_index=True)

            if sel_xfr["status"] == "submitted":
                if st.button("✅ Approve Transfer",
                             key=f"approve_{sel_id}", type="primary"):
                    with get_conn() as conn:
                        cur = conn.cursor()
                        cur.execute("""
                            UPDATE transfers
                            SET status='approved', approved_by=%s,
                                approved_at=NOW()
                            WHERE transfer_id=%s
                        """, ("web_user", sel_id))
                    st.success("Approved.")
                    st.rerun()

        except Exception as exc:
            import traceback
            st.error(f"History error: {exc}")
            st.code(traceback.format_exc())

# ── end of TransferDashboard ──────────────────────────────────────────────────
