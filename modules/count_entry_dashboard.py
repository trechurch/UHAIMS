# ──────────────────────────────────────────────────────────────────────────────
#  modules/count_entry_dashboard.py  —  Physical Inventory Count Entry
#  v1.0.0
#
#  Presents items grouped by GL code (matching the printed count sheet).
#  Counters enter quantities; session is saved and then committed to QOH.
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
from datetime import date, datetime
from base import Dashboard

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
        "label":    "Count Entry",
        "version":  "1.0.0",
        "icon":     "📝",
        "status":   "active",
        "page_key": "count_entry",
        "menu": {
            "parent":   "Dashboards",
            "label":    "Count Entry",
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

        tab1, tab2 = st.tabs(["✏️ Active Count", "📋 Count History"])
        with tab1:
            self._render_active_count()
        with tab2:
            self._render_history()

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
                new_qty = r4.number_input(
                    "", value=prev, min_value=0.0, format="%.2f",
                    step=1.0, key=f"ce_qty_{key}",
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

# ── end of CountEntryDashboard ────────────────────────────────────────────────
