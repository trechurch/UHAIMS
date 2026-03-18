# ──────────────────────────────────────────────────────────────────────────────
#  registry.py  —  Module Registry + Auto-Discovery + Dispatch
#
#  v1.0.2  —  Fix: discovery errors now stored in self._errors so they
#              appear in diagnostics().  Previously they were silently
#              swallowed by st.warning() and never surfaced.
# ──────────────────────────────────────────────────────────────────────────────

__version__ = "1.0.2"

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

import streamlit as st

from base import Dashboard, ManifestError, DocsError, StubMixin

# ── end of imports ────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  DISCOVERY
# ──────────────────────────────────────────────────────────────────────────────

def _discover_dashboard_classes(
    modules_dir: Path,
    errors: List[str],          # ← caller passes in the errors list
) -> List[Type[Dashboard]]:
    """
    Scan modules_dir for .py files, import each, collect Dashboard subclasses.
    All errors are appended to the caller-supplied `errors` list so they
    surface in registry.diagnostics().
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
            msg = f"Import error — {py_file.name}: {type(exc).__name__}: {exc}"
            errors.append(msg)
            continue

        classes_found = 0
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if (
                issubclass(obj, Dashboard)
                and obj is not Dashboard
                and obj is not StubMixin
                and obj.__module__ == module_name
            ):
                found.append(obj)
                classes_found += 1

        if classes_found == 0:
            errors.append(
                f"No Dashboard subclass found in {py_file.name} "
                f"(check class definition and __module__ == '{module_name}')"
            )

    return found

# ── end of discovery ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  REGISTRY
# ──────────────────────────────────────────────────────────────────────────────

class ModuleRegistry:

    def __init__(self, db=None, modules_dir: Optional[Path] = None):
        self._db          = db
        self._modules_dir = modules_dir or (Path(__file__).parent / "modules")
        self._instances:  Dict[str, Dashboard] = {}
        self._by_page:    Dict[str, str]        = {}
        self._errors:     List[str]             = []
        self._load()

    # ── Internal load ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._modules_dir.exists():
            self._errors.append(
                f"modules/ directory not found at {self._modules_dir}"
            )
            return

        # Pass self._errors so discovery errors are captured
        classes = _discover_dashboard_classes(self._modules_dir, self._errors)

        for cls in classes:
            try:
                instance = cls(db=self._db)
            except (ManifestError, DocsError) as exc:
                self._errors.append(f"Manifest/Docs error — {cls.__name__}: {exc}")
                continue
            except Exception as exc:
                self._errors.append(
                    f"Instantiation error — {cls.__name__}: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

            mid = instance.id
            pk  = instance.page_key

            if mid in self._instances:
                self._errors.append(
                    f"Duplicate module id '{mid}' — {cls.__name__} skipped"
                )
                continue

            if pk in self._by_page:
                self._errors.append(
                    f"Duplicate page_key '{pk}' — {cls.__name__} skipped"
                )
                continue

            self._instances[mid] = instance
            self._by_page[pk]    = mid

    # ── Public query API ──────────────────────────────────────────────────────

    def all(self) -> List[Dashboard]:
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
        module = self.by_page_key(page_key)

        if module is None:
            self._render_404(page_key)
            return

        if module.status == "disabled":
            self._render_disabled(module)
            return

        load_key = f"_registry_loaded_{module.id}"
        if not st.session_state.get(load_key, False):
            try:
                module.on_load()
                st.session_state[load_key] = True
            except Exception as exc:
                st.error(f"[{module.label}] on_load() failed: {exc}")

        try:
            module.sidebar()
        except Exception as exc:
            st.sidebar.error(f"[{module.label}] sidebar() error: {exc}")

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
                pass

    # ── Fallback renderers ────────────────────────────────────────────────────

    @staticmethod
    def _render_404(page_key: str) -> None:
        st.title("404 — Page Not Found")
        st.error(
            f"No module registered for page key **`{page_key}`**.  \n"
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
            f"**{module.label}** render error:  \n"
            f"`{type(exc).__name__}: {exc}`"
        )
        with st.expander("Module manifest"):
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
def get_registry(_db=None) -> ModuleRegistry:
    """
    Cached singleton. _db prefix bypasses Streamlit's unhashable param error.
    """
    return ModuleRegistry(db=_db)

# ── end of registry.py ────────────────────────────────────────────────────────
