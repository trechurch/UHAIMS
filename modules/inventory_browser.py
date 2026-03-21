# ──────────────────────────────────────────────────────────────────────────────
#  modules/inventory_browser.py  —  Inventory Browser & Editor
#  v1.2.0  —  Single scrollable dataframe list. Select via dropdown above
#              detail panel. No per-row buttons.
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
from datetime import datetime
from base import Dashboard


class InventoryBrowser(Dashboard):

    MANIFEST = {
        "id":       "inventory_browser",
        "label":    "Inventory",
        "version":  "1.2.0",
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
        "session_keys": ["ib_selected_key", "ib_edit_mode"],
        "abilities": [
            "Search and filter full inventory",
            "View item details with all fields",
            "Edit any field inline",
            "Set and clear field-level overrides",
            "View full change history per item",
        ],
        "permissions": {"min_role": "user"},
    }

    DOCS = {
        "summary": "Browse, search, and edit the full inventory database.",
        "usage": "Search/filter the list. Select an item from the dropdown to view details.",
        "demo_ready": True,
        "notes": "v1.2.0: Single dataframe list + dropdown selector.",
        "known_issues": [],
        "changelog": [
            {"version": "1.2.0", "date": "2026-03-20", "note": "Dataframe list + dropdown selector."},
            {"version": "1.0.0", "date": "2026-03-20", "note": "Initial implementation."},
        ],
    }

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

        # ── Search + filters (top bar) ────────────────────────────────────
        fc1, fc2, fc3 = st.columns([3, 2, 2])
        search     = fc1.text_input("🔍 Search", placeholder="Name, vendor, GL...",
                                    key="ib_search", label_visibility="collapsed")
        with st.spinner(""):
            if search and len(search) >= 2:
                items = self.db.search_items(search)
            else:
                items = self.db.get_all_items("active")

        if not items:
            st.info("No items found.")
            return

        gl_codes   = sorted(set(i.get("gl_code") or "" for i in items if i.get("gl_code")))
        vendors    = sorted(set(i.get("vendor")   or "" for i in items if i.get("vendor")))
        gl_filter  = fc2.selectbox("GL",     ["All"] + gl_codes, key="ib_gl",
                                   label_visibility="collapsed")
        vnd_filter = fc3.selectbox("Vendor", ["All"] + vendors,  key="ib_vnd",
                                   label_visibility="collapsed")

        if gl_filter  != "All": items = [i for i in items if i.get("gl_code") == gl_filter]
        if vnd_filter != "All": items = [i for i in items if i.get("vendor")   == vnd_filter]

        # ── Two columns: list + detail ────────────────────────────────────
        left, right = st.columns([2, 3], gap="medium")

        with left:
            st.caption(f"{len(items)} items")

            # Build display dataframe
            rows = []
            keys = []
            for item in items:
                cost = float(item.get("cost") or 0)
                conv = float(item.get("conv_ratio") or 1)
                uc   = cost / conv if conv > 1 else cost
                qty  = float(item.get("quantity_on_hand") or 0)
                rows.append({
                    "Description": (item.get("description") or "")[:38],
                    "Pack":        (item.get("pack_type") or "")[:14],
                    "$/ea":        f"${uc:.3f}",
                    "Qty":         f"{qty:.0f}",
                })
                keys.append(item["key"])

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True,
                         hide_index=True, height=550)

            # Selector below the list
            st.markdown("**Select item:**")
            desc_labels = [r["Description"] for r in rows]
            sel_idx = st.selectbox(
                "Item", range(len(desc_labels)),
                format_func=lambda i: desc_labels[i],
                key="ib_sel_idx",
                label_visibility="collapsed"
            )
            if sel_idx is not None:
                new_key = keys[sel_idx]
                if new_key != st.session_state.get("ib_selected_key"):
                    st.session_state["ib_selected_key"] = new_key
                    st.session_state["ib_edit_mode"] = False
                    st.rerun()

        with right:
            self._render_detail_panel()

    # ── Detail Panel ──────────────────────────────────────────────────────────

    def _render_detail_panel(self):
        key = st.session_state.get("ib_selected_key")
        if not key:
            st.markdown(
                "<div style='color:#4A4E55;padding:60px 20px;text-align:center;"
                "font-size:14px'>← Select an item to view details</div>",
                unsafe_allow_html=True
            )
            return

        item = self.db.get_item(key)
        if not item:
            st.error("Item not found.")
            return

        edit_mode = st.session_state.get("ib_edit_mode", False)

        hc1, hc2, hc3 = st.columns([4, 1, 1])
        hc1.subheader(item.get("description") or key.split("||")[0])
        if hc2.button("✏️ Edit" if not edit_mode else "👁 View",
                      use_container_width=True, key="ib_edit_btn"):
            st.session_state["ib_edit_mode"] = not edit_mode
            st.rerun()
        if hc3.button("🗑️ Archive", use_container_width=True, key="ib_arch_btn"):
            self.db.delete_item(key, changed_by="web_user")
            st.session_state["ib_selected_key"] = None
            st.rerun()

        st.caption(f"`{key}`")
        st.markdown("---")

        if edit_mode:
            self._render_edit_form(item)
        else:
            self._render_detail_view(item)

    # ── Detail View ───────────────────────────────────────────────────────────

    def _render_detail_view(self, item: dict):
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
        tab1, tab2, tab3 = st.tabs(["📋 Details", "🔒 Overrides", "📜 History"])

        with tab1:
            rows = [
                ("Pack Type",   item.get("pack_type")   or "—"),
                ("Per",         item.get("per")         or "—"),
                ("Conv Ratio",  f"{conv:.4f}"),
                ("Yield %",     f"{yld*100:.1f}%"),
                ("Unit",        item.get("unit")        or "—"),
                ("Vendor",      item.get("vendor")      or "—"),
                ("Item #",      item.get("item_number") or "—"),
                ("MOG",         item.get("mog")         or "—"),
                ("GL Code",     item.get("gl_code")     or "—"),
                ("GL Name",     item.get("gl_name")     or "—"),
                ("Cost Center", item.get("cost_center") or "—"),
                ("Chargeable",  "✅ Yes" if item.get("is_chargeable") else "❌ No"),
                ("Status Tag",  item.get("status_tag")  or "—"),
                ("Last Updated",str(item.get("last_updated") or "—")[:19]),
            ]
            st.dataframe(pd.DataFrame(rows, columns=["Field", "Value"]),
                         use_container_width=True, hide_index=True)

        with tab2:
            self._render_overrides(item)

        with tab3:
            self._render_history(item["key"])

    # ── Edit Form ─────────────────────────────────────────────────────────────

    def _render_edit_form(self, item: dict):
        key = item["key"]
        with st.form(f"edit_{key}"):
            c1, c2 = st.columns(2)
            description = c1.text_input("Description", value=item.get("description") or "")
            pack_type   = c2.text_input("Pack Type",   value=item.get("pack_type")   or "")
            c3, c4, c5 = st.columns(3)
            cost       = c3.number_input("Invoice Cost $", value=float(item.get("cost") or 0), format="%.4f")
            conv_ratio = c4.number_input("Conv Ratio",     value=float(item.get("conv_ratio") or 1), format="%.4f")
            yield_pct  = c5.number_input("Yield %",        value=float(item.get("yield") or 1)*100, format="%.1f")
            c6, c7, c8 = st.columns(3)
            per        = c6.selectbox("Per", ["Case","Each"],
                                      index=0 if (item.get("per") or "Case")=="Case" else 1)
            vendor     = c7.text_input("Vendor",  value=item.get("vendor")     or "")
            gl_code    = c8.text_input("GL Code", value=item.get("gl_code")    or "")
            c9, c10    = st.columns(2)
            item_number  = c9.text_input("Item #",       value=item.get("item_number")  or "")
            cost_center  = c10.text_input("Cost Center", value=item.get("cost_center")  or "")
            is_chargeable = st.checkbox("Chargeable", value=bool(item.get("is_chargeable", True)))
            user_notes    = st.text_area("Notes", value=item.get("user_notes") or "", height=60)
            submitted = st.form_submit_button("💾 Save Changes", type="primary")

        if submitted:
            from database import get_conn
            updates = {
                "description":   description.upper(),
                "pack_type":     pack_type,
                "cost":          cost,
                "conv_ratio":    conv_ratio,
                "yield":         yield_pct / 100.0,
                "per":           per,
                "vendor":        vendor,
                "gl_code":       gl_code,
                "item_number":   item_number,
                "cost_center":   cost_center,
                "is_chargeable": is_chargeable,
                "user_notes":    user_notes,
                "last_updated":  datetime.utcnow(),
            }
            try:
                set_clause = ", ".join(f"{k} = %s" for k in updates)
                with get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute(f"UPDATE items SET {set_clause} WHERE key = %s",
                                list(updates.values()) + [key])
                st.success("✅ Saved.")
                st.session_state["ib_edit_mode"] = False
                st.rerun()
            except Exception as exc:
                st.error(f"Save failed: {exc}")

    # ── Overrides ─────────────────────────────────────────────────────────────

    def _render_overrides(self, item: dict):
        key = item["key"]
        st.caption("Overrides lock a field against future import overwrites.")
        for fk, (label, val) in {
            "conv_ratio": ("Conv Ratio", item.get("override_conv_ratio")),
            "yield":      ("Yield",      item.get("override_yield")),
            "pack_type":  ("Pack Type",  item.get("override_pack_type")),
            "vendor":     ("Vendor",     item.get("override_vendor")),
            "gl":         ("GL Code",    item.get("override_gl")),
        }.items():
            oc1, oc2, oc3 = st.columns([2, 2, 1])
            oc1.markdown(f"**{label}**")
            if val:
                oc2.markdown(f"🔒 `{val}`")
                if oc3.button("Clear", key=f"clr_{fk}_{key}"):
                    self.db.clear_override(key, fk, changed_by="web_user")
                    st.rerun()
            else:
                nv = oc2.text_input("", key=f"ovr_{fk}_{key}",
                                    label_visibility="collapsed",
                                    placeholder=f"Set {label}…")
                if oc3.button("Set", key=f"set_{fk}_{key}"):
                    if nv:
                        self.db.set_override(key, fk, nv, changed_by="web_user")
                        st.rerun()

    # ── History ───────────────────────────────────────────────────────────────

    def _render_history(self, key: str):
        history = self.db.get_item_history(key, limit=50)
        prices  = self.db.get_price_history(key, limit=20)
        if history:
            st.markdown("**Change History**")
            st.dataframe(pd.DataFrame([{
                "Date":   str(h.get("change_date") or "")[:16],
                "Field":  h.get("field_changed") or "",
                "Old":    str(h.get("old_value") or "")[:30],
                "New":    str(h.get("new_value") or "")[:30],
                "By":     h.get("changed_by") or "",
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
