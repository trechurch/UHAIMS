# ──────────────────────────────────────────────────────────────────────────────
#  database_doc.py  —  Diagnostic + Spec Printer
#  Companion doc script for InventoryDatabase service
#
#  Run from repo root:
#    python database_doc.py              # full spec sheet
#    python database_doc.py --validate   # pass/fail only
#    python database_doc.py --ping       # test live DB connection
#
#  NOTE: This is a SERVICE companion, not a module companion.
#        It reads SERVICE_MANIFEST + SERVICE_DOCS instead of MANIFEST + DOCS.
#
#  v1.0.0
# ──────────────────────────────────────────────────────────────────────────────

__version__ = "1.0.0"
__service__  = "database"

import argparse
import os
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

    # stub secrets so get_connection_string() falls through to env var
    class _Secrets(dict):
        def __getitem__(self, k): raise KeyError(k)
    st.secrets = _Secrets()

    sys.modules.setdefault("streamlit", st)

_stub_streamlit()

# ── end of stub ───────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  IMPORT TARGET
# ──────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

try:
    from database import InventoryDatabase
    _IMPORT_OK  = True
    _IMPORT_ERR = None
except Exception as exc:
    _IMPORT_OK  = False
    _IMPORT_ERR = exc
    InventoryDatabase = None

# ── end of import ─────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  VALIDATION
# ──────────────────────────────────────────────────────────────────────────────

_MANIFEST_REQUIRED = {"id", "label", "version", "type", "backend",
                       "connection", "secret_key", "db_tables", "provides"}
_DOCS_REQUIRED     = {"summary", "usage", "demo_ready", "known_issues", "changelog"}


def _validate() -> list:
    results = []

    # 1. Import
    if not _IMPORT_OK:
        results.append(("FAIL", "Import", str(_IMPORT_ERR)))
        return results
    results.append(("PASS", "Import", "database.py imported successfully"))

    # 2. SERVICE_MANIFEST present
    sm = getattr(InventoryDatabase, "SERVICE_MANIFEST", None)
    if not sm:
        results.append(("FAIL", "SERVICE_MANIFEST", "Not found on InventoryDatabase class"))
    else:
        missing = _MANIFEST_REQUIRED - set(sm.keys())
        if missing:
            results.append(("FAIL", "SERVICE_MANIFEST", f"Missing keys: {missing}"))
        else:
            results.append(("PASS", "SERVICE_MANIFEST", "All required keys present"))

    # 3. SERVICE_DOCS present
    sd = getattr(InventoryDatabase, "SERVICE_DOCS", None)
    if not sd:
        results.append(("FAIL", "SERVICE_DOCS", "Not found on InventoryDatabase class"))
    else:
        missing = _DOCS_REQUIRED - set(sd.keys())
        if missing:
            results.append(("FAIL", "SERVICE_DOCS", f"Missing keys: {missing}"))
        else:
            results.append(("PASS", "SERVICE_DOCS", "All required keys present"))

    # 4. Version semver
    v = (sm or {}).get("version", "")
    if v and len(v.split(".")) == 3:
        results.append(("PASS", "version", f"Semver OK: {v}"))
    else:
        results.append(("WARN", "version", f"Version looks odd: {repr(v)}"))

    # 5. DB URL configured
    url = os.environ.get("SUPABASE_DB_URL", "")
    if url:
        results.append(("PASS", "SUPABASE_DB_URL", "Environment variable is set"))
    else:
        results.append(("WARN", "SUPABASE_DB_URL",
                        "Not set in environment — will need st.secrets at runtime"))

    # 6. key_format declared
    kf = (sm or {}).get("key_format", "")
    if kf:
        results.append(("PASS", "key_format", f"Declared: {kf}"))
    else:
        results.append(("WARN", "key_format", "Not declared in SERVICE_MANIFEST"))

    # 7. demo_ready
    dr = (sd or {}).get("demo_ready", False)
    results.append((
        "PASS" if dr else "WARN",
        "demo_ready",
        "Marked demo ready ✅" if dr else "NOT marked demo ready 🚧",
    ))

    # 8. known_issues count
    ki = (sd or {}).get("known_issues", [])
    results.append(("PASS" if not ki else "WARN", "known_issues",
                    f"{len(ki)} known issue(s)"))

    return results

# ── end of validation ─────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  LIVE CONNECTION PING
# ──────────────────────────────────────────────────────────────────────────────

def _ping() -> bool:
    """Attempt a real DB connection and run SELECT 1."""
    if not _IMPORT_OK:
        print(f"  ❌  Cannot ping — import failed: {_IMPORT_ERR}")
        return False
    try:
        from database import get_conn
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        print("  ✅  Database connection successful")
        return True
    except Exception as exc:
        print(f"  ❌  Connection failed: {exc}")
        return False

# ── end of ping ───────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  PRINTERS
# ──────────────────────────────────────────────────────────────────────────────

_W = 72

def _hr(c="─"): print(c * _W)
def _h1(t):     print(); _hr("═"); print(f"  {t}"); _hr("═")
def _h2(t):     print(); _hr();    print(f"  {t}"); _hr()
def _row(k, v): print(f"  {k:<26} {v}")


def print_spec():
    if not _IMPORT_OK:
        print(f"\n❌  Import failed: {_IMPORT_ERR}\n")
        return

    sm = InventoryDatabase.SERVICE_MANIFEST
    sd = InventoryDatabase.SERVICE_DOCS

    _h1("🗄️  InventoryDatabase  —  Service Spec Sheet")
    print(f"  database_doc.py v{__version__}  ·  {date.today()}")

    _h2("Identity")
    _row("ID:",            sm.get("id","?"))
    _row("Label:",         sm.get("label","?"))
    _row("Version:",       sm.get("version","?"))
    _row("Type:",          sm.get("type","?"))
    _row("Backend:",       sm.get("backend","?"))
    _row("Connection:",    sm.get("connection","?"))
    _row("Secret Key:",    sm.get("secret_key","?"))
    _row("Key Format:",    sm.get("key_format","?"))
    _row("Demo Ready:",    "✅ YES" if sd.get("demo_ready") else "🚧 NO")

    _h2("Database Tables Owned")
    for t in sm.get("db_tables", []):
        print(f"  - {t}")

    _h2("Public API  (methods available to modules via self.db)")
    for m in sm.get("provides", []):
        print(f"  • {m}")

    _h2("Summary")
    print(f"  {sd.get('summary','—')}")

    _h2("Usage")
    print(f"  {sd.get('usage','—')}")

    notes = (sd.get("notes") or "").strip()
    if notes:
        _h2("Notes")
        for sentence in notes.replace(". ", ".\n").splitlines():
            s = sentence.strip()
            if s:
                print(f"  {s}")

    _h2("Known Issues")
    issues = sd.get("known_issues", [])
    if issues:
        for i in issues:
            print(f"  ⚠️  {i}")
    else:
        print("  ✅  None")

    _h2("Changelog")
    cl = sd.get("changelog", [])
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
    print(f"\n  Validation Report — InventoryDatabase")
    _hr()
    results  = _validate()
    all_pass = True
    for status, check, msg in results:
        icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ "}.get(status, "  ")
        print(f"  {icon}  {check:<26} {msg}")
        if status == "FAIL":
            all_pass = False
    _hr()
    print("  All checks passed.\n" if all_pass
          else "  ❌  Failures detected. Fix before deploying.\n")
    return all_pass

# ── end of printers ───────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="UHA IMS — database service diagnostic tool"
    )
    parser.add_argument("--validate", action="store_true",
                        help="Validation checks only (exit 1 on failure)")
    parser.add_argument("--ping",     action="store_true",
                        help="Test live database connection")
    args = parser.parse_args()

    if args.validate:
        ok = print_validation()
        sys.exit(0 if ok else 1)
    elif args.ping:
        print()
        _hr()
        print("  DB Connection Ping")
        _hr()
        ok = _ping()
        _hr()
        print()
        sys.exit(0 if ok else 1)
    else:
        print_spec()
        print_validation()

# ── end of database_doc.py ────────────────────────────────────────────────────
