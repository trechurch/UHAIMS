# ──────────────────────────────────────────────────────────────────────────────
#  modules/gl_dashboard.py  —  GL Code Manager Dashboard
#  v2.0.0  —  Bulk assign, upload mapping, cost center assignment, auto-assign
# ──────────────────────────────────────────────────────────────────────────────

import io
import pandas as pd
import streamlit as st
from base import Dashboard

try:
    import auth as _auth
    def _get_changed_by():
        return _auth.get_changed_by()
except Exception:
    def _get_changed_by():
        return "web_user"


class GLDashboard(Dashboard):

    MANIFEST = {
        "id":       "gl_dashboard",
        "label":    "GL Codes",
        "version":  "2.0.0",
        "icon":     "🏷️",
        "status":   "active",
        "page_key": "gl_codes",
        "menu": {
            "parent":   "Tools",
            "label":    "GL Code Manager",
            "shortcut": "G",
            "position": 10,
        },
        "sidebar": {
            "section":  "Tools",
            "position": 10,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["items", "item_history"],
        "session_keys": ["gl_selected_keys"],
        "abilities": [
            "Bulk assign cost center to all untagged items",
            "Bulk assign GL code to selected items by description filter",
            "Upload a CSV mapping file (description → GL code)",
            "Auto-assign GL codes via fuzzy matching",
            "View GL coverage stats",
        ],
        "permissions": {"min_role": "editor"},
    }

    DOCS = {
        "summary": "Bulk GL code and cost center assignment for inventory items.",
        "usage": (
            "1. Admin tab: assign cost center to all untagged items.  "
            "2. Bulk Assign tab: filter items by keyword, select, assign GL code.  "
            "3. Upload Mapping tab: upload a CSV to batch-assign GL codes.  "
            "4. Auto-Assign tab: fuzzy-match once some GL codes are seeded."
        ),
        "demo_ready": True,
        "notes": "v2.0.0: full rebuild with bulk operations replacing single-item flow.",
        "known_issues": [],
        "changelog": [
            {"version": "2.0.0", "date": "2026-03-26",
             "note": "Bulk assign, cost center admin, upload mapping, auto-assign."},
            {"version": "1.0.0", "date": "2026-03-25",
             "note": "Initial migration."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        if "gl_selected_keys" not in st.session_state:
            st.session_state["gl_selected_keys"] = []

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**🏷️ GL Codes**")
            st.caption("Bulk assign · fuzzy match")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.title("🏷️ GL Code Manager")

        items = self.db.get_all_items("active")
        total      = len(items)
        has_gl     = sum(1 for i in items if i.get("gl_code"))
        has_cc     = sum(1 for i in items if i.get("cost_center"))
        no_gl      = total - has_gl
        no_cc      = total - has_cc

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Items",      total)
        c2.metric("With GL Code",     has_gl,
                  delta=f"{no_gl} missing", delta_color="inverse")
        c3.metric("With Cost Center", has_cc,
                  delta=f"{no_cc} missing", delta_color="inverse")
        c4.metric("GL Coverage",
                  f"{has_gl/total*100:.0f}%" if total else "—")

        st.markdown("---")

        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "🏢 Cost Center", "📁 GL Lists Import",
            "🏷️ Bulk GL Assign", "📂 Upload Mapping",
            "🤖 Auto-Assign", "✏️ Manual Entry",
        ])

        with tab1:
            self._tab_cost_center(no_cc, total)
        with tab2:
            self._tab_gl_lists()
        with tab3:
            self._tab_bulk_gl(items)
        with tab4:
            self._tab_upload_mapping()
        with tab5:
            self._tab_auto_assign()
        with tab6:
            self._tab_manual_entry()

    # ── Tab 2: GL Lists Import ────────────────────────────────────────────────

    def _tab_gl_lists(self) -> None:
        from gl_lists_importer import (
            scan_gl_lists_folder, assign_gl_codes,
            import_as_master, GL_LISTS_DIR,
        )

        st.subheader("📁 GL Lists Import")
        st.caption(f"Reading from: `{GL_LISTS_DIR}`")

        categories = scan_gl_lists_folder()
        if not categories:
            st.error(
                f"No GL list files found in `{GL_LISTS_DIR}`. "
                "Make sure the 'GL Lists' folder is in the repo root."
            )
            return

        # ── Summary table ─────────────────────────────────────────────────────
        summary_df = pd.DataFrame([{
            "GL Name":   c["gl_name"],
            "GL Code":   c["gl_code"],
            "Items":     len(c["items"]),
        } for c in categories])
        total_items = summary_df["Items"].sum()

        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("GL Categories", len(categories))
        cc2.metric("Total Items in Files", f"{total_items:,}")
        cc3.metric("Already in DB", self.db.count_items())

        st.dataframe(summary_df, use_container_width=True,
                     hide_index=True, height=min(400, 35*len(categories)+38))

        st.markdown("---")

        # ── Mode selector ─────────────────────────────────────────────────────
        mode = st.radio(
            "What do you want to do?",
            [
                "🏷️  Assign GL codes to existing items (fuzzy description match)",
                "📦  Import as master list (add all items, blank quantities)",
            ],
            key="gl_lists_mode",
        )

        # ── Shared options ────────────────────────────────────────────────────
        CC_OPTIONS = {
            "57230 — Overhead":             "57230",
            "57231 — TDECU Concessions":    "57231",
            "57232 — Warehouse / Fertitta": "57232",
            "57233 — Schroeder Park":       "57233",
            "57234 — Softball Stadium":     "57234",
            "57235 — Team Dining":          "57235",
            "57236 — Catering":             "57236",
        }

        if mode.startswith("🏷️"):
            # ── Assign GL codes ───────────────────────────────────────────────
            st.markdown("**Match existing inventory descriptions to GL list items.**")
            st.caption(
                "Uses fuzzy string matching. Items whose descriptions score "
                "above the threshold get their GL code updated."
            )
            threshold = st.slider(
                "Match confidence threshold (higher = stricter)",
                50, 95, 72, key="gl_lists_threshold",
            )
            only_unset = st.checkbox(
                "Only update items that have no GL code yet",
                value=True, key="gl_lists_only_unset",
            )

            st.markdown(
                "**Phase 1** (Exact) and **Phase 2** (Fuzzy ≥ threshold) are auto-committed.  \n"
                "**Phase 3** (Probabilistic) and Unmatched items open in **Match Review** for manual decisions."
            )

            btn_col, info_col = st.columns([1, 2])
            with btn_col:
                run_match = st.button("🚀 Run Matching Passes",
                                      key="gl_lists_run_match", type="primary")
            with info_col:
                pending = st.session_state.get("match_review_session")
                if pending:
                    stats = pending.get("stats", {})
                    n_pending = (len(pending.get("probabilistic", []))
                                 + len(pending.get("unmatched", [])))
                    st.info(
                        f"Active session: **{stats.get('auto_assigned',0)}** auto-assigned · "
                        f"**{n_pending}** awaiting review"
                    )

            if run_match:
                with st.spinner("Running 3-pass match engine…"):
                    result = assign_gl_codes(
                        self.db, categories,
                        min_score=threshold,
                        changed_by=_get_changed_by(),
                        only_unassigned=only_unset,
                    )
                # Store session for review dashboard
                st.session_state["match_review_session"]   = result
                st.session_state["match_review_decisions"] = {}
                st.session_state["match_review_cursor"]    = 0

                stats = result["stats"]
                n_review = (len(result.get("probabilistic", []))
                            + len(result.get("unmatched", [])))

                st.success(
                    f"✅ Auto-assigned: **{result['assigned']}** "
                    f"(exact: {stats.get('exact',0)} · fuzzy: {stats.get('fuzzy',0)})"
                )
                if result["matches"]:
                    with st.expander(f"📋 {len(result['matches'])} auto-assigned matches"):
                        st.dataframe(
                            pd.DataFrame(result["matches"])[
                                ["item", "matched_to", "score", "gl_code", "gl_name", "phase"]
                            ],
                            use_container_width=True, hide_index=True, height=300,
                        )

                if n_review:
                    st.warning(
                        f"**{n_review} items need manual review** "
                        f"({stats.get('probabilistic',0)} probabilistic · "
                        f"{stats.get('unmatched',0)} unmatched)."
                    )
                    st.page_link("?page=match_review",
                                 label="🔍 Open Match Review →",
                                 help="Review low-confidence matches with degree-of-comparison scoring")
                else:
                    st.success("All items matched — no manual review needed!")

        else:
            # ── Import as master list ─────────────────────────────────────────
            st.markdown("**Import every item from every GL file into the database.**")
            st.caption(
                "Items with duplicate descriptions (same generated key) are skipped "
                "by default. Quantities are left at 0."
            )

            cc_label  = st.selectbox(
                "Tag all imported items to cost center",
                list(CC_OPTIONS.keys()), index=1,
                key="gl_lists_cc",
            )
            cc_code   = CC_OPTIONS[cc_label]
            skip_dup  = st.checkbox(
                "Skip items already in the database (recommended)",
                value=True, key="gl_lists_skip_dup",
            )

            st.info(
                f"This will attempt to add up to **{total_items:,}** items "
                f"tagged to **{cc_label}** with GL codes pre-assigned. "
                "Prices from the GL files will be used as the initial cost."
            )

            confirmed = st.checkbox(
                f"Confirm: import up to {total_items:,} items",
                key="gl_lists_import_confirm",
            )
            if st.button("📦 Import Master List", type="primary",
                         disabled=not confirmed, key="gl_lists_import_go"):
                with st.spinner(f"Importing up to {total_items:,} items…"):
                    result = import_as_master(
                        self.db, categories,
                        cost_center=cc_code,
                        changed_by=_get_changed_by(),
                        skip_existing=skip_dup,
                    )
                st.success(
                    f"✅ Added: **{result['added']:,}**  ·  "
                    f"Updated: **{result['updated']:,}**  ·  "
                    f"Skipped: **{result['skipped']:,}**"
                )
                if result["errors"]:
                    with st.expander(f"⚠️ {len(result['errors'])} errors"):
                        for e in result["errors"]:
                            st.caption(e)
                st.rerun()

    # ── Tab 1: Cost Center ────────────────────────────────────────────────────

    def _tab_cost_center(self, no_cc: int, total: int) -> None:
        st.subheader("Bulk Cost Center Assignment")

        CC_OPTIONS = {
            "57230 — Overhead":             "57230",
            "57231 — TDECU Concessions":    "57231",
            "57232 — Warehouse / Fertitta": "57232",
            "57233 — Schroeder Park":       "57233",
            "57234 — Softball Stadium":     "57234",
            "57235 — Team Dining":          "57235",
            "57236 — Catering":             "57236",
        }

        cc_label = st.selectbox("Assign to cost center",
                                list(CC_OPTIONS.keys()),
                                index=1, key="gl_cc_sel")
        cc_code  = CC_OPTIONS[cc_label]

        mode = st.radio(
            "Which items",
            ["Only items with no cost center set",
             "All active items (overwrite existing)"],
            key="gl_cc_mode",
        )
        only_unset = mode.startswith("Only")

        affected = no_cc if only_unset else total
        st.caption(f"This will update **{affected}** item(s).")

        confirmed = st.checkbox(
            f"Confirm: assign {affected} item(s) to {cc_label}",
            key="gl_cc_confirm",
        )
        if st.button("✅ Assign Cost Center", type="primary",
                     disabled=not confirmed, key="gl_cc_apply"):
            count = self.db.bulk_update_cost_center(cc_code, only_unset=only_unset)
            st.success(f"✅ {count} item(s) assigned to **{cc_label}**.")
            st.rerun()

    # ── Tab 2: Bulk GL Assign ─────────────────────────────────────────────────

    def _tab_bulk_gl(self, items: list) -> None:
        st.subheader("Bulk GL Code Assignment")
        st.caption(
            "Filter the list, select items, then assign a GL code to all selected at once."
        )

        # ── Filter bar ────────────────────────────────────────────────────────
        fc1, fc2, fc3 = st.columns([3, 2, 2])
        keyword   = fc1.text_input("Filter by description keyword",
                                    placeholder="e.g. BEEF, PAPER, BEER…",
                                    key="gl_kw")
        show_only = fc2.selectbox("Show",
                                   ["All items", "Missing GL only",
                                    "Already has GL"],
                                   key="gl_show")
        vendor_f  = fc3.selectbox(
            "Vendor",
            ["All"] + sorted({i.get("vendor") or "" for i in items
                               if i.get("vendor")}),
            key="gl_vendor",
        )

        filtered = items
        if keyword:
            kw = keyword.upper()
            filtered = [i for i in filtered
                        if kw in (i.get("description") or "").upper()]
        if show_only == "Missing GL only":
            filtered = [i for i in filtered if not i.get("gl_code")]
        elif show_only == "Already has GL":
            filtered = [i for i in filtered if i.get("gl_code")]
        if vendor_f != "All":
            filtered = [i for i in filtered if i.get("vendor") == vendor_f]

        if not filtered:
            st.info("No items match the current filter.")
            return

        # ── Item table with row selection ─────────────────────────────────────
        df = pd.DataFrame([{
            "Description": (i.get("description") or "")[:50],
            "Pack":        (i.get("pack_type") or "")[:14],
            "Vendor":      (i.get("vendor") or "")[:20],
            "GL Code":     i.get("gl_code") or "—",
            "GL Name":     (i.get("gl_name") or "")[:24],
            "_key":        i["key"],
        } for i in filtered])

        event = st.dataframe(
            df.drop(columns=["_key"]),
            use_container_width=True,
            hide_index=True,
            height=min(600, 35 * len(df) + 38),
            on_select="rerun",
            selection_mode=["multi-row"],
            key="gl_table",
        )

        sel_rows = []
        try:
            sel_rows = event.selection.rows
        except Exception:
            pass

        selected_keys = [df.iloc[i]["_key"] for i in sel_rows]
        st.caption(
            f"{len(filtered)} items shown  ·  {len(selected_keys)} selected"
        )

        if not selected_keys:
            st.info("Select rows above, then assign a GL code below.")
            return

        # ── GL assignment form ────────────────────────────────────────────────
        st.markdown("---")

        # Quick-pick: catalog codes first, then codes already in items table
        _catalog_codes = {
            f"{c['gl_code']} — {c.get('gl_name','')}"
            for c in self.db.get_gl_catalog()
        }
        _item_codes = {
            f"{i['gl_code']} — {i.get('gl_name','')}"
            for i in self.db.get_all_items()
            if i.get("gl_code")
        }
        existing_codes = sorted(_catalog_codes | _item_codes)

        with st.form("gl_assign_form"):
            ac1, ac2 = st.columns(2)
            if existing_codes:
                quick = ac1.selectbox(
                    "Quick-pick existing GL code",
                    ["— type manually below —"] + existing_codes,
                    key="gl_quick",
                )
            else:
                quick = "— type manually below —"

            gl_code_input = ac2.text_input("GL Code (6 digits)", max_chars=10,
                                            key="gl_code_in")
            gl_name_input = st.text_input("GL Name / Category",
                                           placeholder="e.g. Food — Beef & Pork",
                                           key="gl_name_in")

            submitted = st.form_submit_button(
                f"🏷️ Assign to {len(selected_keys)} item(s)", type="primary"
            )

        if submitted:
            # Resolve final GL code + name
            if quick and not quick.startswith("—"):
                parts     = quick.split(" — ", 1)
                final_code = parts[0].strip()
                final_name = parts[1].strip() if len(parts) > 1 else ""
            else:
                final_code = gl_code_input.strip()
                final_name = gl_name_input.strip()

            if not final_code:
                st.error("Enter a GL code.")
            else:
                count = self.db.bulk_update_gl(
                    selected_keys, final_code, final_name,
                    changed_by=_get_changed_by(),
                )
                st.success(
                    f"✅ Assigned GL **{final_code} — {final_name}** "
                    f"to **{count}** item(s)."
                )
                st.rerun()

    # ── Tab 3: Upload Mapping ─────────────────────────────────────────────────

    def _tab_upload_mapping(self) -> None:
        st.subheader("Upload GL Mapping File")
        st.caption(
            "Upload a CSV or XLSX with at least two columns: "
            "**Description** (or item name) and **GL Code** "
            "(optionally a **GL Name** column too). "
            "Items are matched by exact description. "
            "A template is available below."
        )

        # Download template
        template_df = pd.DataFrame([
            {"Description": "BEEF GROUND 80/20 4/10# CS",
             "GL Code": "411048", "GL Name": "Food — Beef & Pork"},
            {"Description": "PAPER BOAT 8OZ",
             "GL Code": "411052", "GL Name": "Paper & Disposables"},
        ])
        buf = io.BytesIO()
        template_df.to_csv(buf, index=False)
        st.download_button("⬇️ Download Template CSV", data=buf.getvalue(),
                           file_name="gl_mapping_template.csv",
                           mime="text/csv", key="gl_tmpl_dl")

        uploaded = st.file_uploader("Upload mapping file",
                                     type=["csv", "xlsx", "xls"],
                                     key="gl_upload")
        if not uploaded:
            return

        try:
            if uploaded.name.endswith((".xlsx", ".xls")):
                df = pd.read_excel(uploaded)
            else:
                import chardet
                raw = uploaded.read()
                enc = chardet.detect(raw)["encoding"] or "utf-8"
                df = pd.read_csv(io.BytesIO(raw), encoding=enc)
        except Exception as exc:
            st.error(f"Could not read file: {exc}")
            return

        # Detect columns
        cols_lower = {c.lower().strip(): c for c in df.columns}
        desc_col = next(
            (cols_lower[k] for k in cols_lower
             if "desc" in k or "item" in k or "name" in k), None
        )
        gl_code_col = next(
            (cols_lower[k] for k in cols_lower
             if "gl code" in k or "gl_code" in k or k == "gl"), None
        )
        gl_name_col = next(
            (cols_lower[k] for k in cols_lower
             if "gl name" in k or "gl_name" in k
             or "category" in k), None
        )

        if not desc_col or not gl_code_col:
            st.error(
                f"Could not detect Description and GL Code columns. "
                f"Found: {list(df.columns)}"
            )
            return

        st.caption(
            f"Detected — Description: `{desc_col}` · "
            f"GL Code: `{gl_code_col}` · "
            f"GL Name: `{gl_name_col or 'not found'}`"
        )
        st.dataframe(df.head(5), use_container_width=True, hide_index=True)

        # Build lookup: UPPER(description) → (gl_code, gl_name)
        mapping = {}
        for _, row in df.iterrows():
            desc    = str(row.get(desc_col, "") or "").strip().upper()
            gl_code = str(row.get(gl_code_col, "") or "").strip()
            gl_name = str(row.get(gl_name_col, "") or "").strip() if gl_name_col else ""
            if desc and gl_code:
                mapping[desc] = (gl_code, gl_name)

        st.caption(f"{len(mapping)} mapping rows loaded.")

        if st.button("📥 Apply Mapping to Inventory", type="primary",
                     key="gl_upload_apply"):
            items   = self.db.get_all_items("active")
            matched = 0
            for item in items:
                desc = (item.get("description") or "").strip().upper()
                if desc in mapping:
                    gl_code, gl_name = mapping[desc]
                    self.db.bulk_update_gl(
                        [item["key"]], gl_code, gl_name,
                        changed_by=_get_changed_by(),
                    )
                    matched += 1
            st.success(
                f"✅ Matched and updated **{matched}** of "
                f"**{len(items)}** items."
            )
            if len(items) - matched:
                st.info(
                    f"{len(items) - matched} items had no matching "
                    f"description in the file."
                )

    # ── Tab 4: Auto-Assign ────────────────────────────────────────────────────

    def _tab_auto_assign(self) -> None:
        st.subheader("Auto-Assign via Fuzzy Matching")
        st.caption(
            "Uses GL codes already in the database as training examples. "
            "Works best after some items have been assigned manually or via upload."
        )

        try:
            from gl_manager import GLCodeManager
            gl = GLCodeManager(self.db)
        except Exception as exc:
            st.error(f"GL Manager failed to load: {exc}")
            return

        summary = gl.get_gl_summary()
        if not summary:
            st.warning(
                "No GL mappings available yet. "
                "Assign some GL codes first (Bulk Assign or Upload tabs) "
                "so the matcher has examples to learn from."
            )
            return

        st.dataframe(
            pd.DataFrame(summary),
            use_container_width=True, hide_index=True,
        )

        confidence = st.slider("Minimum confidence", 0.4, 0.95, 0.70,
                               key="gl_confidence")
        unassigned = sum(1 for i in self.db.get_all_items("active")
                         if not i.get("gl_code"))
        st.caption(f"{unassigned} items currently have no GL code.")

        if st.button("🤖 Auto-Assign to Unassigned Items",
                     type="primary", key="gl_auto_assign"):
            with st.spinner("Matching…"):
                results = gl.assign_gl_codes_to_items(min_confidence=confidence)
            st.success(
                f"Assigned: **{results['assigned']}** · "
                f"Skipped (already set): **{results['skipped']}** · "
                f"No match: **{results['failed']}**"
            )
            if results.get("assignments"):
                st.dataframe(
                    pd.DataFrame(results["assignments"])[
                        ["gl_code", "gl_name", "confidence"]
                    ],
                    use_container_width=True, hide_index=True,
                )

    # ── Tab 6: Manual Entry ───────────────────────────────────────────────────

    def _tab_manual_entry(self) -> None:
        st.subheader("✏️ GL Code Catalog")
        st.caption(
            "Register GL codes and names here — they'll appear in the Quick-pick "
            "dropdown in Bulk GL Assign without needing items assigned first."
        )

        # ── Add / Update form ─────────────────────────────────────────────────
        with st.form("gl_catalog_form", clear_on_submit=True):
            mc1, mc2 = st.columns([1, 3])
            gl_code  = mc1.text_input("GL Code *", max_chars=12, placeholder="411048")
            gl_name  = mc2.text_input("GL Name *", placeholder="Food — Beef & Pork")
            notes    = st.text_input("Notes (optional)",
                                     placeholder="Protein items, cost center 57231 typical")
            submitted = st.form_submit_button("➕ Add / Update", type="primary")

        if submitted:
            if not gl_code.strip() or not gl_name.strip():
                st.error("GL Code and GL Name are required.")
            else:
                if self.db.upsert_gl_code(gl_code.strip(), gl_name.strip(), notes.strip()):
                    st.success(f"✅ Saved **{gl_code.strip()} — {gl_name.strip()}**")
                    st.rerun()
                else:
                    st.error("Save failed — check logs.")

        # ── Catalog table ─────────────────────────────────────────────────────
        st.markdown("---")
        catalog = self.db.get_gl_catalog()
        if not catalog:
            st.info("No GL codes registered yet. Use the form above to add some.")
            return

        st.caption(f"{len(catalog)} registered code(s)")
        for entry in catalog:
            col_code, col_name, col_notes, col_del = st.columns([1, 3, 3, 1])
            col_code.markdown(f"`{entry['gl_code']}`")
            col_name.write(entry['gl_name'])
            col_notes.caption(entry.get('notes') or "—")
            if col_del.button("🗑️", key=f"gl_cat_del_{entry['gl_code']}",
                              help="Delete from catalog"):
                self.db.delete_gl_code(entry['gl_code'])
                st.rerun()


# ── end of GLDashboard ────────────────────────────────────────────────────────
