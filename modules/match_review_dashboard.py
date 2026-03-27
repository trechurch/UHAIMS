# ──────────────────────────────────────────────────────────────────────────────
#  modules/match_review_dashboard.py  —  Intelligent Inventory Matching Review
#  v1.0.0
#
#  Manual review interface for items that cleared no auto-match phase.
#  Displays Degrees of Comparison scores (Positive, Comparative, Superlative,
#  Probabilistic) for each candidate and lets the user accept, skip, or
#  manually enter a GL code before committing all decisions to the database.
#
#  Populated by GL Dashboard → "📁 GL Lists Import" → run matching passes.
#  Session data lives in st.session_state["match_review_session"].
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
from base import Dashboard

try:
    import auth as _auth
    def _get_changed_by(): return _auth.get_changed_by()
except Exception:
    def _get_changed_by(): return "web_user"

# ── Degree colour map ─────────────────────────────────────────────────────────
_DEGREE_COLOR = {
    "superlative":   "#22c55e",   # green
    "comparative":   "#3b82f6",   # blue
    "positive":      "#f59e0b",   # amber
    "probabilistic": "#ef4444",   # red
}
_DEGREE_ICON = {
    "superlative":   "🏆",
    "comparative":   "🔵",
    "positive":      "🟡",
    "probabilistic": "🔴",
}
_RANK_MEDAL = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

_PHASE_COLOR = {
    "exact":         "#22c55e",
    "fuzzy":         "#3b82f6",
    "probabilistic": "#f59e0b",
    "unmatched":     "#ef4444",
}


class MatchReviewDashboard(Dashboard):

    MANIFEST = {
        "id":       "match_review",
        "label":    "Match Review",
        "version":  "1.0.0",
        "icon":     "🔍",
        "status":   "active",
        "page_key": "match_review",
        "menu": {
            "parent":   "Tools",
            "label":    "Match Review",
            "shortcut": "M",
            "position": 85,
        },
        "sidebar": {
            "section":  "",
            "position": 85,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["items"],
        "session_keys": ["match_review_session", "match_review_decisions",
                         "match_review_cursor"],
        "abilities": [
            "Review unmatched / low-confidence item-to-GL-code assignments",
            "Displays Positive / Comparative / Superlative / Probabilistic scores",
            "Accept top candidate, choose from list, or manually enter GL code",
            "Commit all approved decisions to database in one operation",
            "Reusable for any multi-phase matching workflow",
        ],
        "permissions": {"min_role": "any"},
    }

    DOCS = {
        "summary": "Manual review UI for inventory matching. Shows degree-of-comparison "
                   "scores for each candidate match and lets operators accept or override.",
        "usage":   "Run GL Lists Import in the GL Dashboard first. Pending items are "
                   "stored in session state and reviewed here.",
        "demo_ready": False,
        "notes":   "Scores: Positive = token_set_ratio, Comparative = partial_ratio, "
                   "Superlative = WRatio, Probabilistic = weighted composite.",
        "known_issues": [],
        "changelog": [
            {"version": "1.0.0", "date": "2026-03-26", "note": "Initial implementation."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        if "match_review_decisions" not in st.session_state:
            st.session_state["match_review_decisions"] = {}
        if "match_review_cursor" not in st.session_state:
            st.session_state["match_review_cursor"] = 0

    def sidebar(self) -> None:
        with st.sidebar:
            session = st.session_state.get("match_review_session")
            if session:
                stats = session.get("stats", {})
                review_items = (session.get("probabilistic", [])
                                + session.get("unmatched", []))
                decisions = st.session_state.get("match_review_decisions", {})
                accepted  = sum(1 for d in decisions.values() if d["action"] == "accept")
                skipped   = sum(1 for d in decisions.values() if d["action"] == "skip")
                pending   = len(review_items) - len(decisions)
                st.markdown("**🔍 Match Review**")
                st.caption(
                    f"Auto-assigned: {stats.get('auto_assigned', 0)}  \n"
                    f"Accepted: {accepted}  ·  Skipped: {skipped}  ·  Pending: {pending}"
                )
            else:
                st.markdown("**🔍 Match Review**")
                st.caption("No active session.")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.title("🔍 Intelligent Inventory Matching")
        session = st.session_state.get("match_review_session")

        if not session:
            st.info(
                "No matching session active.  \n"
                "Go to **GL Dashboard → 📁 GL Lists Import** and run the matching passes first."
            )
            return

        stats       = session.get("stats", {})
        review_items = (session.get("probabilistic", [])
                       + session.get("unmatched", []))

        if not review_items:
            st.success(
                f"All {stats.get('auto_assigned', 0)} items were auto-assigned.  \n"
                "Nothing pending manual review."
            )
            self._render_commit_panel(session)
            return

        decisions = st.session_state["match_review_decisions"]

        # ── Summary bar ───────────────────────────────────────────────────────
        accepted = sum(1 for d in decisions.values() if d["action"] == "accept")
        skipped  = sum(1 for d in decisions.values() if d["action"] == "skip")
        pending  = len(review_items) - len(decisions)

        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("Auto-Assigned",  stats.get("auto_assigned", 0),
                   help="Exact + high-confidence fuzzy — committed automatically")
        mc2.metric("For Review",     len(review_items))
        mc3.metric("Accepted",       accepted,   delta=f"+{accepted}" if accepted else None)
        mc4.metric("Skipped",        skipped)
        mc5.metric("Pending",        pending,    delta_color="inverse",
                   delta=f"-{pending}" if pending else None)

        st.markdown("---")

        # ── Two-panel layout ──────────────────────────────────────────────────
        left, right = st.columns([1, 2], gap="medium")

        cursor = st.session_state["match_review_cursor"]
        cursor = max(0, min(cursor, len(review_items) - 1))

        # ── LEFT: item list ───────────────────────────────────────────────────
        with left:
            st.markdown(
                "<div style='background:#1a1a2e;color:#fff;padding:8px 12px;"
                "border-radius:6px;font-weight:bold;font-size:13px;margin-bottom:8px'>"
                "📋 ITEMS PENDING REVIEW</div>",
                unsafe_allow_html=True,
            )

            for idx, mr in enumerate(review_items):
                desc = (mr["db_item"].get("description") or "")[:32]
                phase = mr["phase"]
                key   = mr["db_item"].get("key", str(idx))
                dec   = decisions.get(key, {})
                action = dec.get("action", "")

                # Status badge
                if action == "accept":
                    badge = "✅"
                elif action == "skip":
                    badge = "⏭️"
                elif action == "manual":
                    badge = "✏️"
                else:
                    badge = _DEGREE_ICON.get(phase, "⚪")

                is_current = (idx == cursor)
                bg = "#1e3a5f" if is_current else "transparent"
                border = "2px solid #3b82f6" if is_current else "1px solid #e2e8f0"

                col_btn, col_info = st.columns([1, 4])
                with col_btn:
                    if st.button(f"{badge}", key=f"mrsel_{idx}",
                                 help=desc, use_container_width=True):
                        st.session_state["match_review_cursor"] = idx
                        st.rerun()
                with col_info:
                    conf_pct = int(mr.get("confidence", 0) * 100)
                    phase_col = _PHASE_COLOR.get(phase, "#94a3b8")
                    st.markdown(
                        f"<div style='background:{bg};border:{border};"
                        f"border-radius:4px;padding:4px 6px;cursor:pointer'>"
                        f"<div style='font-size:12px;font-weight:600;color:#1e293b'>{idx+1}. {desc}</div>"
                        f"<div style='font-size:10px;color:{phase_col}'>"
                        f"{phase.upper()} · {conf_pct}%</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

        # ── RIGHT: candidate analysis ─────────────────────────────────────────
        with right:
            mr = review_items[cursor]
            db_item = mr["db_item"]
            key     = db_item.get("key", "")
            desc    = db_item.get("description") or ""
            phase   = mr["phase"]
            conf    = mr.get("confidence", 0)
            cands   = mr.get("candidates", [])
            dec     = decisions.get(key, {})

            # Item header
            phase_col = _PHASE_COLOR.get(phase, "#94a3b8")
            st.markdown(
                f"<div style='background:#1a1a2e;color:#fff;padding:10px 14px;"
                f"border-radius:6px;margin-bottom:12px'>"
                f"<div style='font-size:11px;color:{phase_col};font-weight:600;letter-spacing:1px'>"
                f"POTENTIAL MATCHES ANALYSIS</div>"
                f"<div style='font-size:17px;font-weight:700;margin-top:4px'>{desc}</div>"
                f"<div style='font-size:11px;color:#94a3b8;margin-top:2px'>"
                f"Phase: {phase.upper()} · Confidence: {int(conf*100)}% · "
                f"Pack: {db_item.get('pack_type') or '—'} · "
                f"GL: {db_item.get('gl_code') or 'unassigned'}"
                f"</div></div>",
                unsafe_allow_html=True,
            )

            if not cands:
                st.warning("No candidates found for this item. Use manual GL entry below.")
            else:
                self._render_candidates(cands, key, dec)

            st.markdown("---")
            self._render_decision_controls(mr, key, dec, cursor, len(review_items))

        st.markdown("---")
        self._render_commit_panel(session)

    # ── Candidate Cards ───────────────────────────────────────────────────────

    def _render_candidates(self, candidates, item_key, current_decision):
        accepted_desc = current_decision.get("accepted_desc") if current_decision else None

        for i, cand in enumerate(candidates[:5]):
            degree = cand.get("degree", "probabilistic")
            deg_col  = _DEGREE_COLOR.get(degree, "#94a3b8")
            medal    = _RANK_MEDAL[i] if i < len(_RANK_MEDAL) else f"#{i+1}"
            comp     = cand.get("composite", 0)
            is_accepted = (accepted_desc == cand["description"])
            border = "2px solid #22c55e" if is_accepted else f"1px solid {deg_col}33"
            bg     = "#f0fdf4" if is_accepted else "#ffffff"

            # Score bar HTML helper
            def bar(score, color, label):
                w = int(min(score, 100))
                return (
                    f"<div style='display:flex;align-items:center;gap:6px;margin:3px 0'>"
                    f"<span style='font-size:10px;color:#64748b;width:90px;flex-shrink:0'>{label}</span>"
                    f"<div style='flex:1;background:#e2e8f0;border-radius:3px;height:8px'>"
                    f"<div style='width:{w}%;background:{color};border-radius:3px;height:8px'></div></div>"
                    f"<span style='font-size:10px;color:#1e293b;width:32px;text-align:right'>{w}%</span>"
                    f"</div>"
                )

            token_bar  = bar(cand.get("token_set", 0),  "#3b82f6", "Positive")
            partial_bar= bar(cand.get("partial",    0),  "#f59e0b", "Comparative")
            wratio_bar = bar(cand.get("wratio",     0),  "#22c55e", "Superlative")
            prob_bar   = bar(cand.get("composite",  0),  deg_col,   "Probabilistic")

            # Star rating (0–5 based on composite)
            stars = min(5, round(comp / 20))
            star_html = "★" * stars + "☆" * (5 - stars)

            accepted_badge = (
                "<span style='background:#22c55e;color:#fff;font-size:10px;"
                "padding:1px 6px;border-radius:3px;margin-left:8px'>ACCEPTED</span>"
                if is_accepted else ""
            )

            st.markdown(
                f"<div style='background:{bg};border:{border};border-radius:8px;"
                f"padding:12px 14px;margin-bottom:10px'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>"
                f"<div style='font-weight:700;font-size:14px'>{medal} {cand['description']}{accepted_badge}</div>"
                f"<div style='text-align:right'>"
                f"<div style='font-size:18px;font-weight:800;color:{deg_col}'>{int(comp)}%</div>"
                f"<div style='font-size:11px;color:#f59e0b'>{star_html}</div>"
                f"</div></div>"
                f"<div style='font-size:11px;color:#64748b;margin-bottom:6px'>"
                f"GL: <strong>{cand['gl_code']}</strong> — {cand['gl_name']} &nbsp;|&nbsp; "
                f"Pack: {cand.get('pack_type') or '—'} &nbsp;|&nbsp; "
                f"<span style='color:{deg_col};font-weight:600'>"
                f"{_DEGREE_ICON.get(degree,'')} {degree.upper()}</span> — {cand.get('degree_note','')}"
                f"</div>"
                f"{token_bar}{partial_bar}{wratio_bar}{prob_bar}"
                f"</div>",
                unsafe_allow_html=True,
            )

            # Accept this candidate button
            if not is_accepted:
                if st.button(f"✅ Accept — {cand['description'][:40]}",
                             key=f"accept_{item_key}_{i}"):
                    st.session_state["match_review_decisions"][item_key] = {
                        "action":        "accept",
                        "gl_code":       cand["gl_code"],
                        "gl_name":       cand["gl_name"],
                        "accepted_desc": cand["description"],
                        "confidence":    cand["composite"] / 100,
                    }
                    # Auto-advance cursor
                    session  = st.session_state.get("match_review_session", {})
                    n_review = len(session.get("probabilistic", []) + session.get("unmatched", []))
                    cur = st.session_state["match_review_cursor"]
                    if cur + 1 < n_review:
                        st.session_state["match_review_cursor"] = cur + 1
                    st.rerun()

    # ── Decision Controls ─────────────────────────────────────────────────────

    def _render_decision_controls(self, mr, item_key, current_decision,
                                  cursor, total):
        col_skip, col_man, col_nav = st.columns([1, 2, 1])

        with col_skip:
            if st.button("⏭️ Skip", key=f"skip_{item_key}", use_container_width=True):
                st.session_state["match_review_decisions"][item_key] = {
                    "action": "skip", "gl_code": "", "gl_name": "",
                }
                if cursor + 1 < total:
                    st.session_state["match_review_cursor"] = cursor + 1
                st.rerun()

        with col_man:
            with st.expander("✏️ Manual GL Entry"):
                db_item = mr["db_item"]
                mc1, mc2 = st.columns(2)
                manual_gl  = mc1.text_input("GL Code",  key=f"man_gl_{item_key}",
                                            value=current_decision.get("gl_code", "")
                                                  if current_decision else "")
                manual_name= mc2.text_input("GL Name",  key=f"man_nm_{item_key}",
                                            value=current_decision.get("gl_name", "")
                                                  if current_decision else "")
                if st.button("💾 Save Manual", key=f"man_save_{item_key}",
                             disabled=not manual_gl.strip()):
                    st.session_state["match_review_decisions"][item_key] = {
                        "action":  "manual",
                        "gl_code": manual_gl.strip(),
                        "gl_name": manual_name.strip(),
                        "accepted_desc": "(manual entry)",
                    }
                    if cursor + 1 < total:
                        st.session_state["match_review_cursor"] = cursor + 1
                    st.rerun()

        with col_nav:
            nc1, nc2 = st.columns(2)
            if nc1.button("◀", key=f"prev_{item_key}",
                          disabled=(cursor == 0)):
                st.session_state["match_review_cursor"] = cursor - 1
                st.rerun()
            if nc2.button("▶", key=f"next_{item_key}",
                          disabled=(cursor == total - 1)):
                st.session_state["match_review_cursor"] = cursor + 1
                st.rerun()

    # ── Commit Panel ──────────────────────────────────────────────────────────

    def _render_commit_panel(self, session):
        decisions  = st.session_state.get("match_review_decisions", {})
        to_commit  = {k: d for k, d in decisions.items()
                      if d.get("action") in ("accept", "manual")}
        review_items = (session.get("probabilistic", []) + session.get("unmatched", []))

        if not to_commit:
            if review_items:
                st.info("Accept or manually assign items above, then commit here.")
            return

        st.subheader(f"💾 Commit {len(to_commit)} Approved Assignments")

        # Preview table
        rows = []
        for mr in review_items:
            k = mr["db_item"].get("key", "")
            if k in to_commit:
                d = to_commit[k]
                rows.append({
                    "Item":     (mr["db_item"].get("description") or "")[:40],
                    "GL Code":  d["gl_code"],
                    "GL Name":  d["gl_name"],
                    "Method":   d["action"].upper(),
                    "Conf %":   f"{int(d.get('confidence', 0) * 100)}%",
                })

        import pandas as pd
        st.dataframe(pd.DataFrame(rows), use_container_width=True,
                     hide_index=True, height=min(350, 38 * len(rows) + 40))

        confirm = st.checkbox(
            f"Confirm: write {len(to_commit)} GL code assignments to database",
            key="mr_commit_confirm",
        )
        if st.button("✅ Commit to Database", type="primary",
                     disabled=not confirm, key="mr_commit_go"):
            changed_by = _get_changed_by()
            ok, err = 0, []
            for mr in review_items:
                k = mr["db_item"].get("key", "")
                if k not in to_commit:
                    continue
                d = to_commit[k]
                try:
                    self.db.update_item(
                        k,
                        {"gl_code": d["gl_code"], "gl_name": d["gl_name"]},
                        changed_by=changed_by,
                    )
                    ok += 1
                except Exception as exc:
                    err.append(f"{k}: {exc}")

            if ok:
                st.success(f"✅ Committed {ok} GL assignments.")
            if err:
                st.warning(f"{len(err)} errors:")
                for e in err[:5]:
                    st.caption(e)

            # Clear committed decisions
            committed_keys = set(to_commit.keys())
            st.session_state["match_review_decisions"] = {
                k: v for k, v in decisions.items()
                if k not in committed_keys
            }
            st.rerun()

        st.markdown("---")
        if st.button("🗑️ Clear Session", key="mr_clear_session",
                     help="Discard all pending matches and decisions"):
            for key in ("match_review_session", "match_review_decisions",
                        "match_review_cursor"):
                st.session_state.pop(key, None)
            st.rerun()


# ── end of MatchReviewDashboard ───────────────────────────────────────────────
