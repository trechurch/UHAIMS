# ──────────────────────────────────────────────────────────────────────────────
#  modules/history_dashboard.py  —  Change History Dashboard
#  v2.0.0  —  Full list view, filters, search, popup detail
# ──────────────────────────────────────────────────────────────────────────────

import pandas as pd
import streamlit as st
from datetime import datetime, timezone
from base import Dashboard


_TIME_WINDOWS = {
    "Today":      1,
    "Last 7 days": 7,
    "Last 30 days": 30,
    "Last 90 days": 90,
    "All time":   None,
}

_CHANGE_TYPE_ICONS = {
    "add":    "➕",
    "update": "✏️",
    "delete": "🗑️",
    "import": "📥",
    "override": "🔒",
    "commit": "✅",
}


class HistoryDashboard(Dashboard):

    MANIFEST = {
        "id":       "history_dashboard",
        "label":    "History",
        "version":  "2.0.0",
        "icon":     "📜",
        "status":   "active",
        "page_key": "history",
        "menu": {
            "parent":   "View",
            "label":    "Change History",
            "shortcut": "H",
            "position": 20,
        },
        "sidebar": {
            "section":  "",
            "position": 20,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["items", "item_history"],
        "session_keys": ["hist_search", "hist_detail_id"],
        "abilities": [
            "Browse full change history — never blank on open",
            "Filter by time window, change type, user, field",
            "Search by item name or description",
            "Click any row to open popup with full field-level diff",
        ],
        "permissions": {"min_role": "any"},
    }

    DOCS = {
        "summary": "Sortable, filterable change history for all inventory items.",
        "usage":   "History loads immediately. Use filters to narrow. Click a row for full detail.",
        "demo_ready": True,
        "notes":   "Every import, manual edit, and override is recorded here.",
        "known_issues": [],
        "changelog": [
            {"version": "2.0.0", "date": "2026-03-28",
             "note": "Full list view, filter bar, popup detail. Replaced blank-screen stub."},
            {"version": "1.0.0", "date": "2026-03-25",
             "note": "Initial SDOA migration."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        if "hist_detail_id" not in st.session_state:
            st.session_state["hist_detail_id"] = None

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**📜 History**")
            st.caption("Change log · Field-level diff")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.markdown("### 📜 Change History")

        # ── Filter bar ────────────────────────────────────────────────────────
        fa, fb, fc, fd, fe = st.columns([3, 2, 2, 2, 1])

        search = fa.text_input(
            "", placeholder="🔍  Search item name...",
            key="hist_search_input", label_visibility="collapsed",
        )

        time_label = fb.selectbox(
            "", list(_TIME_WINDOWS.keys()), index=2,
            key="hist_time", label_visibility="collapsed",
        )
        since_days = _TIME_WINDOWS[time_label]

        # Lazy-load distinct values for filter dropdowns
        try:
            _dv = self.db.get_history_distinct_values()
        except Exception:
            _dv = {"change_types": [], "changed_bys": [], "field_changeds": []}

        change_types = ["All types"] + _dv.get("change_types", [])
        users        = ["All users"] + _dv.get("changed_bys", [])
        fields       = ["All fields"] + _dv.get("field_changeds", [])

        ct_filter  = fc.selectbox("", change_types,  key="hist_ct",  label_visibility="collapsed")
        usr_filter = fd.selectbox("", users,          key="hist_usr", label_visibility="collapsed")

        if fe.button("↺", key="hist_reset", help="Clear filters"):
            for k in ("hist_search_input", "hist_time", "hist_ct", "hist_usr"):
                st.session_state.pop(k, None)
            st.rerun()

        # ── Load data ─────────────────────────────────────────────────────────
        rows = self.db.get_all_history(
            limit=500,
            change_type=None if ct_filter  == "All types" else ct_filter,
            changed_by=None  if usr_filter == "All users" else usr_filter,
            search=search or None,
            since_days=since_days,
        )

        if not rows:
            st.info("No history records match the current filters.")
            return

        # ── Build display DataFrame ───────────────────────────────────────────
        display = []
        for r in rows:
            ct = r.get("change_type") or ""
            icon = _CHANGE_TYPE_ICONS.get(ct, "•")
            cd = r.get("change_date")
            if cd and hasattr(cd, "strftime"):
                date_str = cd.strftime("%Y-%m-%d %H:%M")
            else:
                date_str = str(cd or "")

            old_v = str(r.get("old_value") or "")[:40]
            new_v = str(r.get("new_value") or "")[:40]
            delta = ""
            try:
                if old_v and new_v:
                    diff = float(new_v) - float(old_v)
                    delta = f"{diff:+.2f}".rstrip("0").rstrip(".")
            except (ValueError, TypeError):
                pass

            display.append({
                "  ": icon,
                "Date":        date_str,
                "Item":        (r.get("description") or r.get("item_key") or "")[:38],
                "GL":          r.get("gl_code") or "",
                "Field":       r.get("field_changed") or "",
                "Old":         old_v,
                "New":         new_v,
                "Δ":           delta,
                "By":          r.get("changed_by") or "",
                "Source":      (r.get("change_source") or "")[:20],
                "_id":         r.get("history_id"),
            })

        df = pd.DataFrame(display)

        st.caption(
            f"{len(rows)} records · "
            f"{time_label.lower()} · "
            f"click a row to expand detail"
        )

        # ── Table with row selection ───────────────────────────────────────────
        event = st.dataframe(
            df.drop(columns=["_id"]),
            use_container_width=True,
            hide_index=True,
            height=520,
            column_config={
                "  ":   st.column_config.TextColumn("", width="small"),
                "Date": st.column_config.TextColumn("Date", width="medium"),
                "Item": st.column_config.TextColumn("Item", width="large"),
                "GL":   st.column_config.TextColumn("GL", width="small"),
                "Δ":    st.column_config.TextColumn("Δ", width="small"),
            },
            on_select="rerun",
            selection_mode="single-row",
            key="hist_table",
        )

        sel = event.selection.rows if hasattr(event, "selection") else []
        if sel:
            idx = sel[0]
            rid = display[idx]["_id"]
            if rid != st.session_state.get("hist_detail_id"):
                st.session_state["hist_detail_id"] = rid
                st.rerun()

        # ── Detail popup ──────────────────────────────────────────────────────
        detail_id = st.session_state.get("hist_detail_id")
        if detail_id is not None:
            # Find the record
            rec = next((r for r in rows if r.get("history_id") == detail_id), None)
            if rec:
                self._render_detail_popup(rec)

    # ── Detail popup ──────────────────────────────────────────────────────────

    def _render_detail_popup(self, rec: dict) -> None:
        ct = rec.get("change_type") or ""
        icon = _CHANGE_TYPE_ICONS.get(ct, "•")
        desc = rec.get("description") or rec.get("item_key") or "Unknown Item"

        with st.expander(
            f"{icon} {desc} — {ct.upper()} detail",
            expanded=True,
        ):
            col1, col2 = st.columns(2)

            cd = rec.get("change_date")
            date_str = cd.strftime("%Y-%m-%d %H:%M:%S %Z") if hasattr(cd, "strftime") else str(cd or "")

            col1.markdown(f"**Item:** `{rec.get('item_key', '')}`")
            col1.markdown(f"**Description:** {desc}")
            col1.markdown(f"**GL:** {rec.get('gl_code') or '—'}  {rec.get('gl_name') or ''}")
            col1.markdown(f"**Vendor:** {rec.get('vendor') or '—'}")

            col2.markdown(f"**Date:** {date_str}")
            col2.markdown(f"**Changed by:** {rec.get('changed_by') or '—'}")
            col2.markdown(f"**Source:** {rec.get('change_source') or '—'}")
            col2.markdown(f"**Document:** {rec.get('source_document') or '—'}")

            st.markdown("---")

            fc1, fc2, fc3 = st.columns(3)
            fc1.markdown("**Field**")
            fc2.markdown("**Old value**")
            fc3.markdown("**New value**")

            field = rec.get("field_changed") or "—"
            old_v = rec.get("old_value") or "—"
            new_v = rec.get("new_value") or "—"

            fc1.code(field)
            fc2.code(old_v)
            fc3.code(new_v)

            # Delta if numeric
            try:
                diff = float(new_v) - float(old_v)
                sign = "+" if diff >= 0 else ""
                color = "green" if diff >= 0 else "red"
                st.markdown(
                    f"**Value change:** :{color}[{sign}{diff:.4f}]",
                    unsafe_allow_html=False,
                )
            except (ValueError, TypeError):
                pass

            if rec.get("change_reason"):
                st.markdown(f"**Reason:** {rec['change_reason']}")
            if rec.get("metadata"):
                with st.expander("Raw metadata", expanded=False):
                    st.json(rec["metadata"])

            if st.button("✕ Close", key="hist_close_detail"):
                st.session_state["hist_detail_id"] = None
                st.rerun()

# ── end of HistoryDashboard ───────────────────────────────────────────────────
