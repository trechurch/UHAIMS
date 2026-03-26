# ──────────────────────────────────────────────────────────────────────────────
#  registry.py  —  SDOA Module Registry
#
#  v1.0.3  —  verify() called before on_load().
#              DEMO_MODE propagated to all modules.
#              verify() warnings shown before module renders.
# ──────────────────────────────────────────────────────────────────────────────

__version__ = "1.0.3"

import importlib
import inspect
import os
import streamlit as st
from typing import Dict, List, Optional, Any

from base import Dashboard

# ── end of imports ────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  MODULE REGISTRY
# ──────────────────────────────────────────────────────────────────────────────

class ModuleRegistry:

    SERVICE_MANIFEST = {
        "id":      "registry",
        "label":   "Module Registry",
        "version": "1.0.3",
        "type":    "service",
        "provides": [
            "all() -> List[Dashboard]",
            "page_keys() -> List[str]",
            "sidebar_items() -> List[dict]",
            "dispatch(page_key)",
            "on_navigate_away(page_key)",
            "diagnostics() -> dict",
            "has_errors() -> bool",
            "errors() -> List[str]",
        ],
    }

    def __init__(self, db=None, demo_mode: bool = False):
        self._db         = db
        self._demo_mode  = demo_mode
        self._modules:   Dict[str, Dashboard] = {}
        self._page_map:  Dict[str, str]        = {}
        self._errors:    List[str]             = []
        self._loaded:    set                   = set()

        # Propagate demo_mode to base class (class-level flag)
        Dashboard.DEMO_MODE = demo_mode

        self._discover()

    # ──────────────────────────────────────────────────────────────────────────
    #  DISCOVERY
    # ──────────────────────────────────────────────────────────────────────────

    def _discover(self):
        modules_dir = os.path.join(os.path.dirname(__file__), "modules")
        if not os.path.isdir(modules_dir):
            self._errors.append("modules/ directory not found")
            return

        for fname in sorted(os.listdir(modules_dir)):
            if not fname.endswith(".py"):
                continue
            if fname.startswith("_"):
                continue
            if fname.endswith("_doc.py"):
                continue

            module_name = fname[:-3]
            try:
                mod = importlib.import_module(f"modules.{module_name}")
                classes = self._find_dashboard_classes(mod)
                for cls in classes:
                    self._register(cls)
            except Exception as exc:
                self._errors.append(
                    f"Failed to load modules/{fname}: {type(exc).__name__}: {exc}"
                )

    def _find_dashboard_classes(self, module) -> List[type]:
        found = []
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (obj is not Dashboard
                    and issubclass(obj, Dashboard)
                    and obj.__module__ == module.__name__):
                found.append(obj)
        return found

    def _register(self, cls: type):
        try:
            instance = cls(db=self._db)
        except Exception as exc:
            self._errors.append(
                f"Failed to instantiate {cls.__name__}: {type(exc).__name__}: {exc}"
            )
            return

        mod_id   = instance.id
        page_key = instance.page_key

        if mod_id in self._modules:
            self._errors.append(
                f"Duplicate module id '{mod_id}' — "
                f"{cls.__name__} conflicts with existing module"
            )
            return

        if page_key in self._page_map:
            self._errors.append(
                f"Duplicate page_key '{page_key}' — "
                f"{cls.__name__} conflicts with existing module"
            )
            return

        self._modules[mod_id]      = instance
        self._page_map[page_key]   = mod_id

    # ──────────────────────────────────────────────────────────────────────────
    #  PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def all(self) -> List[Dashboard]:
        return list(self._modules.values())

    def page_keys(self) -> List[str]:
        return list(self._page_map.keys())

    def sidebar_items(self) -> List[dict]:
        items = []
        for mod in self._modules.values():
            sidebar_cfg = mod.MANIFEST.get("sidebar", {})
            if not sidebar_cfg.get("show", True):
                continue
            if mod.status == "disabled":
                continue
            items.append({
                "id":       mod.id,
                "label":    mod.label,
                "icon":     mod.icon,
                "page_key": mod.page_key,
                "position": sidebar_cfg.get("position", 99),
                "section":  sidebar_cfg.get("section", ""),
            })
        return sorted(items, key=lambda x: x["position"])

    def on_navigate_away(self, page_key: str) -> None:
        """Called when user navigates away from a module."""
        mod_id = self._page_map.get(page_key)
        if mod_id and hasattr(self._modules[mod_id], "on_navigate_away"):
            try:
                self._modules[mod_id].on_navigate_away()
            except Exception:
                pass

    def dispatch(self, page_key: str) -> None:
        """
        Route to the module for the given page_key.
        Calls verify() → on_load() → sidebar() → render().
        """
        mod_id = self._page_map.get(page_key)
        if not mod_id:
            st.warning(f"No module registered for page_key '{page_key}'")
            return

        mod = self._modules[mod_id]

        # ── Demo mode warning ─────────────────────────────────────────────
        if self._demo_mode:
            mod._render_demo_warning()

        # ── verify() — health check before on_load ────────────────────────
        verify_key = f"_verified_{mod_id}"
        if verify_key not in st.session_state:
            try:
                warnings = mod.verify()
                st.session_state[verify_key] = warnings
            except Exception as exc:
                st.session_state[verify_key] = [f"verify() raised: {exc}"]

        verify_warnings = st.session_state.get(verify_key, [])
        if verify_warnings:
            mod._render_verify_warnings(verify_warnings)

        # ── on_load() — once per session ──────────────────────────────────
        load_key = f"_loaded_{mod_id}"
        if load_key not in st.session_state:
            try:
                mod.on_load()
                st.session_state[load_key] = True
            except Exception as exc:
                st.session_state[load_key] = False
                mod._render_crash(exc)
                return

        # ── sidebar() ─────────────────────────────────────────────────────
        try:
            mod.sidebar()
        except Exception as exc:
            pass  # sidebar errors shouldn't block render

        # ── render() ─────────────────────────────────────────────────────
        try:
            if mod.status == "stub":
                mod._render_stub()
            elif mod.status == "disabled":
                mod._render_disabled()
            else:
                mod.render()
        except Exception as exc:
            mod._render_crash(exc)

    # ──────────────────────────────────────────────────────────────────────────
    #  DIAGNOSTICS
    # ──────────────────────────────────────────────────────────────────────────

    def diagnostics(self) -> dict:
        active   = sum(1 for m in self._modules.values() if m.status == "active")
        stubs    = sum(1 for m in self._modules.values() if m.status == "stub")
        disabled = sum(1 for m in self._modules.values() if m.status == "disabled")
        return {
            "total_modules":     len(self._modules),
            "active":            active,
            "stubs":             stubs,
            "disabled":          disabled,
            "registered_pages":  sorted(self._page_map.keys()),
            "load_errors":       self._errors,
            "demo_mode":         self._demo_mode,
        }

    def has_errors(self) -> bool:
        return len(self._errors) > 0

    def errors(self) -> List[str]:
        return self._errors

# ── end of ModuleRegistry ─────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  CACHED FACTORY
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_registry(_db=None, _demo_mode: bool = False) -> ModuleRegistry:
    """
    Cached registry singleton.
    _db and _demo_mode use leading underscore to bypass Streamlit's
    cache hash (psycopg2 connections are not hashable).
    """
    return ModuleRegistry(db=_db, demo_mode=_demo_mode)

# ── end of registry.py ────────────────────────────────────────────────────────
