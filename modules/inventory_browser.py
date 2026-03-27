# ──────────────────────────────────────────────────────────────────────────────
#  modules/inventory_browser.py  —  Inventory Browser & Editor
#  v2.0.0  —  Split-panel layout: 2/5 scrollable list · 3/5 detail/edit panel.
#              Single click   → populates detail panel, no tabs.
#              Multi-checkbox → one tab per selected item in detail panel.
#              All edits committed as manual changes with full history.
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
from datetime import datetime
from base import Dashboard
from utils import num_input, fmt_num
from ui_helpers import render_empty_state

try:
    import auth as _auth
    def _get_changed_by():
        return _auth.get_changed_by()
except Exception:
    def _get_changed_by():
        return "web_user"


class InventoryBrowser(Dashboard):

    MANIFEST = {
        "id":       "inventory_browser",
        "label":    "Inventory",
        "version":  "2.0.0",
        "icon":     "🗃️",
        "status":   "active",
        "page_key": "inventory",
        "menu": {
            "parent":   "Dashboards",
            "label":    "Inventory Browser",
            "shortcut": "I",
            "position": 30,
        },
        "sidebar": {
            "section":  "",
            "position": 30,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["items", "item_history", "price_history"],
        "session_keys": ["ib_selected_keys", "ib_focus_key"],
        "abilities": [
            "Search and filter full inventory",
            "Single-click to view item details",
            "Multi-checkbox → tabbed comparison",
            "Edit any field inline with full change history",
            "Set and clear field-level override locks",
            "View price history per item",
        ],
        "permissions": {"min_role": "user"},
    }

    DOCS = {
        "summary": "Split-panel inventory browser: scrollable list left, detail/edit panel right.",
        "usage": (
            "Search or filter the list. Click a row to view details. "
            "Check multiple rows to open tabbed comparison. "
            "Edit fields and save — changes are tracked with your username."
        ),
        "demo_ready": True,
        "notes": "v2.0.0: full split-panel rewrite matching design mockup.",
        "known_issues": [],
        "changelog": [
            {"version": "2.0.0", "date": "2026-03-23",
             "note": "Split-panel layout, multi-select tabs, click-to-edit."},
            {"version": "1.2.0", "date": "2026-03-20",
             "note": "Dataframe list + dropdown selector."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        if "ib_selected_keys" not in st.session_state:
            st.session_state["ib_selected_keys"] = []
        if "ib_focus_key" not in st.session_state:
            st.session_state["ib_focus_key"] = None
        if "ib_show_list" not in st.session_state:
            st.session_state["ib_show_list"] = True
        if "ib_recent_views" not in st.session_state:
            st.session_state["ib_recent_views"] = []  # list of (key, label), max 10

    @staticmethod
    def _push_recent(key: str, label: str) -> None:
        """Add an item to the recent-views list (deduped, newest first, max 10)."""
        hist = st.session_state.get("ib_recent_views", [])
        hist = [(k, l) for k, l in hist if k != key]   # remove existing entry
        hist.insert(0, (key, label))
        st.session_state["ib_recent_views"] = hist[:10]

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**🗃️ Inventory**")
            st.caption("Browse · Search · Edit")
            recent = st.session_state.get("ib_recent_views", [])
            if recent:
                st.markdown("**Recently Viewed**")
                for _key, _lbl in recent[:5]:
                    if st.button(_lbl[:30], key=f"ib_rv_{_key}",
                                 use_container_width=True):
                        st.session_state["ib_focus_key"]     = _key
                        st.session_state["ib_selected_keys"] = []
                        st.rerun()

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        # ── Page-level CSS ────────────────────────────────────────────────────
        st.markdown("""
        <style>
        /* Remove default top padding so the split panel fills the window */
        .block-container { padding-top: 0.5rem !important; }

        /* List panel row hover */
        .ib-row { cursor: pointer; }
        .ib-row:hover td { background: #1e293b !important; }

        /* Detail panel header */
        .ib-detail-header {
            font-size: 0.75rem;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 2px;
        }
        .ib-detail-value {
            font-size: 0.95rem;
            color: #e2e8f0;
            font-weight: 500;
            margin-bottom: 10px;
        }
        </style>
        """, unsafe_allow_html=True)

        # ── Top filter bar (full width) ───────────────────────────────────────
        show_list = st.session_state.get("ib_show_list", True)

        # Search history chips
        _search_hist = st.session_state.get("ib_search_history", [])
        if _search_hist:
            _chip_cols = st.columns([1] + [2] * len(_search_hist))
            _chip_cols[0].caption("Recent:")
            for _ci, _term in enumerate(_search_hist):
                if _chip_cols[_ci + 1].button(_term, key=f"ib_chip_{_ci}",
                                               use_container_width=True):
                    st.session_state["ib_search"] = _term
                    st.rerun()

        fc1, fc2, fc3, fc4, fc5 = st.columns([3, 2, 2, 1, 1])
        search     = fc1.text_input("", placeholder="🔍  Search items, vendor, GL...",
                                    key="ib_search", label_visibility="collapsed")
        with st.spinner(""):
            if search and len(search) >= 2:
                _hist = st.session_state.get("ib_search_history", [])
                if search not in _hist:
                    st.session_state["ib_search_history"] = ([search] + _hist)[:5]
                items = self.db.search_items(search)
            else:
                items = self.db.get_all_items("active")

        if not items:
            render_empty_state(
                "🔍", "No items found",
                "Try adjusting your search or clearing the GL / vendor filter.",
            )
            return

        gl_codes   = sorted({i.get("gl_code") or "" for i in items if i.get("gl_code")})
        vendors    = sorted({i.get("vendor") or "" for i in items if i.get("vendor")})
        gl_filter  = fc2.selectbox("GL",     ["All GL"] + gl_codes,
                                   key="ib_gl", label_visibility="collapsed")
        vnd_filter = fc3.selectbox("Vendor", ["All Vendors"] + vendors,
                                   key="ib_vnd", label_visibility="collapsed")
        show_disc  = fc4.checkbox("Disc.", key="ib_disc", help="Show discontinued")
        if fc5.button("◀ List" if show_list else "▶ List",
                      key="ib_toggle_list", use_container_width=True,
                      help="Hide list to expand detail panel"):
            st.session_state["ib_show_list"] = not show_list
            st.rerun()

        if gl_filter  != "All GL":
            items = [i for i in items if i.get("gl_code") == gl_filter]
        if vnd_filter != "All Vendors":
            items = [i for i in items if i.get("vendor") == vnd_filter]
        if not show_disc:
            items = [i for i in items if i.get("record_status", "active") == "active"]

        # ── Split: left list (2/5) · right detail (3/5) ───────────────────────
        if show_list:
            left, right = st.columns([2, 3], gap="medium")
            with left:
                self._render_list(items)
            with right:
                self._render_detail_panel(items)
        else:
            self._render_detail_panel(items)

    # ── LIST PANEL ────────────────────────────────────────────────────────────

    def _render_list(self, items: list) -> None:
        selected_keys = st.session_state.get("ib_selected_keys", [])
        focus_key     = st.session_state.get("ib_focus_key")

        st.caption(
            f"{len(items)} items · "
            f"{len(selected_keys)} selected"
            + (" · click row to view" if not selected_keys else "")
        )

        # Build display rows
        rows, keys = [], []
        for item in items:
            cost = float(item.get("cost") or 0)
            conv = float(item.get("conv_ratio") or 1)
            qty  = float(item.get("quantity_on_hand") or 0)
            uc   = cost / conv if conv > 1 else cost
            rows.append({
                "Description": (item.get("description") or "")[:36],
                "Pack":        (item.get("pack_type") or "")[:14],
                "$/ea":        round(uc, 3),
                "Qty":         round(qty, 0),
            })
            keys.append(item["key"])

        df = pd.DataFrame(rows)

        # Render with selection — Streamlit adds its own selection checkbox column
        event = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=620,
            column_config={
                "$/ea": st.column_config.NumberColumn("$/ea", format="$%.3f"),
                "Qty":  st.column_config.NumberColumn("Qty", format="%.0f"),
            },
            on_select="rerun",
            selection_mode=["multi-row"],
            key="ib_table",
        )

        # ── Process selections ─────────────────────────────────────────────────
        sel_rows = []
        try:
            sel_rows = event.selection.rows
        except Exception:
            sel_rows = st.session_state.get("ib_table", {}).get(
                "selection", {}).get("rows", [])

        if sel_rows:
            newly_selected = [keys[i] for i in sel_rows if i < len(keys)]
            if len(newly_selected) == 1:
                # Single row clicked → focus only
                new_focus = newly_selected[0]
                if new_focus != focus_key:
                    st.session_state["ib_focus_key"]     = new_focus
                    st.session_state["ib_selected_keys"] = []
                    st.rerun()
            else:
                # Multiple rows → multi-select mode
                if set(newly_selected) != set(selected_keys):
                    st.session_state["ib_selected_keys"] = newly_selected
                    st.session_state["ib_focus_key"]     = None
                    st.rerun()

        # ── Clear selection button ─────────────────────────────────────────────
        if selected_keys or focus_key:
            if st.button("✕ Clear selection", key="ib_clear",
                         use_container_width=True):
                st.session_state["ib_selected_keys"] = []
                st.session_state["ib_focus_key"]     = None
                st.rerun()

    # ── DETAIL PANEL ──────────────────────────────────────────────────────────

    def _render_detail_panel(self, items: list) -> None:
        focus_key     = st.session_state.get("ib_focus_key")
        selected_keys = st.session_state.get("ib_selected_keys", [])

        # Nothing selected
        if not focus_key and not selected_keys:
            render_empty_state(
                "←", "Select an item",
                "Click any row to view details · check multiple rows to compare",
            )
            return

        # ── Single item focus ─────────────────────────────────────────────────
        if focus_key and not selected_keys:
            item = self.db.get_item(focus_key)
            if not item:
                st.error("Item not found.")
                return
            self._push_recent(focus_key,
                              item.get("description") or focus_key.split("||")[0])
            self._render_single_item(item)
            return

        # ── Multi-select: one tab per item ────────────────────────────────────
        tab_labels = []
        tab_items  = []
        for key in selected_keys:
            item = self.db.get_item(key)
            if item:
                label = (item.get("description") or key.split("||")[0])[:18]
                tab_labels.append(label)
                tab_items.append(item)

        if not tab_items:
            render_empty_state("📭", "Items not found", "The selected items could not be loaded.")
            return

        tabs = st.tabs(tab_labels)
        for tab, item in zip(tabs, tab_items):
            with tab:
                self._render_single_item(item)

    # ── SINGLE ITEM VIEW ──────────────────────────────────────────────────────

    def _render_single_item(self, item: dict) -> None:
        key = item["key"]

        # ── Header row ────────────────────────────────────────────────────────
        h1, h2, h3 = st.columns([5, 1, 1])
        h1.subheader(item.get("description") or key.split("||")[0])
        edit_mode = st.session_state.get(f"ib_edit_{key}", False)

        if h2.button("✏️ Edit" if not edit_mode else "👁 View",
                     key=f"ib_edit_btn_{key}", use_container_width=True):
            st.session_state[f"ib_edit_{key}"] = not edit_mode
            st.rerun()

        if h3.button("🗑️ Archive", key=f"ib_arch_{key}", use_container_width=True):
            st.session_state["ib_confirm_delete"] = key
            st.rerun()

        st.caption(f"`{key}`")

        if st.session_state.get("ib_confirm_delete") == key:
            st.warning(f"Archive **{item.get('description', key)}**? This cannot be undone.")
            _dc1, _dc2 = st.columns(2)
            if _dc1.button("✅ Confirm Archive", key=f"ib_del_conf_{key}",
                           type="primary", use_container_width=True):
                self.db.delete_item(key, changed_by=_get_changed_by())
                st.session_state["ib_focus_key"] = None
                st.session_state["ib_selected_keys"] = []
                st.session_state.pop("ib_confirm_delete", None)
                st.rerun()
            if _dc2.button("✕ Cancel", key=f"ib_del_cancel_{key}", use_container_width=True):
                st.session_state.pop("ib_confirm_delete", None)
                st.rerun()
        st.markdown("---")

        if edit_mode:
            self._render_edit_form(item)
        else:
            self._render_view(item)

    # ── VIEW MODE ─────────────────────────────────────────────────────────────

    def _render_view(self, item: dict) -> None:
        cost = float(item.get("cost") or 0)
        conv = float(item.get("override_conv_ratio") or item.get("conv_ratio") or 1)
        yld  = float(item.get("override_yield")      or item.get("yield")      or 1)
        uc   = cost / conv if conv > 1 else cost
        epc  = uc / yld if yld > 0 else uc

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Invoice Cost", f"${cost:.4f}")
        c2.metric("Unit Cost",    f"${uc:.4f}")
        c3.metric("EP Cost",      f"${epc:.4f}")
        c4.metric("On Hand",      f"{float(item.get('quantity_on_hand') or 0):.1f}")

        st.markdown("---")
        t1, t2, t3 = st.tabs(["📋 Details", "🔒 Overrides", "📜 History"])

        with t1:
            def _lock(val) -> str:
                return " 🔒" if val is not None and str(val).strip() != "" else ""

            detail_rows = [
                ("Pack Type",    (item.get("pack_type")   or "—") + _lock(item.get("override_pack_type"))),
                ("Per",          item.get("per")           or "—"),
                ("Conv Ratio",   f"{conv:.4f}"             + _lock(item.get("override_conv_ratio"))),
                ("Yield %",      f"{yld * 100:.1f}%"       + _lock(item.get("override_yield"))),
                ("Vendor",       (item.get("vendor")       or "—") + _lock(item.get("override_vendor"))),
                ("Item #",       item.get("item_number")   or "—"),
                ("MOG",          item.get("mog")           or "—"),
                ("GL Code",      (item.get("gl_code")      or "—") + _lock(item.get("override_gl"))),
                ("GL Name",      item.get("gl_name")       or "—"),
                ("Cost Center",  item.get("cost_center")   or "—"),
                ("Chargeable",   "✅ Yes" if item.get("is_chargeable") else "❌ No"),
                ("Status Tag",   item.get("status_tag")    or "—"),
                ("Last Updated", str(item.get("last_updated") or "—")[:19]),
            ]
            st.dataframe(
                pd.DataFrame(detail_rows, columns=["Field", "Value"]),
                use_container_width=True, hide_index=True,
            )
            locked_count = sum(1 for f in [
                item.get("override_pack_type"), item.get("override_conv_ratio"),
                item.get("override_yield"), item.get("override_vendor"),
                item.get("override_gl"),
            ] if f is not None and str(f).strip() != "")
            if locked_count:
                st.caption(f"🔒 {locked_count} field(s) locked — see **Overrides** tab to manage")

        with t2:
            self._render_overrides(item)

        with t3:
            self._render_history(item["key"])

    # ── EDIT FORM ─────────────────────────────────────────────────────────────

    def _render_edit_form(self, item: dict) -> None:
        key = item["key"]

        with st.form(f"ib_edit_form_{key}"):
            c1, c2 = st.columns(2)
            description   = c1.text_input("Description",  value=item.get("description") or "")
            pack_type     = c2.text_input("Pack Type",    value=item.get("pack_type")   or "")

            c3, c4, c5 = st.columns(3)
            cost          = num_input("Invoice Cost $",
                                      value=float(item.get("cost") or 0),
                                      min_value=0.0, step=0.01)
            conv_ratio    = num_input("Conv Ratio",
                                      value=float(item.get("conv_ratio") or 1),
                                      min_value=0.0, step=0.01)
            yield_pct     = num_input("Yield %",
                                      value=float(item.get("yield") or 1) * 100,
                                      min_value=0.0, max_value=100.0, step=1.0)

            c6, c7, c8 = st.columns(3)
            per           = c6.selectbox("Per", ["Case", "Each"],
                                         index=0 if (item.get("per") or "Case") == "Case" else 1)
            vendor        = c7.text_input("Vendor",  value=item.get("vendor")      or "")
            gl_code       = c8.text_input("GL Code", value=item.get("gl_code")     or "")

            c9, c10, c11 = st.columns(3)
            item_number   = c9.text_input("Item #",       value=item.get("item_number")  or "")
            cost_center   = c10.text_input("Cost Center", value=item.get("cost_center")  or "")
            qoh           = num_input("Qty on Hand",
                                      value=float(item.get("quantity_on_hand") or 0),
                                      min_value=0.0)

            is_chargeable = st.checkbox("Chargeable",
                                        value=bool(item.get("is_chargeable", True)))
            user_notes    = st.text_area("Notes", value=item.get("user_notes") or "",
                                         height=60)

            st.markdown("**Override Locks** — checked = won't be overwritten by imports")
            oc1, oc2, oc3 = st.columns(3)
            lock_pack  = oc1.checkbox("Lock Pack Type",
                                      value=bool(item.get("override_pack_type")))
            lock_yield = oc2.checkbox("Lock Yield",
                                      value=bool(item.get("override_yield")))
            lock_conv  = oc3.checkbox("Lock Conv Ratio",
                                      value=bool(item.get("override_conv_ratio")))

            submitted = st.form_submit_button("💾 Save Changes", type="primary")

        if not submitted:
            return

        updates = {
            "description":      description.strip().upper(),
            "pack_type":        pack_type.strip().upper(),
            "cost":             cost,
            "conv_ratio":       conv_ratio,
            "yield":            yield_pct / 100.0,
            "per":              per,
            "vendor":           vendor,
            "gl_code":          gl_code,
            "item_number":      item_number,
            "cost_center":      cost_center,
            "quantity_on_hand": qoh,
            "is_chargeable":    is_chargeable,
            "user_notes":       user_notes,
            "last_updated":     datetime.utcnow(),
        }

        # Override lock handling
        if lock_pack:
            updates["override_pack_type"] = pack_type.strip().upper()
        elif not lock_pack and item.get("override_pack_type"):
            updates["override_pack_type"] = None

        if lock_yield:
            updates["override_yield"] = yield_pct / 100.0
        elif not lock_yield and item.get("override_yield"):
            updates["override_yield"] = None

        if lock_conv:
            updates["override_conv_ratio"] = conv_ratio
        elif not lock_conv and item.get("override_conv_ratio"):
            updates["override_conv_ratio"] = None

        try:
            self.db._apply_update(
                key, updates,
                change_source="manual_edit",
                changed_by=_get_changed_by(),
            )
            st.success("✅ Saved.")
            st.session_state[f"ib_edit_{key}"] = False
            st.rerun()
        except Exception as exc:
            st.error(f"Save failed: {exc}")

    # ── OVERRIDES ─────────────────────────────────────────────────────────────

    def _render_overrides(self, item: dict) -> None:
        key = item["key"]

        st.markdown("""
        <style>
        .ovr-locked {
            display:inline-block; background:#78350f; color:#fef3c7;
            border-radius:4px; padding:2px 10px; font-size:12px;
            font-family:monospace; font-weight:700; letter-spacing:.02em;
        }
        .ovr-free {
            display:inline-block; color:#475569;
            font-size:12px; font-family:monospace;
        }
        .ovr-live {
            display:inline-block; color:#94a3b8; font-size:11px;
        }
        </style>
        """, unsafe_allow_html=True)

        st.caption(
            "🔒 **Locked** fields keep their value through imports.  "
            "🔓 **Unlocked** fields follow incoming data."
        )
        st.markdown("")

        # field_key → (label, override_col_value, live_col_value)
        FIELDS = [
            ("conv_ratio", "Conv Ratio",
             item.get("override_conv_ratio"), item.get("conv_ratio")),
            ("yield",      "Yield",
             item.get("override_yield"),      item.get("yield")),
            ("pack_type",  "Pack Type",
             item.get("override_pack_type"),  item.get("pack_type")),
            ("vendor",     "Vendor",
             item.get("override_vendor"),     item.get("vendor")),
            ("gl",         "GL Code",
             item.get("override_gl"),         item.get("gl_code")),
        ]

        for fk, label, locked_val, live_val in FIELDS:
            is_locked = locked_val is not None and str(locked_val).strip() != ""
            c1, c2, c3, c4 = st.columns([2, 2, 2, 1])

            c1.markdown(f"**{label}**")

            if is_locked:
                c2.markdown(
                    f"<span class='ovr-locked'>🔒 {locked_val}</span>",
                    unsafe_allow_html=True,
                )
                c3.markdown(
                    f"<span class='ovr-live'>live: {live_val or '—'}</span>",
                    unsafe_allow_html=True,
                )
                if c4.button("Unlock", key=f"clr_{fk}_{key}",
                             use_container_width=True,
                             help=f"Remove lock — {label} will follow future imports"):
                    self.db.clear_override(key, fk, changed_by=_get_changed_by())
                    st.rerun()
            else:
                c2.markdown(
                    f"<span class='ovr-free'>🔓 {live_val or '—'}</span>",
                    unsafe_allow_html=True,
                )
                c3.markdown(
                    "<span class='ovr-live'>follows imports</span>",
                    unsafe_allow_html=True,
                )
                if c4.button("Lock", key=f"set_{fk}_{key}",
                             use_container_width=True,
                             help=f"Lock {label} to current value: {live_val}"):
                    if live_val is not None:
                        self.db.set_override(key, fk, str(live_val),
                                             changed_by=_get_changed_by())
                        st.rerun()
                    else:
                        st.caption(f"No current value to lock for {label}.")

    # ── HISTORY ───────────────────────────────────────────────────────────────

    def _render_history(self, key: str) -> None:
        history = self.db.get_item_history(key, limit=50)
        prices  = self.db.get_price_history(key, limit=20)

        if history:
            st.markdown("**Change History**")
            st.dataframe(pd.DataFrame([{
                "Date":  str(h.get("change_date") or "")[:16],
                "Field": h.get("field_changed") or "",
                "Old":   str(h.get("old_value")  or "")[:30],
                "New":   str(h.get("new_value")  or "")[:30],
                "By":    h.get("changed_by") or "",
                "Source":h.get("change_source") or "",
            } for h in history]), use_container_width=True, hide_index=True)
        else:
            st.info("No change history.")

        if prices:
            st.markdown("**Price History**")
            st.dataframe(pd.DataFrame([{
                "Date":   str(p.get("doc_date") or "")[:10],
                "Price":  f"${float(p.get('price') or 0):.4f}",
                "Vendor": p.get("vendor") or "",
            } for p in prices]), use_container_width=True, hide_index=True)

# ── end of InventoryBrowser ───────────────────────────────────────────────────
