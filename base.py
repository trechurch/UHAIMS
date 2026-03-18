# ──────────────────────────────────────────────────────────────────────────────
#  base.py  —  Dashboard Base Class + MANIFEST + DOCS Contract
#  Every module in modules/ inherits from Dashboard.
#  The registry reads MANIFESTs; docs_generator reads DOCS.
#  app.py reads nothing directly — registry handles everything.
# ──────────────────────────────────────────────────────────────────────────────

__version__ = "1.1.0"

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import streamlit as st

# ── end of imports ────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  MANIFEST SCHEMA  (enforced by ManifestValidator)
#
#  {
#    "id":           str,        # unique snake_case identifier
#    "label":        str,        # human display name
#    "version":      str,        # semver  e.g. "1.0.0"
#    "icon":         str,        # emoji used in nav/sidebar
#    "status":       str,        # "active" | "stub" | "disabled"
#    "page_key":     str,        # ?page= URL key that routes here
#
#    "menu": {
#      "parent":     str,        # "File"|"Dashboards"|"View"|"Help"
#      "label":      str,        # override label (defaults to MANIFEST label)
#      "shortcut":   str,        # single-key hint shown in dropdown
#      "position":   int,        # sort order within parent
#    },
#
#    "sidebar": {
#      "section":    str,        # sidebar section header
#      "position":   int,        # sort order
#      "show":       bool,       # appear in sidebar nav
#    },
#
#    "depends_on":   List[str],  # module ids or service names required
#    "db_tables":    List[str],  # supabase tables read/written
#    "session_keys": List[str],  # st.session_state keys OWNED by this module
#    "abilities":    List[str],  # plain-english capability list
#    "permissions":  {
#      "min_role":   str,        # "admin" | "user" | "any"
#    },
#  }
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  DOCS SCHEMA  (enforced by DocsValidator)
#
#  {
#    "summary":      str,        # one-sentence plain-english description
#    "usage":        str,        # what the user does here / how to invoke
#    "demo_ready":   bool,       # safe to show in a live demo right now?
#    "notes":        str,        # narrative, design decisions, gotchas
#    "known_issues": List[str],  # active bugs or missing pieces
#    "changelog": [
#      { "version": str, "date": "YYYY-MM-DD", "note": str },
#    ],
#  }
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  VALIDATORS
# ──────────────────────────────────────────────────────────────────────────────

_MANIFEST_REQUIRED = {"id", "label", "version", "icon", "status", "page_key"}
_DOCS_REQUIRED     = {"summary", "usage", "demo_ready", "known_issues", "changelog"}
_VALID_STATUSES    = {"active", "stub", "disabled"}


class ManifestError(Exception):
    """Raised when a module MANIFEST fails validation."""


class DocsError(Exception):
    """Raised when a module DOCS block fails validation."""


class ManifestValidator:
    @staticmethod
    def validate(manifest: Dict, cls_name: str) -> None:
        missing = _MANIFEST_REQUIRED - set(manifest.keys())
        if missing:
            raise ManifestError(
                f"{cls_name}.MANIFEST is missing required keys: {missing}"
            )
        if manifest.get("status") not in _VALID_STATUSES:
            raise ManifestError(
                f"{cls_name}.MANIFEST 'status' must be one of {_VALID_STATUSES}, "
                f"got {repr(manifest.get('status'))}"
            )
        if not manifest.get("id", "").replace("_", "").isalnum():
            raise ManifestError(
                f"{cls_name}.MANIFEST 'id' must be snake_case alphanumeric, "
                f"got {repr(manifest.get('id'))}"
            )


class DocsValidator:
    @staticmethod
    def validate(docs: Dict, cls_name: str) -> None:
        missing = _DOCS_REQUIRED - set(docs.keys())
        if missing:
            raise DocsError(
                f"{cls_name}.DOCS is missing required keys: {missing}"
            )
        if not isinstance(docs.get("known_issues"), list):
            raise DocsError(f"{cls_name}.DOCS 'known_issues' must be a list")
        if not isinstance(docs.get("changelog"), list):
            raise DocsError(f"{cls_name}.DOCS 'changelog' must be a list")
        for entry in docs.get("changelog", []):
            if not isinstance(entry, dict) or not {"version", "date", "note"} <= entry.keys():
                raise DocsError(
                    f"{cls_name}.DOCS each 'changelog' entry must have keys: "
                    f"version, date, note"
                )

# ── end of validators ─────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  DASHBOARD BASE CLASS
# ──────────────────────────────────────────────────────────────────────────────

class Dashboard(ABC):
    """
    Base class for every UHA IMS dashboard module.

    Subclass contract:
      1. Define class-level MANIFEST dict  (see schema above)
      2. Define class-level DOCS dict      (see schema above)
      3. Implement render()
      4. Optionally override sidebar(), on_load(), on_unload()

    State convention:
      Use self.state() / self.set_state() / self.clear_state().
      Keys are auto-namespaced under the module id — no cross-module collisions.
    """

    MANIFEST: Dict[str, Any] = {}
    DOCS:     Dict[str, Any] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def __init__(self, db=None):
        self._db = db
        ManifestValidator.validate(self.MANIFEST, self.__class__.__name__)
        DocsValidator.validate(self.DOCS,         self.__class__.__name__)
        self._init_session_keys()

    def _init_session_keys(self):
        """Pre-populate declared session keys with None so render() never hits KeyError."""
        for key in self.MANIFEST.get("session_keys", []):
            ns = self._ns(key)
            if ns not in st.session_state:
                st.session_state[ns] = None

    # ── Session helpers ───────────────────────────────────────────────────────

    def _ns(self, key: str) -> str:
        """Namespace a raw key under this module's id."""
        return f"_mod_{self.MANIFEST['id']}_{key}"

    def state(self, key: str, default: Any = None) -> Any:
        """Get a namespaced session state value."""
        return st.session_state.get(self._ns(key), default)

    def set_state(self, key: str, value: Any) -> None:
        """Set a namespaced session state value."""
        st.session_state[self._ns(key)] = value

    def clear_state(self, key: str) -> None:
        """Delete a namespaced session state value."""
        ns = self._ns(key)
        if ns in st.session_state:
            del st.session_state[ns]

    # ── Lifecycle hooks (override as needed) ──────────────────────────────────

    def on_load(self) -> None:
        """Called once per session when this module is first routed to."""

    def on_unload(self) -> None:
        """Called when the user navigates away from this module."""

    # ── Navigation contributions ──────────────────────────────────────────────

    def sidebar(self) -> None:
        """
        Module-specific sidebar widgets drawn when this module is active.
        Default: nothing.  Override to add controls.
        """

    # ── Main render (required) ────────────────────────────────────────────────

    @abstractmethod
    def render(self) -> None:
        """Draw the main content area. Must be implemented by every module."""

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def id(self)         -> str:  return self.MANIFEST["id"]

    @property
    def label(self)      -> str:  return self.MANIFEST["label"]

    @property
    def icon(self)       -> str:  return self.MANIFEST["icon"]

    @property
    def status(self)     -> str:  return self.MANIFEST["status"]

    @property
    def page_key(self)   -> str:  return self.MANIFEST["page_key"]

    @property
    def version(self)    -> str:  return self.MANIFEST["version"]

    @property
    def is_active(self)  -> bool: return self.status == "active"

    @property
    def is_stub(self)    -> bool: return self.status == "stub"

    @property
    def demo_ready(self) -> bool: return bool(self.DOCS.get("demo_ready", False))

    @property
    def db(self):
        """Shared database connection. Raises clearly if the module forgot to declare it."""
        if self._db is None:
            raise RuntimeError(
                f"Module '{self.id}' accessed self.db but no db instance was injected. "
                f"Add 'database' to MANIFEST['depends_on']."
            )
        return self._db

    # ── Default stub render ───────────────────────────────────────────────────

    def _render_stub(self) -> None:
        st.title(f"{self.icon} {self.label}")
        st.info(f"**{self.label}** is on the implementation roadmap.")
        with st.expander("Module details"):
            st.markdown(f"**Summary:** {self.DOCS.get('summary', '—')}")
            issues = self.DOCS.get("known_issues", [])
            if issues:
                st.markdown("**Known issues:**")
                for issue in issues:
                    st.markdown(f"- {issue}")

# ── end of Dashboard ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  STUB MIXIN
# ──────────────────────────────────────────────────────────────────────────────

class StubMixin:
    """
    Provide a concrete render() for modules whose status='stub'.
    Saves you from implementing an abstract method just to show a placeholder.

    Usage:
        class TransferDashboard(StubMixin, Dashboard):
            MANIFEST = { ..., "status": "stub", ... }
            DOCS     = { ... }
    """
    def render(self) -> None:
        self._render_stub()

# ── end of StubMixin ──────────────────────────────────────────────────────────
