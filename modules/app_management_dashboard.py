# ──────────────────────────────────────────────────────────────────────────────
#  modules/app_management_dashboard.py  —  App Management Dashboard (F-011)
#  v1.0.0
#
#  Tabs: Features | Users | Import Reports | Version Sync
#  Replaces the ad-hoc _page_settings() in app.py.
#  Admin-only (min_role: admin).
# ──────────────────────────────────────────────────────────────────────────────

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from base import Dashboard


class AppManagementDashboard(Dashboard):

    MANIFEST = {
        "id":       "app_management",
        "label":    "App Management",
        "version":  "1.0.0",
        "icon":     "⚙️",
        "status":   "active",
        "page_key": "app_management",
        "menu": {
            "parent":   "Tools",
            "label":    "App Management",
            "shortcut": "A",
            "position": 99,
        },
        "sidebar": {
            "section":  "",
            "position": 99,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["import_jobs"],
        "session_keys": [],
        "abilities": [
            "Toggle feature flags live without redeploy",
            "Manage user accounts and roles",
            "View import job history and aggregate metrics",
            "Trigger version sync with GitHub",
        ],
        "permissions": {"min_role": "admin"},
    }

    DOCS = {
        "summary": "Admin control panel — features, users, import reporting, version sync.",
        "usage":   "Admin-only. Replaces the legacy Settings page.",
        "demo_ready": False,
        "notes":   "Migrated from _page_settings() in app.py (F-011).",
        "known_issues": [],
        "changelog": [
            {"version": "1.0.0", "date": "2026-03-27",
             "note": "Initial implementation, absorbs Settings + Import Reporting (F-011, F-006)."},
        ],
    }

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**⚙️ App Management**")
            st.caption("Admin · Features · Users · Reports")

    def render(self) -> None:
        st.title("⚙️ App Management")

        try:
            import auth
            if not auth.is_admin():
                st.warning("🔒 Admin access required.")
                st.info(
                    "The first user to sign in is automatically granted admin. "
                    "Ask your admin to promote your account."
                )
                return
        except Exception:
            st.warning("Auth module unavailable — admin check skipped.")

        tab1, tab2, tab3, tab4 = st.tabs(
            ["🔧 Features", "👥 Users", "📊 Import Reports", "🔀 Version Sync"]
        )

        with tab1:
            self._render_features()

        with tab2:
            self._render_users()

        with tab3:
            self._render_import_reports()

        with tab4:
            self._render_version_sync()

    # ── Features tab ──────────────────────────────────────────────────────────

    def _render_features(self) -> None:
        st.subheader("Feature Toggles")
        st.caption("Changes persist while the server is running. Reset to defaults on next deploy.")

        try:
            from ui_skeleton import get_feature_registry
            feat_registry = get_feature_registry()
        except Exception as exc:
            st.error(f"Could not load feature registry: {exc}")
            return

        cols = st.columns(2)
        for i, feat in enumerate(feat_registry.all_features()):
            with cols[i % 2]:
                new_val = st.toggle(
                    feat.description or feat.name,
                    value=feat.option_available,
                    key=f"amgmt_feat_{feat.name}",
                    help=feat.name,
                )
                if new_val != feat.option_available:
                    feat_registry.set(feat.name, new_val)
                    st.rerun()

    # ── Users tab ─────────────────────────────────────────────────────────────

    def _render_users(self) -> None:
        try:
            import auth
            auth.render_user_management(self.db)
        except Exception as exc:
            st.error(f"User management unavailable: {exc}")

    # ── Import Reports tab (F-006) ────────────────────────────────────────────

    def _render_import_reports(self) -> None:
        st.subheader("Import Job History")

        # ── Controls ──────────────────────────────────────────────────────────
        fc1, fc2, fc3 = st.columns(3)
        limit = fc1.number_input("Show last N jobs", value=50, min_value=1,
                                  step=10, format="%.0f", key="amgmt_ir_limit")
        type_filter = fc2.selectbox(
            "Job Type",
            ["All", "invoice_import", "count_import", "db_import", "gl_import"],
            key="amgmt_ir_type",
        )
        status_filter = fc3.selectbox(
            "Status",
            ["All", "running", "complete", "failed"],
            key="amgmt_ir_status",
        )

        try:
            jobs = self.db.get_recent_jobs(limit=int(limit))
        except Exception as exc:
            st.error(f"Could not load jobs: {exc}")
            return

        if type_filter != "All":
            jobs = [j for j in jobs if j.get("job_type") == type_filter]
        if status_filter != "All":
            jobs = [j for j in jobs if j.get("status") == status_filter]

        if not jobs:
            st.info("No import jobs found matching filters.")
            return

        # ── Summary metrics ────────────────────────────────────────────────────
        total_jobs    = len(jobs)
        total_rows    = sum(j.get("total_rows")  or 0 for j in jobs)
        total_added   = sum(j.get("added")       or 0 for j in jobs)
        total_updated = sum(j.get("updated")     or 0 for j in jobs)
        total_errors  = sum(j.get("error_count") or 0 for j in jobs)
        failed_jobs   = sum(1 for j in jobs if j.get("status") == "failed")

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Jobs",       total_jobs)
        m2.metric("Rows",       f"{total_rows:,}")
        m3.metric("Added",      f"{total_added:,}")
        m4.metric("Updated",    f"{total_updated:,}")
        m5.metric("Errors",     total_errors,
                  delta=str(total_errors) if total_errors else None,
                  delta_color="inverse")
        m6.metric("Failed Jobs", failed_jobs,
                  delta=str(failed_jobs) if failed_jobs else None,
                  delta_color="inverse")

        st.markdown("---")

        # ── View selector ─────────────────────────────────────────────────────
        view = st.radio("View by", ["Job", "Date", "Source File"],
                        horizontal=True, key="amgmt_ir_view")

        # ── Column chooser ────────────────────────────────────────────────────
        all_cols = ["Job ID", "Type", "Status", "Source File", "Date",
                    "Rows", "Added", "Updated", "Skipped", "Errors",
                    "Triggered By", "Duration"]
        visible = st.multiselect("Columns", all_cols, default=[
            "Type", "Status", "Source File", "Date",
            "Added", "Updated", "Errors", "Duration",
        ], key="amgmt_ir_cols")

        # ── Build display rows ─────────────────────────────────────────────────
        def _duration(job) -> str:
            try:
                start = job.get("started_at")
                end   = job.get("finished_at")
                if start and end:
                    delta = end - start
                    secs  = int(delta.total_seconds())
                    return f"{secs}s" if secs < 60 else f"{secs // 60}m {secs % 60}s"
                if start:
                    now   = datetime.now(timezone.utc)
                    secs  = int((now - start).total_seconds())
                    return f"~{secs}s (running)"
            except Exception:
                pass
            return "—"

        def _status_icon(status: str) -> str:
            return {"running": "🔄", "complete": "✅", "failed": "❌"}.get(status, "⏳")

        all_rows = []
        for j in jobs:
            all_rows.append({
                "Job ID":       j.get("job_id", "")[:12] + "…",
                "Type":         j.get("job_type", "—"),
                "Status":       f"{_status_icon(j.get('status',''))} {j.get('status','')}",
                "Source File":  (j.get("source_file") or "—")[-40:],
                "Date":         str(j.get("started_at") or "—")[:16],
                "Rows":         j.get("total_rows")  or 0,
                "Added":        j.get("added")       or 0,
                "Updated":      j.get("updated")     or 0,
                "Skipped":      j.get("skipped")     or 0,
                "Errors":       j.get("error_count") or 0,
                "Triggered By": j.get("triggered_by") or "—",
                "Duration":     _duration(j),
            })

        df = pd.DataFrame(all_rows)

        if view == "Date":
            df["_date"] = [str(j.get("started_at") or "")[:10] for j in jobs]
            for date_val, group in df.groupby("_date", sort=False):
                with st.expander(f"📅 {date_val} — {len(group)} job(s)"):
                    st.dataframe(
                        group[[c for c in visible if c in group.columns]],
                        use_container_width=True, hide_index=True,
                    )

        elif view == "Source File":
            df["_src"] = [j.get("source_file") or "unknown" for j in jobs]
            for src, group in df.groupby("_src", sort=False):
                with st.expander(f"📄 {src} — {len(group)} import(s)"):
                    st.dataframe(
                        group[[c for c in visible if c in group.columns]],
                        use_container_width=True, hide_index=True,
                    )

        else:  # Job (flat list)
            st.dataframe(
                df[[c for c in visible if c in df.columns]],
                use_container_width=True, hide_index=True,
                height=min(400, 36 + len(df) * 35),
            )

        # ── Failed job detail ──────────────────────────────────────────────────
        failed = [j for j in jobs if j.get("status") == "failed" and j.get("errors")]
        if failed:
            with st.expander(f"❌ {len(failed)} failed job error(s)"):
                for j in failed:
                    st.markdown(f"**{j.get('job_id','')[:12]}** · {j.get('source_file','—')}")
                    errs = j.get("errors")
                    if isinstance(errs, list):
                        for e in errs[:5]:
                            st.caption(str(e))
                    elif errs:
                        st.caption(str(errs))

    # ── Version Sync tab ──────────────────────────────────────────────────────

    def _render_version_sync(self) -> None:
        try:
            from registry import get_registry
            from version_syncer import VersionSyncer
            registry = get_registry()
            syncer   = VersionSyncer(registry=registry, repo="trechurch/UHAIMS")
            syncer.render_panel()
        except Exception as exc:
            st.error(f"Version sync unavailable: {exc}")
            st.caption("Check that the GitHub repo is accessible and secrets are configured.")


# ── end of AppManagementDashboard ─────────────────────────────────────────────
