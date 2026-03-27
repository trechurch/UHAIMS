# ──────────────────────────────────────────────────────────────────────────────
#  modules/pos_map_dashboard.py  —  POS ↔ Inventory Item Mapping (F-037)
#  v1.0.0
# ──────────────────────────────────────────────────────────────────────────────

import re
from pathlib import Path

import pandas as pd
import streamlit as st

from base import Dashboard

try:
    import auth as _auth
    def _get_changed_by(): return _auth.get_changed_by()
except Exception:
    def _get_changed_by(): return "web_user"

_SOURCE_FILE = Path(__file__).parent.parent / "docs" / "compare product lists.txt"


class PosMapDashboard(Dashboard):

    MANIFEST = {
        "id":       "pos_map",
        "label":    "POS Mapping",
        "version":  "1.0.0",
        "icon":     "🗺️",
        "status":   "active",
        "page_key": "pos_map",
        "menu": {
            "parent":   "Tools",
            "label":    "POS ↔ Inventory Map",
            "shortcut": "P",
            "position": 95,
        },
        "sidebar": {
            "section":  "",
            "position": 95,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["pos_item_map"],
        "session_keys": [],
        "abilities": [
            "Map POS menu items to inventory item keys",
            "Flag items as chargeable (Chargeable Principle)",
            "Seed from compare product lists.txt",
            "Add, edit, and delete mappings manually",
            "Auto-match inventory descriptions to keys",
        ],
        "permissions": {"min_role": "editor"},
    }

    DOCS = {
        "summary": "POS ↔ Inventory mapping table — links POS menu item names to "
                   "inventory keys for count reconciliation.",
        "usage":   "Click 'Seed from source file' to load the initial mapping. "
                   "Use Auto-match to resolve inventory keys. Edit manually as needed.",
        "demo_ready": False,
        "notes":   "Source file: docs/compare product lists.txt. "
                   "* prefix = chargeable, ~ prefix = inventory description.",
        "known_issues": [],
        "changelog": [
            {"version": "1.0.0", "date": "2026-03-27", "note": "Initial implementation (F-037)."},
        ],
    }

    def on_load(self) -> None:
        try:
            self.db.ensure_pos_item_map_table()
        except Exception:
            pass

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**🗺️ POS Mapping**")
            try:
                rows = self.db.get_pos_item_map()
                mapped   = sum(1 for r in rows if r.get("inventory_key"))
                st.caption(f"{len(rows)} entries · {mapped} mapped to inventory")
            except Exception:
                st.caption("Loading…")

    def render(self) -> None:
        st.title("🗺️ POS ↔ Inventory Mapping")
        st.caption(
            "Links POS menu item names to inventory item keys. "
            "★ Chargeable items are tracked under the Chargeable Principle."
        )

        # ── Action bar ────────────────────────────────────────────────────────
        ac1, ac2, ac3 = st.columns(3)

        if ac1.button("🌱 Seed from source file", key="pos_seed",
                      help="Load initial mappings from docs/compare product lists.txt"):
            seeded, skipped = self._seed_from_file()
            if seeded or skipped:
                st.success(f"Seeded {seeded} entries ({skipped} already existed).")
                st.rerun()
            else:
                st.warning("Source file not found or empty.")

        if ac2.button("🔗 Auto-match inventory keys", key="pos_automatch",
                      help="Match inventory_description to actual item keys via exact then fuzzy search"):
            matched = self._auto_match_keys()
            st.success(f"Auto-matched {matched} entry/entries.")
            st.rerun()

        rows = self.db.get_pos_item_map()

        # ── Summary metrics ───────────────────────────────────────────────────
        total      = len(rows)
        mapped     = sum(1 for r in rows if r.get("inventory_key"))
        chargeable = sum(1 for r in rows if r.get("is_chargeable"))
        unmapped   = total - mapped

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total POS Items", total)
        m2.metric("Mapped to Inventory", mapped)
        m3.metric("Chargeable ★", chargeable)
        m4.metric("Unmapped", unmapped,
                  delta=f"-{unmapped}" if unmapped else None,
                  delta_color="inverse")

        st.markdown("---")

        # ── Mapping table ─────────────────────────────────────────────────────
        if not rows:
            st.info("No mappings yet — click 🌱 Seed from source file to begin.")
        else:
            filter_opts = st.radio(
                "Show", ["All", "Mapped only", "Unmapped only", "Chargeable only"],
                horizontal=True, key="pos_filter",
            )
            display = rows
            if filter_opts == "Mapped only":
                display = [r for r in rows if r.get("inventory_key")]
            elif filter_opts == "Unmapped only":
                display = [r for r in rows if not r.get("inventory_key")]
            elif filter_opts == "Chargeable only":
                display = [r for r in rows if r.get("is_chargeable")]

            st.dataframe(
                pd.DataFrame([{
                    "★":              "★" if r.get("is_chargeable") else "",
                    "POS Item":       r["pos_item_name"],
                    "Inventory Key":  r.get("inventory_key") or "—",
                    "Inv Description":r.get("inventory_description") or "—",
                    "Notes":          r.get("notes") or "",
                } for r in display]),
                use_container_width=True,
                hide_index=True,
            )

            # ── Per-row edit / delete ──────────────────────────────────────
            with st.expander("✏️ Edit or Delete a mapping"):
                sel_name = st.selectbox(
                    "Select POS item", [r["pos_item_name"] for r in rows],
                    key="pos_edit_sel",
                )
                sel = next((r for r in rows if r["pos_item_name"] == sel_name), None)
                if sel:
                    with st.form("pos_edit_form"):
                        e1, e2 = st.columns(2)
                        new_key  = e1.text_input("Inventory Key",
                                                  value=sel.get("inventory_key") or "")
                        new_desc = e2.text_input("Inventory Description",
                                                  value=sel.get("inventory_description") or "")
                        new_chg  = st.checkbox("Chargeable ★",
                                               value=bool(sel.get("is_chargeable")))
                        new_note = st.text_input("Notes", value=sel.get("notes") or "")

                        fc1, fc2 = st.columns(2)
                        if fc1.form_submit_button("💾 Save", type="primary"):
                            self.db.upsert_pos_mapping(
                                sel_name,
                                inventory_key=new_key.strip() or None,
                                inventory_description=new_desc.strip() or None,
                                is_chargeable=new_chg,
                                sort_order=sel.get("sort_order", 0),
                                notes=new_note.strip(),
                            )
                            st.success("Saved.")
                            st.rerun()
                        if fc2.form_submit_button("🗑️ Delete"):
                            self.db.delete_pos_mapping(sel_name)
                            st.success(f"Deleted: {sel_name}")
                            st.rerun()

        st.markdown("---")

        # ── Add new mapping ───────────────────────────────────────────────────
        st.subheader("➕ Add Mapping")
        with st.form("pos_add_form", clear_on_submit=True):
            a1, a2 = st.columns(2)
            new_pos  = a1.text_input("POS Item Name", placeholder="e.g. Hot Dog")
            new_key  = a2.text_input("Inventory Key", placeholder="e.g. HOT DOG||CASE")
            a3, a4   = st.columns(2)
            new_desc = a3.text_input("Inventory Description", placeholder="Optional")
            new_chg  = a4.checkbox("Chargeable ★", value=True)
            new_note = st.text_input("Notes", placeholder="Optional")

            if st.form_submit_button("➕ Add", type="primary"):
                if not new_pos.strip():
                    st.error("POS Item Name is required.")
                else:
                    ok = self.db.upsert_pos_mapping(
                        new_pos.strip(),
                        inventory_key=new_key.strip() or None,
                        inventory_description=new_desc.strip() or None,
                        is_chargeable=new_chg,
                        notes=new_note.strip(),
                    )
                    if ok:
                        st.success(f"Added: {new_pos.strip()}")
                        st.rerun()
                    else:
                        st.error("Save failed — check logs.")

    # ── Seed from source file ─────────────────────────────────────────────────

    def _seed_from_file(self):
        if not _SOURCE_FILE.exists():
            return 0, 0

        seeded = skipped = 0
        existing = {r["pos_item_name"] for r in self.db.get_pos_item_map()}

        for sort_order, raw in enumerate(_SOURCE_FILE.read_text(encoding="utf-8").splitlines()):
            line = raw.strip()
            if not line:
                continue

            is_chargeable = line.startswith("*")
            line = line.lstrip("*").strip()

            # Split on ~ to get POS name and inventory description
            if "~" in line:
                parts = line.split("~", 1)
                pos_name  = re.sub(r'\s+', ' ', parts[0]).strip()
                inv_desc  = re.sub(r'\s+', ' ', parts[1]).strip()
            else:
                pos_name  = re.sub(r'\s+', ' ', line).strip()
                inv_desc  = None

            if not pos_name:
                continue

            if pos_name in existing:
                skipped += 1
                continue

            self.db.upsert_pos_mapping(
                pos_name,
                inventory_key=None,
                inventory_description=inv_desc,
                is_chargeable=is_chargeable,
                sort_order=sort_order,
            )
            seeded += 1

        return seeded, skipped

    # ── Auto-match inventory keys ─────────────────────────────────────────────

    def _auto_match_keys(self) -> int:
        rows = self.db.get_pos_item_map()
        unmapped = [r for r in rows if not r.get("inventory_key")
                    and r.get("inventory_description")]
        if not unmapped:
            return 0

        all_items = self.db.get_all_items("active")
        # Build description → key lookup (normalized)
        desc_map = {
            re.sub(r'[^A-Z0-9 ]', '', (i.get("description") or "").upper()): i["key"]
            for i in all_items
        }

        matched = 0
        for row in unmapped:
            needle = re.sub(r'[^A-Z0-9 ]', '',
                            (row["inventory_description"] or "").upper())
            if needle in desc_map:
                self.db.upsert_pos_mapping(
                    row["pos_item_name"],
                    inventory_key=desc_map[needle],
                    inventory_description=row["inventory_description"],
                    is_chargeable=row.get("is_chargeable", True),
                    sort_order=row.get("sort_order", 0),
                    notes=row.get("notes", ""),
                )
                matched += 1
            else:
                # Fuzzy fallback
                try:
                    from rapidfuzz import process as rfp
                    result = rfp.extractOne(needle, list(desc_map.keys()),
                                           score_cutoff=88)
                    if result:
                        best_desc, score, _ = result
                        self.db.upsert_pos_mapping(
                            row["pos_item_name"],
                            inventory_key=desc_map[best_desc],
                            inventory_description=row["inventory_description"],
                            is_chargeable=row.get("is_chargeable", True),
                            sort_order=row.get("sort_order", 0),
                            notes=f"fuzzy match ({score:.0f}%)",
                        )
                        matched += 1
                except ImportError:
                    pass

        return matched


# ── end of PosMapDashboard ────────────────────────────────────────────────────
