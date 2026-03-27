# ──────────────────────────────────────────────────────────────────────────────
#  modules/overrides_dashboard.py  —  Count Override Rule Manager
#  v1.0.0
#
#  Manages per-item count multiplier rules for items with non-standard
#  pack ratios (e.g. tray items where the count sheet reports 1/1000 packs
#  but the actual unit quantity is 6, 12, or 24× higher).
#
#  Known required rules (MOG tray items):
#    1LB TRAY||1/1000   → ×12
#    2LB TRAY||1/1000   → ×6
#    3LB TRAY||1/500    → ×24
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
from base import Dashboard

try:
    import auth as _auth
    def _get_changed_by(): return _auth.get_changed_by()
except Exception:
    def _get_changed_by(): return "web_user"


class OverridesDashboard(Dashboard):

    MANIFEST = {
        "id":       "overrides",
        "label":    "Count Overrides",
        "version":  "1.0.0",
        "icon":     "✏️",
        "status":   "active",
        "page_key": "overrides",
        "menu": {
            "parent":   "Tools",
            "label":    "Count Overrides",
            "shortcut": "O",
            "position": 90,
        },
        "sidebar": {
            "section":  "",
            "position": 90,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["count_overrides", "count_override_settings"],
        "session_keys": [],
        "abilities": [
            "Manage per-item count quantity multiplier rules",
            "Enable/disable global override system",
            "Add, edit, toggle, and delete override rules",
            "Pre-seeded with known MOG tray item rules",
        ],
        "permissions": {"min_role": "editor"},
    }

    DOCS = {
        "summary": "Count Override Rule Manager — fixes items whose count-sheet pack "
                   "ratios don't match actual inventory units (e.g. MOG tray items).",
        "usage":   "Enable overrides globally, then add rules per item_key. "
                   "Rules are applied automatically during count import.",
        "demo_ready": False,
        "notes":   "item_key format: DESCRIPTION||PACK_TYPE (uppercase, double-pipe). "
                   "multiplier: the count quantity is multiplied by this value.",
        "known_issues": [],
        "changelog": [
            {"version": "1.0.0", "date": "2026-03-27", "note": "Initial implementation (F-031)."},
        ],
    }

    _SEED_RULES = [
        {"item_key": "1LB TRAY||1/1000",  "multiplier": 12.0,
         "reason": "MOG tray — 12 units per pack"},
        {"item_key": "2LB TRAY||1/1000",  "multiplier": 6.0,
         "reason": "MOG tray — 6 units per pack"},
        {"item_key": "3LB TRAY||1/500",   "multiplier": 24.0,
         "reason": "MOG tray — 24 units per pack"},
    ]

    def on_load(self) -> None:
        try:
            self.db.ensure_count_override_tables()
        except Exception:
            pass

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**✏️ Count Overrides**")
            try:
                rules = self.db.get_count_overrides(active_only=False)
                active = sum(1 for r in rules if r.get("active"))
                enabled = self.db.get_override_settings_enabled()
                st.caption(
                    f"{'🟢 Enabled' if enabled else '🔴 Disabled'} · "
                    f"{active} active rule(s)"
                )
            except Exception:
                st.caption("Loading…")

    def render(self) -> None:
        st.title("✏️ Count Override Rules")
        st.caption(
            "Items where the count sheet pack size doesn't match actual inventory units. "
            "The count quantity is multiplied by the rule's factor before committing to the database."
        )

        # ── Global enable toggle ───────────────────────────────────────────────
        try:
            enabled = self.db.get_override_settings_enabled()
        except Exception:
            enabled = True

        col_tog, col_seed = st.columns([2, 1])
        new_enabled = col_tog.toggle(
            "Override system enabled",
            value=enabled,
            key="overrides_global_toggle",
            help="When disabled, all override rules are skipped during count import.",
        )
        if new_enabled != enabled:
            self.db.set_override_settings_enabled(new_enabled)
            st.rerun()

        if col_seed.button("🌱 Seed known rules", key="overrides_seed",
                           help="Add the three known MOG tray item rules"):
            seeded = 0
            for rule in self._SEED_RULES:
                if self.db.upsert_count_override(
                    rule["item_key"], rule["multiplier"],
                    reason=rule["reason"], created_by=_get_changed_by()
                ):
                    seeded += 1
            st.success(f"Seeded {seeded} rule(s).")
            st.rerun()

        st.markdown("---")

        # ── Existing rules table ───────────────────────────────────────────────
        try:
            rules = self.db.get_count_overrides(active_only=False)
        except Exception as exc:
            st.error(f"Could not load overrides: {exc}")
            return

        if not rules:
            st.info("No override rules defined yet. Use 🌱 Seed known rules or add one below.")
        else:
            st.subheader(f"📋 {len(rules)} Rule(s)")

            for rule in rules:
                key    = rule["item_key"]
                mult   = float(rule.get("multiplier", 1))
                reason = rule.get("reason", "")
                active = rule.get("active", True)

                with st.container():
                    rc1, rc2, rc3, rc4, rc5 = st.columns([3, 1, 2, 1, 1])

                    rc1.markdown(
                        f"<div style='font-family:monospace;font-size:12px;"
                        f"padding-top:6px'>{key}</div>",
                        unsafe_allow_html=True,
                    )
                    rc2.markdown(
                        f"<div style='font-size:18px;font-weight:800;"
                        f"color:#3b82f6;padding-top:4px;text-align:center'>"
                        f"×{mult:g}</div>",
                        unsafe_allow_html=True,
                    )
                    rc3.caption(reason or "—")

                    # Toggle active
                    if rc4.button(
                        "🟢 Active" if active else "🔴 Off",
                        key=f"ovr_tog_{key}",
                        help="Click to toggle",
                        use_container_width=True,
                    ):
                        self.db.toggle_count_override(key, not active)
                        st.rerun()

                    # Delete
                    if rc5.button("🗑️", key=f"ovr_del_{key}",
                                  help=f"Delete rule for {key}"):
                        self.db.delete_count_override(key)
                        st.rerun()

                st.divider()

        # ── Add new rule ───────────────────────────────────────────────────────
        st.subheader("➕ Add / Update Rule")
        st.caption(
            "item_key format: `DESCRIPTION||PACK_TYPE` — must match exactly what appears "
            "in the count sheet (uppercase, double-pipe separator)."
        )

        with st.form("add_override_form", clear_on_submit=True):
            fc1, fc2 = st.columns([3, 1])
            new_key  = fc1.text_input(
                "Item Key",
                placeholder="e.g. 1LB TRAY||1/1000",
                help="DESCRIPTION||PACK_TYPE — uppercase, exact match",
            )
            new_mult = fc2.number_input(
                "Multiplier", value=1.0, min_value=0.01,
                step=1.0, format="%.2f",
                help="Count qty will be multiplied by this value",
            )
            new_reason = st.text_input(
                "Reason / Note",
                placeholder="e.g. MOG tray — 12 units per pack",
            )

            if st.form_submit_button("💾 Save Rule", type="primary"):
                if not new_key.strip():
                    st.error("Item key is required.")
                elif new_mult <= 0:
                    st.error("Multiplier must be > 0.")
                else:
                    ok = self.db.upsert_count_override(
                        new_key, new_mult,
                        reason=new_reason,
                        created_by=_get_changed_by(),
                    )
                    if ok:
                        st.success(f"Rule saved: {new_key.upper()} × {new_mult:g}")
                        st.rerun()
                    else:
                        st.error("Save failed — check logs.")

        # ── How it works ──────────────────────────────────────────────────────
        with st.expander("ℹ️ How count overrides work"):
            st.markdown("""
**Problem:** Some items (like MOG tray meats) are sold in packs where the count sheet
reports a weight-based unit (`1/1000`) but the actual countable unit is a whole tray.

**Example:** `1LB TRAY||1/1000` with multiplier `12`
- Count sheet reports: `5` cases
- After override: `5 × 12 = 60` units committed to inventory

**When are overrides applied?**
- Automatically during **Count Import** (file upload)
- Automatically during **Count Entry** commit (manual entry)
- The multiplied value is what gets written to `quantity_on_hand`

**item_key format:**
```
DESCRIPTION||PACK_TYPE
```
Must be uppercase, exactly as it appears in the raw count data.
Use the Count Import page to see what keys are parsed from your files.
""")


# ── end of OverridesDashboard ─────────────────────────────────────────────────
