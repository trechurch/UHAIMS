# ──────────────────────────────────────────────────────────────────────────────
#  registry.py  —  Module Registry + Auto-Discovery + Dispatch
#
#  Responsibilities:
#    1. Scan modules/ folder and import every Dashboard subclass
#    2. Validate each MANIFEST + DOCS (fails loudly at startup)
#    3. Build nav structures (menu items, sidebar entries) from manifests
#    4. Dispatch routing — given a page_key, call the right module
#    5. Inject shared services (db) into modules at instantiation
#
#  app.py calls:
#    registry = get_registry(db=get_db())
#    registry.dispatch(st.session_state.page_key)
#
#  That is all app.py needs to know.
#
#  v1.0.0
# ──────────────────────────────────────────────────────────────────────────────

__version__ = "1.0.0"

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type

import streamlit as st

from base import Dashboard, ManifestError, DocsError, StubMixin

# ── end of imports ────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  DISCOVERY
# ──────────────────────────────────────────────────────────────────────────────

def _discover_dashboard_classes(modules_dir: Path) -> List[Type[Dashboard]]:
    """
    Scan modules_dir for .py files, import each, collect Dashboard subclasses.
    Skips _doc.py companions, __init__.py, and base.py.
    Logs warnings on import errors and continues — one bad module never
    kills the whole app.
    """
    found: List[Type[Dashboard]] = []

    for py_file in sorted(modules_dir.glob("*.py")):
        if py_file.stem.startswith("_"):
            continue
        if py_file.stem in ("base",):
            continue
        if py_file.stem.endswith("_doc"):
            continue

        module_name = f"modules.{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            mod  = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
        except Exception as exc:
            st.warning(f"[registry] Could not import {py_file.name}: {exc}")
            continue

        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if (
                issubclass(obj, Dashboard)
                and obj is not Dashboard
                and obj is not StubMixin
                and obj.__module__ == module_name
            ):
                found.append(obj)

    return found

# ── end of discovery ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  REGISTRY
# ──────────────────────────────────────────────────────────────────────────────

class ModuleRegistry:
    """
    Central wiring point for all dashboard modules.

    Instantiation:
        registry = ModuleRegistry(db=get_db())

    Query:
        registry.all()                     -> list of all registered modules
        registry.by_page_key("import")     -> Dashboard | None
        registry.by_id("import_dashboard") -> Dashboard | None
        registry.nav_items("Dashboards")   -> list of menu contribution dicts
        registry.sidebar_items()           -> list of sidebar contribution dicts

    Dispatch:
        registry.dispatch("import")        -> calls module.render()
    """

    def __init__(self, db=None, modules_dir: Optional[Path] = None):
        self._db          = db
        self._modules_dir = modules_dir or (Path(__file__).parent / "modules")
        self._instances:  Dict[str, Dashboard] = {}   # module id -> instance
        self._by_page:    Dict[str, str]        = {}   # page_key  -> module id
        self._errors:     List[str]             = []
        self._load()

    # ── Internal load ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._modules_dir.exists():
            st.error(
                f"[registry] modules/ directory not found at {self._modules_dir}. "
                f"Create it and add your dashboard modules."
            )
            return

        classes = _discover_dashboard_classes(self._modules_dir)

        for cls in classes:
            try:
                instance = cls(db=self._db)
            except (ManifestError, DocsError) as exc:
                self._errors.append(str(exc))
                st.warning(f"[registry] Skipping {cls.__name__}: {exc}")
                continue
            except Exception as exc:
                self._errors.append(str(exc))
                st.warning(f"[registry] Error instantiating {cls.__name__}: {exc}")
                continue

            mid = instance.id
            pk  = instance.page_key

            if mid in self._instances:
                st.warning(
                    f"[registry] Duplicate module id '{mid}' "
                    f"({cls.__name__} conflicts with existing). Skipping."
                )
                continue

            if pk in self._by_page:
                st.warning(
                    f"[registry] Duplicate page_key '{pk}' "
                    f"({cls.__name__} conflicts with existing). Skipping."
                )
                continue

            self._instances[mid] = instance
            self._by_page[pk]    = mid

    # ── Public query API ──────────────────────────────────────────────────────

    def all(self) -> List[Dashboard]:
        """All registered non-disabled modules."""
        return [m for m in self._instances.values() if m.status != "disabled"]

    def by_id(self, module_id: str) -> Optional[Dashboard]:
        return self._instances.get(module_id)

    def by_page_key(self, page_key: str) -> Optional[Dashboard]:
        mid = self._by_page.get(page_key)
        return self._instances.get(mid) if mid else None

    def page_keys(self) -> List[str]:
        return list(self._by_page.keys())

    def has_errors(self) -> bool:
        return bool(self._errors)

    def errors(self) -> List[str]:
        return list(self._errors)

    # ── Navigation builders ───────────────────────────────────────────────────

    def nav_items(self, menu_parent: str) -> List[Dict]:
        """
        Menu contribution dicts for all modules whose
        MANIFEST["menu"]["parent"] == menu_parent.

        Returns list of:
          { label, page_key, icon, shortcut, position, status }
        sorted by position.
        """
        items = []
        for m in self.all():
            menu_cfg = m.MANIFEST.get("menu", {})
            if menu_cfg.get("parent") == menu_parent:
                items.append({
                    "label":    menu_cfg.get("label", m.label),
                    "page_key": m.page_key,
                    "icon":     m.icon,
                    "shortcut": menu_cfg.get("shortcut", ""),
                    "position": menu_cfg.get("position", 99),
                    "status":   m.status,
                })
        return sorted(items, key=lambda x: x["position"])

    def sidebar_items(self) -> List[Dict]:
        """
        Sidebar nav dicts for all modules whose
        MANIFEST["sidebar"]["show"] == True.

        Returns list of:
          { label, page_key, icon, section, position, status }
        sorted by section then position.
        """
        items = []
        for m in self.all():
            sb_cfg = m.MANIFEST.get("sidebar", {})
            if sb_cfg.get("show", False):
                items.append({
                    "label":    m.label,
                    "page_key": m.page_key,
                    "icon":     m.icon,
                    "section":  sb_cfg.get("section", ""),
                    "position": sb_cfg.get("position", 99),
                    "status":   m.status,
                })
        return sorted(items, key=lambda x: (x["section"], x["position"]))

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def dispatch(self, page_key: str) -> None:
        """
        Route a page_key to the correct module.

        Sequence:
          1. Look up module by page_key
          2. Fire on_load once per session
          3. Call module.sidebar()
          4. Call module.render() (or _render_stub() for stubs)

        Graceful fallback on every failure — never white-screens.
        """
        module = self.by_page_key(page_key)

        if module is None:
            self._render_404(page_key)
            return

        if module.status == "disabled":
            self._render_disabled(module)
            return

        # on_load once per session
        load_key = f"_registry_loaded_{module.id}"
        if not st.session_state.get(load_key, False):
            try:
                module.on_load()
                st.session_state[load_key] = True
            except Exception as exc:
                st.error(f"[{module.label}] on_load() failed: {exc}")

        # sidebar
        try:
            module.sidebar()
        except Exception as exc:
            st.sidebar.error(f"[{module.label}] sidebar() error: {exc}")

        # render
        try:
            if module.is_stub:
                module._render_stub()
            else:
                module.render()
        except Exception as exc:
            self._render_crash(module, exc)

    # ── on_unload ─────────────────────────────────────────────────────────────

    def on_navigate_away(self, previous_page_key: str) -> None:
        module = self.by_page_key(previous_page_key)
        if module:
            try:
                module.on_unload()
            except Exception:
                pass  # non-fatal

    # ── Fallback renderers ────────────────────────────────────────────────────

    @staticmethod
    def _render_404(page_key: str) -> None:
        st.title("404 — Page Not Found")
        st.error(
            f"No module is registered for page key **`{page_key}`**.  "
            f"Check the module's MANIFEST `page_key` field."
        )

    @staticmethod
    def _render_disabled(module: Dashboard) -> None:
        st.title(f"{module.icon} {module.label}")
        st.warning(f"**{module.label}** is currently disabled.")

    @staticmethod
    def _render_crash(module: Dashboard, exc: Exception) -> None:
        st.title(f"{module.icon} {module.label}")
        st.error(
            f"**{module.label}** encountered a render error.  \n"
            f"`{type(exc).__name__}: {exc}`"
        )
        with st.expander("Module manifest (for debugging)"):
            st.json(module.MANIFEST)

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def diagnostics(self) -> Dict:
        return {
            "total_modules":    len(self._instances),
            "active":           len([m for m in self._instances.values() if m.status == "active"]),
            "stubs":            len([m for m in self._instances.values() if m.status == "stub"]),
            "disabled":         len([m for m in self._instances.values() if m.status == "disabled"]),
            "load_errors":      self._errors,
            "registered_pages": list(self._by_page.keys()),
            "manifests":        {mid: m.MANIFEST for mid, m in self._instances.items()},
        }

# ── end of ModuleRegistry ─────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_registry(db=None) -> ModuleRegistry:
    """
    Cached singleton — _load() runs exactly once per app process.
    Safe to call from anywhere.
    """
    return ModuleRegistry(db=db)

# ── end of registry.py ────────────────────────────────────────────────────────
