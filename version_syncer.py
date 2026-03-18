# ──────────────────────────────────────────────────────────────────────────────
#  version_syncer.py  —  Live vs Repo Version Sync Checker
#
#  Compares the version of every running component against what is currently
#  in the GitHub repo. If anything is out of sync, surfaces it clearly and
#  offers a one-click hot-reload (cache clear + rerun) without a full reboot.
#
#  Usage (in app.py or any dashboard):
#    from version_syncer import VersionSyncer
#    syncer = VersionSyncer(registry=registry, repo="trechurch/UHAIMS")
#    syncer.render_badge()        # sidebar badge — compact
#    syncer.render_panel()        # full panel — detailed diff
#
#  v1.0.0
# ──────────────────────────────────────────────────────────────────────────────

__version__ = "1.0.0"

import re
import requests
import streamlit as st
from typing import Dict, List, Optional, Tuple

# ── end of imports ────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  SERVICE_MANIFEST  (self-describing per SDOA)
# ──────────────────────────────────────────────────────────────────────────────

SERVICE_MANIFEST = {
    "id":      "version_syncer",
    "label":   "Version Sync Checker",
    "version": "1.0.0",
    "type":    "service",
    "depends_on": ["registry"],
    "provides": [
        "check() -> List[VersionRecord]",
        "render_badge()  — sidebar compact badge",
        "render_panel()  — full diff panel",
        "hot_reload()    — clear registry cache + rerun",
    ],
}

SERVICE_DOCS = {
    "summary": (
        "Compares live running component versions against the GitHub repo. "
        "Surfaces drifts and offers one-click hot-reload."
    ),
    "usage": (
        "Instantiate with registry + repo slug. "
        "Call render_badge() in the sidebar, render_panel() on the diagnostics page."
    ),
    "demo_ready": True,
    "notes": (
        "Fetches raw GitHub content via raw.githubusercontent.com. "
        "Version parsing uses regex — matches 'version': '1.2.3', "
        "__version__ = '1.2.3', and MANIFEST version fields. "
        "Hot-reload clears st.cache_resource and calls st.rerun() — "
        "no full app reboot required."
    ),
    "known_issues": [
        "GitHub rate limit: 60 unauthenticated requests/hour. "
        "Add GITHUB_TOKEN to st.secrets to raise to 5000/hour.",
    ],
    "changelog": [
        {"version": "1.0.0", "date": "2026-03-18", "note": "Initial implementation."},
    ],
}

# ── end of manifests ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  VERSION RECORD
# ──────────────────────────────────────────────────────────────────────────────

class VersionRecord:
    """Holds the live vs repo version comparison for one component."""

    def __init__(self, name: str, filepath: str,
                 live: Optional[str], repo: Optional[str]):
        self.name     = name
        self.filepath = filepath
        self.live     = live or "?"
        self.repo     = repo or "?"

    @property
    def in_sync(self) -> bool:
        return self.live != "?" and self.repo != "?" and self.live == self.repo

    @property
    def status_icon(self) -> str:
        if self.live == "?" or self.repo == "?":
            return "❓"
        return "✅" if self.in_sync else "🔴"

    def __repr__(self):
        return f"VersionRecord({self.name}: live={self.live} repo={self.repo})"

# ── end of VersionRecord ──────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  VERSION PARSER
# ──────────────────────────────────────────────────────────────────────────────

# Patterns tried in order — first match wins
_VERSION_PATTERNS = [
    # MANIFEST / SERVICE_MANIFEST dict key
    r'"version"\s*:\s*"([0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)"',
    # __version__ = "x.y.z"
    r'__version__\s*=\s*["\']([0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)["\']',
    # version = "x.y.z" (bare assignment)
    r'\bversion\s*=\s*["\']([0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)["\']',
]

def _parse_version(content: str) -> Optional[str]:
    """Extract the first semver string from file content."""
    for pattern in _VERSION_PATTERNS:
        m = re.search(pattern, content)
        if m:
            return m.group(1)
    return None

# ── end of version parser ─────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  VERSION SYNCER
# ──────────────────────────────────────────────────────────────────────────────

# Components to check — (display_name, repo_filepath)
# Add new files here as the project grows
_COMPONENTS = [
    ("app.py",            "app.py"),
    ("base.py",           "base.py"),
    ("registry.py",       "registry.py"),
    ("database.py",       "database.py"),
    ("importer.py",       "importer.py"),
    ("version_syncer.py", "version_syncer.py"),
    # Modules discovered dynamically from registry
]


class VersionSyncer:

    def __init__(self, registry=None, repo: str = "trechurch/UHAIMS",
                 branch: str = "main"):
        self._registry = registry
        self._repo     = repo
        self._branch   = branch
        self._base_url = f"https://raw.githubusercontent.com/{repo}/{branch}"
        self._cache: Optional[List[VersionRecord]] = None

    # ── GitHub fetch ──────────────────────────────────────────────────────────

    def _fetch_version(self, filepath: str) -> Optional[str]:
        """Fetch a file from GitHub and parse its version string."""
        url = f"{self._base_url}/{filepath}"
        headers = {}
        try:
            token = st.secrets.get("GITHUB_TOKEN")
            if token:
                headers["Authorization"] = f"token {token}"
        except Exception:
            pass
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                return _parse_version(resp.text)
        except Exception:
            pass
        return None

    # ── Live version readers ──────────────────────────────────────────────────

    def _live_versions(self) -> Dict[str, str]:
        """
        Build a dict of component_name -> live_version from:
          - Hardcoded service imports
          - Registry module manifests
        """
        live = {}

        # Shell + services
        try:
            import app as _app
            live["app.py"] = getattr(_app, "__version__", "?")
        except Exception:
            live["app.py"] = "?"

        try:
            import base as _base
            live["base.py"] = getattr(_base, "__version__", "?")
        except Exception:
            live["base.py"] = "?"

        try:
            import registry as _reg
            live["registry.py"] = getattr(_reg, "__version__", "?")
        except Exception:
            live["registry.py"] = "?"

        try:
            from database import InventoryDatabase
            live["database.py"] = InventoryDatabase.SERVICE_MANIFEST.get("version", "?")
        except Exception:
            live["database.py"] = "?"

        try:
            from importer import InventoryImporter
            live["importer.py"] = InventoryImporter.SERVICE_MANIFEST.get("version", "?")
        except Exception:
            live["importer.py"] = "?"

        live["version_syncer.py"] = __version__

        # Modules from registry
        if self._registry:
            for m in self._registry.all():
                key = f"modules/{m.id}.py"
                live[key] = m.version

        return live

    # ── Main check ────────────────────────────────────────────────────────────

    def check(self, force: bool = False) -> List[VersionRecord]:
        """
        Compare live versions against repo versions.
        Results are cached for the session — pass force=True to refresh.
        """
        if self._cache is not None and not force:
            return self._cache

        live_versions = self._live_versions()

        # Build component list — static + dynamic modules
        components = list(_COMPONENTS)
        if self._registry:
            for m in self._registry.all():
                entry = (f"modules/{m.id}.py", f"modules/{m.id}.py")
                if entry not in components:
                    components.append(entry)

        records = []
        for name, filepath in components:
            live = live_versions.get(name) or live_versions.get(filepath, "?")
            repo = self._fetch_version(filepath)
            records.append(VersionRecord(name, filepath, live, repo))

        self._cache = records
        return records

    def clear_cache(self):
        """Force re-fetch on next check()."""
        self._cache = None

    # ── Hot reload ────────────────────────────────────────────────────────────

    @staticmethod
    def hot_reload():
        """
        Clear Streamlit's registry cache and rerun.
        Forces a cold module re-scan without a full app reboot.
        """
        try:
            from registry import get_registry
            get_registry.clear()
        except Exception:
            pass
        st.rerun()

    # ── Renderers ─────────────────────────────────────────────────────────────

    def render_badge(self, force: bool = False):
        """
        Compact sidebar badge. Shows sync status at a glance.
        Call this from app.py _render_sidebar().
        """
        records = self.check(force=force)
        out_of_sync = [r for r in records if not r.in_sync]
        unknown     = [r for r in records if r.live == "?" or r.repo == "?"]

        with st.sidebar:
            if not out_of_sync and not unknown:
                st.caption("✅ All components in sync")
            else:
                drifted = [r for r in out_of_sync if r.live != "?" and r.repo != "?"]
                if drifted:
                    st.warning(
                        f"🔴 {len(drifted)} component(s) out of sync",
                        icon="⚠️",
                    )
                    if st.button("🔄 Hot Reload", key="syncer_hot_reload_badge",
                                 use_container_width=True):
                        self.hot_reload()

    def render_panel(self, force: bool = False):
        """
        Full sync panel. Shows version table with live vs repo diff.
        Call from diagnostics expander or a dedicated settings page.
        """
        col1, col2 = st.columns([4, 1])
        with col1:
            st.subheader("🔀 Version Sync")
        with col2:
            if st.button("↻ Refresh", key="syncer_refresh"):
                self.clear_cache()
                force = True

        with st.spinner("Checking GitHub…"):
            records = self.check(force=force)

        out_of_sync = [r for r in records if not r.in_sync
                       and r.live != "?" and r.repo != "?"]

        if out_of_sync:
            st.error(
                f"**{len(out_of_sync)} component(s) out of sync** — "
                f"live version differs from repo."
            )
            if st.button("🔄 Hot Reload Now", key="syncer_hot_reload_panel",
                         type="primary"):
                self.hot_reload()
        else:
            st.success("All components match the repo.")

        # Version table
        import pandas as pd
        rows = []
        for r in records:
            rows.append({
                "":        r.status_icon,
                "Component": r.name,
                "Live":    r.live,
                "Repo":    r.repo,
                "Drift":   "" if r.in_sync else
                           f"{r.live} → {r.repo}" if r.live != "?" and r.repo != "?"
                           else "unknown",
            })
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )

        st.caption(
            "Hot Reload clears the module registry cache and reruns the app. "
            "No full reboot needed — takes ~2 seconds."
        )

# ── end of VersionSyncer ──────────────────────────────────────────────────────
