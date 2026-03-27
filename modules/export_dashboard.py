# ──────────────────────────────────────────────────────────────────────────────
#  modules/export_dashboard.py  —  Export Dashboard
#  v1.0.0  —  Migrated from inventory_logic.page_export()
# ──────────────────────────────────────────────────────────────────────────────

import io
from datetime import datetime

import pandas as pd
import streamlit as st
from base import Dashboard


class ExportDashboard(Dashboard):

    MANIFEST = {
        "id":       "export_dashboard",
        "label":    "Export",
        "version":  "1.1.0",
        "icon":     "📤",
        "status":   "active",
        "page_key": "export",
        "menu": {
            "parent":   "Tools",
            "label":    "Export",
            "shortcut": "E",
            "position": 30,
        },
        "sidebar": {
            "section":  "Tools",
            "position": 30,
            "show":     True,
        },
        "depends_on":   ["database"],
        "db_tables":    ["items"],
        "session_keys": [],
        "abilities": [
            "Export full inventory to Excel (.xlsx)",
            "Export full inventory to CSV",
            "Save export to OneDrive (if connected)",
        ],
        "permissions": {"min_role": "any"},
    }

    DOCS = {
        "summary": "Download a full inventory snapshot as Excel or CSV.",
        "usage":   "Click Download. OneDrive save is available if connected.",
        "demo_ready": True,
        "notes":   "Exports all active items. OneDrive integration is optional.",
        "known_issues": [],
        "changelog": [
            {"version": "1.1.0", "date": "2026-03-27", "note": "F-030: filter controls (status, GL code, vendor, status tag) above download buttons."},
            {"version": "1.0.0", "date": "2026-03-25", "note": "Migrated from inventory_logic.page_export() to SDOA module."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        pass

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**📤 Export**")
            st.caption("Download full inventory snapshot")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        st.title("📤 Export Inventory")

        try:
            items = self.db.get_all_items(record_status=None)
        except Exception as exc:
            st.error(f"Could not load inventory: {exc}")
            return

        if not items:
            st.info("No items to export.")
            return

        df = pd.DataFrame(items)

        # ── Filter controls ───────────────────────────────────────────────────
        with st.expander("🔽 Filter export", expanded=False):
            fc1, fc2, fc3, fc4 = st.columns(4)

            # Status
            statuses = sorted(df["record_status"].dropna().unique().tolist())
            sel_status = fc1.multiselect(
                "Status", statuses,
                default=["active"],
                key="exp_filter_status",
            )

            # GL Code
            gl_codes = sorted(df["gl_code"].dropna().unique().tolist())
            sel_gl = fc2.multiselect("GL Code", gl_codes, key="exp_filter_gl")

            # Vendor
            vendors = sorted(df["vendor"].dropna().unique().tolist())
            sel_vendor = fc3.multiselect("Vendor", vendors, key="exp_filter_vendor")

            # Status tag
            tags = sorted(df["status_tag"].dropna().unique().tolist())
            sel_tag = fc4.multiselect("Status Tag", tags, key="exp_filter_tag")

        # Apply filters
        mask = pd.Series([True] * len(df), index=df.index)
        if sel_status:
            mask &= df["record_status"].isin(sel_status)
        if sel_gl:
            mask &= df["gl_code"].isin(sel_gl)
        if sel_vendor:
            mask &= df["vendor"].isin(sel_vendor)
        if sel_tag:
            mask &= df["status_tag"].isin(sel_tag)
        df = df[mask].reset_index(drop=True)

        st.caption(f"{len(df)} item(s) — {len(items) - len(df)} filtered out")

        # Strip timezone from any datetime columns — Excel doesn't support tz-aware
        for col in df.select_dtypes(include=["datetimetz"]).columns:
            df[col] = df[col].dt.tz_localize(None)

        datestamp = datetime.now().strftime("%Y%m%d")

        # ── Excel download ────────────────────────────────────────────────────
        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Inventory")
        excel_buf.seek(0)

        st.download_button(
            "⬇️ Download as Excel",
            data=excel_buf,
            file_name=f"inventory_export_{datestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # ── CSV download ──────────────────────────────────────────────────────
        st.download_button(
            "⬇️ Download as CSV",
            data=df.to_csv(index=False),
            file_name=f"inventory_export_{datestamp}.csv",
            mime="text/csv",
        )

        # ── OneDrive save (optional) ──────────────────────────────────────────
        od = None
        try:
            import onedrive_connector as _od
            od = _od
        except Exception:
            pass

        if od:
            try:
                token = od.get_access_token()
            except Exception:
                token = None
            if token:
                st.subheader("Save to OneDrive")
                if st.button("☁️ Export to OneDrive", key="export_onedrive"):
                    buf = io.BytesIO()
                    df.to_excel(buf, index=False)
                    filename = f"inventory_export_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
                    od.archive_file(filename, buf.getvalue(), subfolder="Exports")
                    st.success(f"Saved {filename} to OneDrive Archives.")

# ── end of ExportDashboard ────────────────────────────────────────────────────
