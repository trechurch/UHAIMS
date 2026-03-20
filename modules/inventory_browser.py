# ──────────────────────────────────────────────────────────────────────────────
#  modules/inventory_browser.py  —  Inventory Browser & Editor
#  v1.0.0  —  Two-panel layout: searchable item list + detail/edit panel.
#              Inline editing, override management, field-level history.
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
from datetime import datetime
from base import Dashboard


class InventoryBrowser(Dashboard):

    MANIFEST = {
        "id":       "inventory_browser",
        "label":    "Inventory",
        "version":  "1.0.0",
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
        "session_keys": ["ib_selected_key", "ib_search", "ib_filter_gl",
                         "ib_filter_vendor", "ib_edit_mode"],
        "abilities": [
            "Search and filter full inventory",
            "View item details with all fields",
            "Edit any field inline",
            "Set and clear field-level overrides",
            "View full change history per item",
            "View price history per item",
        ],
        "permissions": {"min_role": "user"},
    }

    DOCS = {
        "summary": "Browse, search, and edit the full inventory database.",
        "usage": "Search or filter on the left. Click an item to view and edit on the right.",
        "demo_ready": True,
        "notes": "Overrides lock a field against future import overwrites.",
        "known_issues": [],
        "changelog": [
            {"version": "1.0.0", "date": "2026-03-20", "note": "Initial implementation."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        if "ib_selected_key" not in st.session_state:
            st.session_state["ib_selected_key"] = None
        if "ib_edit_mode" not in st.session_state:
            st.session_state["ib_edit_mode"] = False

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**🗃️ Inventory**")
            st.caption("Browse · Search · Edit")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.title("🗃️ Inventory Browser")

        # Two-column layout — left: list, right: detail
        left, right = st.columns([2, 3], gap="medium")

        with left:
            self._render_list_panel()

        with right:
            self._render_detail_panel()

    # ── Left Panel: List ──────────────────────────────────────────────────────

    def _render_list_panel(self):
        st.subheader("Items")

        # Search
        search = st.text_input("🔍 Search", 
                                placeholder="Name, vendor, GL code...",
                                key="ib_search_input",
                                label_visibility="collapsed")

        # Load items
        with st.spinner(""):
            if search and len(search) >= 2:
                items = self.db.search_items(search)
            else:
                items = self.db.get_all_items("active")

        if not items:
            st.info("No items found.")
            return

        # Filter row
        fc1, fc2 = st.columns(2)
        gl_codes  = sorted(set(i.get("gl_code") or "" for i in items if i.get("gl_code")))
        vendors   = sorted(set(i.get("vendor") or "" for i in items if i.get("vendor")))

        gl_filter  = fc1.selectbox("GL", ["All"] + gl_codes,
                                    key="ib_gl_filter", label_visibility="collapsed")
        vnd_filter = fc2.selectbox("Vendor", ["All"] + vendors,
                                    key="ib_vnd_filter", label_visibility="collapsed")

        if gl_filter  != "All": items = [i for i in items if i.get("gl_code") == gl_filter]
        if vnd_filter != "All": items = [i for i in items if i.get("vendor") == vnd_filter]

        st.caption(f"{len(items)} items")

        # Item list — styled rows
        selected = st.session_state.get("ib_selected_key")

        for item in items:
            key  = item["key"]
            desc = item.get("description") or key.split("||")[0]
            pack = item.get("pack_type") or ""
            cost = float(item.get("cost") or 0)
            conv = float(item.get("conv_ratio") or 1)
            unit_cost = cost / conv if conv > 1 else cost
            qty  = float(item.get("quantity_on_hand") or 0)
            vendor = item.get("vendor") or "—"

            is_selected = (key == selected)
            bg = "#1E3A5F" if is_selected else "#1A1D23"
            border = "2px solid #0066CC" if is_selected else "1px solid #2D3139"

            st.markdown(
                f"""<div style='background:{bg};border:{border};border-radius:6px;
                    padding:8px 12px;margin-bottom:4px;cursor:pointer;'>
                    <div style='font-size:12px;font-weight:600;color:#E8EAF0'>{desc[:45]}</div>
                    <div style='font-size:10px;color:#6E737A;margin-top:2px'>
                        {pack} &nbsp;·&nbsp; ${unit_cost:.4f}/ea &nbsp;·&nbsp; 
                        qty: {qty:.1f} &nbsp;·&nbsp; {vendor[:20]}
                    </div>
                </div>""",
                unsafe_allow_html=True
            )
            if st.button("Select", key=f"sel_{key}",
                         help=desc, use_container_width=True,
                         type="primary" if is_selected else "secondary"):
                st.session_state["ib_selected_key"] = key
                st.session_state["ib_edit_mode"] = False
                st.rerun()

    # ── Right Panel: Detail / Edit ────────────────────────────────────────────

    def _render_detail_panel(self):
        key = st.session_state.get("ib_selected_key")
        if not key:
            st.markdown(
                "<div style='color:#4A4E55;padding:40px;text-align:center;"
                "font-size:14px'>← Select an item to view details</div>",
                unsafe_allow_html=True
            )
            return

        item = self.db.get_item(key)
        if not item:
            st.error("Item not found.")
            return

        edit_mode = st.session_state.get("ib_edit_mode", False)

        # Header
        hc1, hc2, hc3 = st.columns([4, 1, 1])
        hc1.subheader(item.get("description") or key.split("||")[0])
        if hc2.button("✏️ Edit" if not edit_mode else "👁 View",
                       use_container_width=True):
            st.session_state["ib_edit_mode"] = not edit_mode
            st.rerun()
        if hc3.button("🗑️ Archive", use_container_width=True):
            self.db.delete_item(key, changed_by="web_user")
            st.session_state["ib_selected_key"] = None
            st.success("Archived.")
            st.rerun()

        st.caption(f"Key: `{key}`")
        st.markdown("---")

        if edit_mode:
            self._render_edit_form(item)
        else:
            self._render_detail_view(item)

    # ── Detail View ───────────────────────────────────────────────────────────

    def _render_detail_view(self, item: dict):
        key = item["key"]

        # Cost metrics
        cost      = float(item.get("cost") or 0)
        conv      = float(item.get("override_conv_ratio") or item.get("conv_ratio") or 1)
        yld       = float(item.get("override_yield") or item.get("yield") or 1)
        unit_cost = cost / conv if conv > 1 else cost
        ep_cost   = unit_cost / yld if yld > 0 else unit_cost

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Invoice Cost",  f"${cost:.4f}")
        c2.metric("Unit Cost",     f"${unit_cost:.4f}")
        c3.metric("EP Cost",       f"${ep_cost:.4f}")
        c4.metric("On Hand",       f"{float(item.get('quantity_on_hand') or 0):.1f}")

        st.markdown("---")
        tab1, tab2, tab3 = st.tabs(["📋 Details", "🔒 Overrides", "📜 History"])

        with tab1:
            rows = [
                ("Pack Type",    item.get("pack_type")    or "—"),
                ("Per",          item.get("per")          or "—"),
                ("Conv Ratio",   f"{conv:.4f}"),
                ("Yield %",      f"{yld*100:.1f}%"),
                ("Unit",         item.get("unit")         or "—"),
                ("Vendor",       item.get("vendor")       or "—"),
                ("Item #",       item.get("item_number")  or "—"),
                ("MOG",          item.get("mog")          or "—"),
                ("GL Code",      item.get("gl_code")      or "—"),
                ("GL Name",      item.get("gl_name")      or "—"),
                ("Cost Center",  item.get("cost_center")  or "—"),
                ("Chargeable",   "✅ Yes" if item.get("is_chargeable") else "❌ No"),
                ("Status Tag",   item.get("status_tag")   or "—"),
                ("Last Updated", str(item.get("last_updated") or "—")[:19]),
            ]
            st.dataframe(
                pd.DataFrame(rows, columns=["Field", "Value"]),
                use_container_width=True, hide_index=True
            )

        with tab2:
            self._render_overrides(item)

        with tab3:
            self._render_history(item["key"])

    # ── Edit Form ─────────────────────────────────────────────────────────────

    def _render_edit_form(self, item: dict):
        key = item["key"]
        st.markdown("**Edit Item**")

        with st.form(f"edit_{key}"):
            c1, c2 = st.columns(2)

            description = c1.text_input("Description",
                                         value=item.get("description") or "")
            pack_type   = c2.text_input("Pack Type",
                                         value=item.get("pack_type") or "")

            c3, c4, c5 = st.columns(3)
            cost       = c3.number_input("Invoice Cost $",
                                          value=float(item.get("cost") or 0),
                                          format="%.4f")
            conv_ratio = c4.number_input("Conv Ratio",
                                          value=float(item.get("conv_ratio") or 1),
                                          format="%.4f")
            yield_pct  = c5.number_input("Yield %",
                                          value=float(item.get("yield") or 1) * 100,
                                          format="%.1f")

            c6, c7, c8 = st.columns(3)
            per        = c6.selectbox("Per", ["Case", "Each"],
                                       index=0 if (item.get("per") or "Case") == "Case" else 1)
            vendor     = c7.text_input("Vendor",
                                        value=item.get("vendor") or "")
            gl_code    = c8.text_input("GL Code",
                                        value=item.get("gl_code") or "")

            c9, c10 = st.columns(2)
            item_number = c9.text_input("Item #",
                                         value=item.get("item_number") or "")
            cost_center = c10.text_input("Cost Center",
                                          value=item.get("cost_center") or "")

            is_chargeable = st.checkbox("Chargeable",
                                         value=bool(item.get("is_chargeable", True)))
            user_notes    = st.text_area("Notes",
                                          value=item.get("user_notes") or "",
                                          height=80)

            submitted = st.form_submit_button("💾 Save Changes", type="primary")

        if submitted:
            updates = {
                "description":      description.upper(),
                "pack_type":        pack_type,
                "cost":             cost,
                "conv_ratio":       conv_ratio,
                "yield":            yield_pct / 100.0,
                "per":              per,
                "vendor":           vendor,
                "gl_code":          gl_code,
                "item_number":      item_number,
                "cost_center":      cost_center,
                "is_chargeable":    is_chargeable,
                "user_notes":       user_notes,
                "last_updated":     datetime.utcnow(),
            }
            from database import get_conn
            try:
                set_clause = ", ".join(f"{k} = %s" for k in updates)
                vals       = list(updates.values()) + [key]
                with get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        f"UPDATE items SET {set_clause} WHERE key = %s", vals
                    )
                st.success("✅ Saved.")
                st.session_state["ib_edit_mode"] = False
                st.rerun()
            except Exception as exc:
                st.error(f"Save failed: {exc}")

    # ── Overrides ─────────────────────────────────────────────────────────────

    def _render_overrides(self, item: dict):
        key = item["key"]
        st.caption("Overrides lock a field against future import overwrites.")

        override_fields = {
            "conv_ratio": ("Conv Ratio",    item.get("override_conv_ratio")),
            "yield":      ("Yield",         item.get("override_yield")),
            "pack_type":  ("Pack Type",     item.get("override_pack_type")),
            "vendor":     ("Vendor",        item.get("override_vendor")),
            "gl":         ("GL Code",       item.get("override_gl")),
        }

        for field_key, (label, current_val) in override_fields.items():
            oc1, oc2, oc3 = st.columns([2, 2, 1])
            oc1.markdown(f"**{label}**")
            if current_val:
                oc2.markdown(f"🔒 `{current_val}`")
                if oc3.button("Clear", key=f"clr_{field_key}_{key}"):
                    self.db.clear_override(key, field_key, changed_by="web_user")
                    st.rerun()
            else:
                new_val = oc2.text_input("Set override",
                                          key=f"ovr_{field_key}_{key}",
                                          label_visibility="collapsed",
                                          placeholder=f"Set {label} override…")
                if oc3.button("Set", key=f"set_{field_key}_{key}"):
                    if new_val:
                        self.db.set_override(key, field_key, new_val,
                                             changed_by="web_user")
                        st.rerun()

    # ── History ───────────────────────────────────────────────────────────────

    def _render_history(self, key: str):
        history = self.db.get_item_history(key, limit=50)
        prices  = self.db.get_price_history(key, limit=20)

        if history:
            st.markdown("**Change History**")
            hist_df = pd.DataFrame([{
                "Date":    str(h.get("change_date") or "")[:16],
                "Type":    h.get("change_type") or "",
                "Field":   h.get("field_changed") or "",
                "Old":     str(h.get("old_value") or "")[:30],
                "New":     str(h.get("new_value") or "")[:30],
                "By":      h.get("changed_by") or "",
                "Source":  h.get("change_source") or "",
            } for h in history])
            st.dataframe(hist_df, use_container_width=True, hide_index=True)
        else:
            st.info("No change history.")

        if prices:
            st.markdown("**Price History**")
            price_df = pd.DataFrame([{
                "Date":   str(p.get("doc_date") or "")[:10],
                "Price":  f"${float(p.get('price') or 0):.4f}",
                "File":   p.get("source_file") or "",
                "Vendor": p.get("vendor") or "",
            } for p in prices])
            st.dataframe(price_df, use_container_width=True, hide_index=True)

# ── end of InventoryBrowser ───────────────────────────────────────────────────
