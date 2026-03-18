# ──────────────────────────────────────────────────────────────────────────────
#  modules/dashboard_module_doc.py  —  Diagnostic + Spec Printer
#  Companion doc script for DatabaseDashboard
#
#  Run from repo root:
#    python modules/dashboard_module_doc.py              # full spec sheet
#    python modules/dashboard_module_doc.py --validate   # pass/fail only
#    python modules/dashboard_module_doc.py --markdown   # markdown output
#
#  Copy this file for every new module.
#  Change only the two constants directly below.
#
#  v1.0.0
# ──────────────────────────────────────────────────────────────────────────────

# ── CHANGE THESE TWO LINES WHEN COPYING TO A NEW MODULE ──────────────────────
__module_id__  = "dashboard_module"                          # matches MANIFEST id
__cls_import__ = "from modules.dashboard_module import DatabaseDashboard as _Target"
# ── end of per-module constants ───────────────────────────────────────────────

__version__ = "1.0.0"

import argparse
import sys
import types
from pathlib import Path
from datetime import date

# ── end of imports ────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  STREAMLIT STUB — allows import without a running Streamlit server
# ──────────────────────────────────────────────────────────────────────────────

def _stub_streamlit():
    st = types.ModuleType("streamlit")
    class _SS(dict):
        def __getattr__(self, k): return self.get(k)
        def __setattr__(self, k, v): self[k] = v
    st.session_state = _SS()
    st.cache_resource = lambda f: f
    sys.modules.setdefault("streamlit", st)

_stub_streamlit()

# ── end of stub ───────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  IMPORT TARGET
# ──────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    exec(__cls_import__)           # imports _Target into local scope
    _IMPORT_OK  = True
    _IMPORT_ERR = None
except Exception as exc:
    _IMPORT_OK  = False
    _IMPORT_ERR = exc
    _Target     = None             # noqa: F841 — used below via locals()

# ── end of import ─────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  VALIDATION
# ──────────────────────────────────────────────────────────────────────────────

def _validate() -> list:
    results = []
    cls = locals().get("_Target") or globals().get("_Target")

    if not _IMPORT_OK:
        results.append(("FAIL", "Import", str(_IMPORT_ERR)))
        return results
    results.append(("PASS", "Import", "Module imported successfully"))

    # MANIFEST
    try:
        from base import ManifestValidator
        ManifestValidator.validate(cls.MANIFEST, cls.__name__)
        results.append(("PASS", "MANIFEST", "All required keys present and valid"))
    except Exception as exc:
        results.append(("FAIL", "MANIFEST", str(exc)))

    # DOCS
    try:
        from base import DocsValidator
        DocsValidator.validate(cls.DOCS, cls.__name__)
        results.append(("PASS", "DOCS", "All required keys present and valid"))
    except Exception as exc:
        results.append(("FAIL", "DOCS", str(exc)))

    # render() implemented
    if hasattr(cls, "render") and not getattr(cls.render, "__isabstractmethod__", False):
        results.append(("PASS", "render()", "Concrete render() found"))
    else:
        results.append(("FAIL", "render()", "render() is abstract or missing"))

    # version semver
    v = cls.MANIFEST.get("version", "")
    if v and len(v.split(".")) == 3:
        results.append(("PASS", "version", f"Semver OK: {v}"))
    else:
        results.append(("WARN", "version", f"Version looks odd: {repr(v)}"))

    # demo_ready
    dr = cls.DOCS.get("demo_ready", False)
    results.append((
        "PASS" if dr else "WARN",
        "demo_ready",
        "Marked demo ready ✅" if dr else "NOT marked demo ready 🚧",
    ))

    # known_issues
    ki = cls.DOCS.get("known_issues", [])
    results.append(("PASS" if not ki else "WARN", "known_issues", f"{len(ki)} known issue(s)"))

    return results

# ── end of validation ─────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  PRINTERS
# ──────────────────────────────────────────────────────────────────────────────

_W = 72

def _hr(c="─"): print(c * _W)
def _h1(t):     print(); _hr("═"); print(f"  {t}"); _hr("═")
def _h2(t):     print(); _hr();    print(f"  {t}"); _hr()
def _row(k, v): print(f"  {k:<24} {v}")


def print_spec():
    cls = globals().get("_Target")
    if not _IMPORT_OK or cls is None:
        print(f"\n❌  Import failed: {_IMPORT_ERR}\n")
        return

    m = cls.MANIFEST
    d = cls.DOCS

    _h1(f"{m.get('icon','')}  {m.get('label','?')}  —  Module Spec Sheet")
    print(f"  {__module_id__}_doc.py v{__version__}  ·  {date.today()}")

    _h2("Identity")
    _row("ID:",          m.get("id","?"))
    _row("Label:",       m.get("label","?"))
    _row("Version:",     m.get("version","?"))
    _row("Status:",      m.get("status","?"))
    _row("Page Key:",    m.get("page_key","?"))
    _row("Min Role:",    m.get("permissions",{}).get("min_role","any"))
    _row("Demo Ready:",  "✅ YES" if d.get("demo_ready") else "🚧 NO")

    _h2("Navigation")
    menu = m.get("menu", {})
    sb   = m.get("sidebar", {})
    _row("Menu Parent:",      menu.get("parent","—"))
    _row("Menu Label:",       menu.get("label", m.get("label","—")))
    _row("Menu Shortcut:",    menu.get("shortcut","—"))
    _row("Menu Position:",    str(menu.get("position","—")))
    _row("Sidebar Section:",  sb.get("section","—") or "(top)")
    _row("Sidebar Position:", str(sb.get("position","—")))
    _row("Shows in Sidebar:", str(sb.get("show", False)))

    _h2("Dependencies")
    for dep in m.get("depends_on", []) or ["None"]: print(f"  - {dep}")

    _h2("Database Tables")
    for t in m.get("db_tables", []) or ["None"]: print(f"  - {t}")

    _h2("Session State Keys (namespaced)")
    keys = m.get("session_keys", [])
    if keys:
        for k in keys: print(f"  - _mod_{m.get('id','')}_{k}")
    else:
        print("  None declared")

    _h2("Abilities")
    for a in m.get("abilities", []) or ["None declared"]: print(f"  • {a}")

    _h2("Summary")
    print(f"  {d.get('summary','—')}")

    _h2("Usage")
    print(f"  {d.get('usage','—')}")

    notes = (d.get("notes") or "").strip()
    if notes:
        _h2("Notes")
        print(f"  {notes}")

    _h2("Known Issues")
    issues = d.get("known_issues", [])
    if issues:
        for i in issues: print(f"  ⚠️  {i}")
    else:
        print("  ✅  None")

    _h2("Changelog")
    cl = d.get("changelog", [])
    if cl:
        print(f"  {'Version':<10} {'Date':<14} Note")
        print(f"  {'─'*8:<10} {'─'*12:<14} {'─'*30}")
        for e in cl:
            print(f"  {e.get('version','?'):<10} {e.get('date','?'):<14} {e.get('note','?')}")
    else:
        print("  No entries")

    _hr("═")
    print()


def print_validation() -> bool:
    cls = globals().get("_Target")
    label = cls.__name__ if cls else __module_id__
    print(f"\n  Validation Report — {label}")
    _hr()
    results = _validate()
    all_pass = True
    for status, check, msg in results:
        icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ "}.get(status, "  ")
        print(f"  {icon}  {check:<24} {msg}")
        if status == "FAIL":
            all_pass = False
    _hr()
    print("  All checks passed.\n" if all_pass else "  ❌  Failures detected. Fix before deploying.\n")
    return all_pass


def print_markdown():
    try:
        from docs_generator import generate_module_doc
        src = Path(__file__).parent / f"{__module_id__}.py"
        cls = globals().get("_Target")
        print(generate_module_doc(cls, src))
    except Exception as exc:
        print(f"Could not generate markdown: {exc}")

# ── end of printers ───────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"UHA IMS — {__module_id__} diagnostic tool"
    )
    parser.add_argument("--validate", action="store_true",
                        help="Validation checks only (exit 1 on failure)")
    parser.add_argument("--markdown", action="store_true",
                        help="Print markdown spec sheet")
    args = parser.parse_args()

    if args.validate:
        ok = print_validation()
        sys.exit(0 if ok else 1)
    elif args.markdown:
        print_markdown()
    else:
        print_spec()
        print_validation()

# ── end of dashboard_module_doc.py ────────────────────────────────────────────
