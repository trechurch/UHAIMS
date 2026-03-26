# ──────────────────────────────────────────────────────────────────────────────
#  base.py  —  SDOA Base Contract
#
#  v1.2.0  —  Added:
#               verify()      — health-check hook, runs before on_load()
#               demo_mode     — flag to show demo-safe UI
#               ScopedDBProxy — limits module DB access to declared tables
#               pitch         — one-liner field in MANIFEST (optional)
#               _render_demo_warning() — shown when demo_mode=True
# ──────────────────────────────────────────────────────────────────────────────

__version__ = "1.2.0"

import streamlit as st
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

# ── end of imports ────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  SCOPED DB PROXY
# ──────────────────────────────────────────────────────────────────────────────

class ScopedDBProxy:
    """
    Wraps InventoryDatabase and restricts access to the tables declared
    in the module's MANIFEST.db_tables.

    Any method call that tries to touch an undeclared table raises a
    PermissionError — caught by the registry and shown as a load error.

    Methods that don't touch specific tables (count_items, get_inventory_value,
    create_job, etc.) are passed through unrestricted.
    """

    # Methods that target a specific table via a key or explicit arg
    _TABLE_GATED = {
        "get_item":           "items",
        "add_item":           "items",
        "upsert_item":        "items",
        "update_item_smart":  "items",
        "delete_item":        "items",
        "item_exists":        "items",
        "set_override":       "items",
        "clear_override":     "items",
        "get_item_history":   "item_history",
        "get_price_history":  "price_history",
        "get_job":            "import_jobs",
        "update_job":         "import_jobs",
        "fail_job":           "import_jobs",
    }

    def __init__(self, db, allowed_tables: List[str], module_id: str):
        self._db            = db
        self._allowed       = set(allowed_tables)
        self._module_id     = module_id

    def _check(self, table: str):
        if table not in self._allowed:
            raise PermissionError(
                f"Module '{self._module_id}' tried to access table "
                f"'{table}' which is not declared in MANIFEST.db_tables. "
                f"Declared: {sorted(self._allowed)}"
            )

    def __getattr__(self, name: str):
        # Pass through to the real DB object
        attr = getattr(self._db, name)

        # If it's a table-gated method, wrap it with a check
        required_table = self._TABLE_GATED.get(name)
        if required_table and callable(attr):
            def _guarded(*args, **kwargs):
                self._check(required_table)
                return attr(*args, **kwargs)
            return _guarded

        return attr

# ── end of ScopedDBProxy ──────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  MANIFEST VALIDATOR
# ──────────────────────────────────────────────────────────────────────────────

class ManifestValidator:

    REQUIRED = ["id", "label", "version", "icon", "status", "page_key"]

    @classmethod
    def validate(cls, manifest: Dict[str, Any]) -> List[str]:
        """
        Returns a list of error strings.
        Empty list = valid.
        """
        errors = []
        for key in cls.REQUIRED:
            if key not in manifest:
                errors.append(f"MANIFEST missing required key: '{key}'")

        valid_statuses = {"active", "stub", "disabled"}
        status = manifest.get("status", "")
        if status not in valid_statuses:
            errors.append(
                f"MANIFEST.status '{status}' invalid. "
                f"Must be one of: {valid_statuses}"
            )

        # Warn (not error) if pitch is missing — it's optional but encouraged
        if "pitch" not in manifest:
            pass  # encouraged but not required

        return errors

# ── end of ManifestValidator ──────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  DOCS VALIDATOR
# ──────────────────────────────────────────────────────────────────────────────

class DocsValidator:

    REQUIRED = ["summary", "usage", "demo_ready", "known_issues", "changelog"]

    @classmethod
    def validate(cls, docs: Dict[str, Any]) -> List[str]:
        errors = []
        for key in cls.REQUIRED:
            if key not in docs:
                errors.append(f"DOCS missing required key: '{key}'")
        if not isinstance(docs.get("known_issues", []), list):
            errors.append("DOCS.known_issues must be a list")
        if not isinstance(docs.get("changelog", []), list):
            errors.append("DOCS.changelog must be a list")
        return errors

# ── end of DocsValidator ──────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  DASHBOARD BASE CLASS
# ──────────────────────────────────────────────────────────────────────────────

class Dashboard(ABC):
    """
    Base class for all SDOA Dashboard modules.

    Subclasses MUST define:
        MANIFEST: Dict  — machine-readable wiring
        DOCS:     Dict  — human-readable narrative
        render()        — main page content

    Subclasses MAY define:
        sidebar()       — module-specific sidebar widgets
        on_load()       — one-time setup per session
        verify()        — health check (NEW v1.2.0)
    """

    # ── These must be overridden ──────────────────────────────────────────────
    MANIFEST: Dict[str, Any] = {}
    DOCS:     Dict[str, Any] = {}

    # ── Class-level demo mode flag ────────────────────────────────────────────
    # Set to True globally in app.py for demo sessions:
    #   Dashboard.DEMO_MODE = True
    DEMO_MODE: bool = False

    # ──────────────────────────────────────────────────────────────────────────
    #  INIT
    # ──────────────────────────────────────────────────────────────────────────

    def __init__(self, db=None):
        # Validate MANIFEST
        manifest_errors = ManifestValidator.validate(self.MANIFEST)
        if manifest_errors:
            raise ValueError(
                f"Module '{self.__class__.__name__}' MANIFEST invalid:\n"
                + "\n".join(f"  • {e}" for e in manifest_errors)
            )

        # Validate DOCS
        docs_errors = DocsValidator.validate(self.DOCS)
        if docs_errors:
            raise ValueError(
                f"Module '{self.__class__.__name__}' DOCS invalid:\n"
                + "\n".join(f"  • {e}" for e in docs_errors)
            )

        # Inject DB — wrap in ScopedProxy if db_tables are declared
        if db is not None:
            declared_tables = self.MANIFEST.get("db_tables", [])
            if declared_tables:
                self._db = ScopedDBProxy(db, declared_tables, self.id)
            else:
                self._db = db
        else:
            self._db = None

        # Pre-initialize declared session keys to None
        for key in self.MANIFEST.get("session_keys", []):
            ns_key = self._ns(key)
            if ns_key not in st.session_state:
                st.session_state[ns_key] = None

    # ──────────────────────────────────────────────────────────────────────────
    #  CONVENIENCE PROPERTIES
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def id(self) -> str:
        return self.MANIFEST.get("id", self.__class__.__name__)

    @property
    def label(self) -> str:
        return self.MANIFEST.get("label", self.id)

    @property
    def icon(self) -> str:
        return self.MANIFEST.get("icon", "📦")

    @property
    def version(self) -> str:
        return self.MANIFEST.get("version", "0.0.0")

    @property
    def pitch(self) -> str:
        """One-liner elevator pitch (optional MANIFEST field)."""
        return self.MANIFEST.get("pitch", self.DOCS.get("summary", ""))

    @property
    def status(self) -> str:
        return self.MANIFEST.get("status", "active")

    @property
    def page_key(self) -> str:
        return self.MANIFEST.get("page_key", self.id)

    @property
    def demo_ready(self) -> bool:
        return bool(self.DOCS.get("demo_ready", False))

    @property
    def db(self):
        if self._db is None:
            raise RuntimeError(
                f"Module '{self.id}' accessed self.db but no db instance was injected. "
                f"Add 'database' to MANIFEST['depends_on']."
            )
        return self._db

    # ──────────────────────────────────────────────────────────────────────────
    #  SESSION STATE HELPERS  (namespaced)
    # ──────────────────────────────────────────────────────────────────────────

    def _ns(self, key: str) -> str:
        return f"_mod_{self.id}_{key}"

    def state(self, key: str, default=None) -> Any:
        return st.session_state.get(self._ns(key), default)

    def set_state(self, key: str, value: Any) -> None:
        st.session_state[self._ns(key)] = value

    def clear_state(self, key: str) -> None:
        ns = self._ns(key)
        if ns in st.session_state:
            del st.session_state[ns]

    # ──────────────────────────────────────────────────────────────────────────
    #  LIFECYCLE HOOKS
    # ──────────────────────────────────────────────────────────────────────────

    def verify(self) -> List[str]:
        """
        Health-check hook — runs before on_load().
        Returns a list of warning strings.
        Empty list = all clear.

        Default implementation checks that declared db_tables actually exist
        in the database. Override to add module-specific checks.
        """
        warnings = []
        if self._db is None:
            return warnings

        declared_tables = self.MANIFEST.get("db_tables", [])
        if not declared_tables:
            return warnings

        try:
            from database import get_conn
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                existing = {row[0] for row in cur.fetchall()}

            for table in declared_tables:
                if table not in existing:
                    warnings.append(
                        f"Table '{table}' declared in MANIFEST.db_tables "
                        f"does not exist in the database."
                    )
        except Exception as exc:
            warnings.append(f"verify() could not check tables: {exc}")

        return warnings

    def on_load(self) -> None:
        """Called once per session when user first navigates to this module."""
        pass

    def sidebar(self) -> None:
        """Module-specific sidebar widgets. Called every render cycle."""
        pass

    @abstractmethod
    def render(self) -> None:
        """Main page content. Must be implemented by every module."""

    # ──────────────────────────────────────────────────────────────────────────
    #  INTERNAL RENDERERS
    # ──────────────────────────────────────────────────────────────────────────

    def _render_stub(self) -> None:
        st.title(f"{self.icon} {self.label}")
        st.info(
            f"**{self.label}** is on the roadmap.  \n"
            f"{self.pitch or self.DOCS.get('summary', '')}  \n\n"
            f"*Status: Coming soon*"
        )
        if self.DOCS.get("known_issues"):
            with st.expander("Known issues"):
                for issue in self.DOCS["known_issues"]:
                    st.caption(f"• {issue}")

    def _render_disabled(self) -> None:
        st.info(f"{self.icon} **{self.label}** is currently disabled.")

    def _render_crash(self, exc: Exception) -> None:
        st.error(f"**{self.icon} {self.label}** encountered an error.")
        st.exception(exc)
        with st.expander("Module manifest"):
            st.json(self.MANIFEST)

    def _render_demo_warning(self) -> None:
        """Shown at the top of every page when DEMO_MODE is active."""
        st.warning(
            "🎬 **Demo Mode** — showing live data. "
            "Sensitive fields are visible. "
            "Do not commit changes during the demo.",
            icon="🎬"
        )

    def _render_verify_warnings(self, warnings: List[str]) -> None:
        """Shown when verify() returns issues."""
        for w in warnings:
            st.warning(f"⚠️ Health check: {w}")

# ── end of Dashboard ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  STUB MIXIN
# ──────────────────────────────────────────────────────────────────────────────

class StubMixin:
    """
    Mixin for modules that are declared but not yet implemented.
    Provides a concrete render() so the class can be instantiated
    without raising AbstractMethodError.
    """

    def render(self) -> None:
        self._render_stub()

# ── end of StubMixin ──────────────────────────────────────────────────────────
