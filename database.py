"""
UHA IMS — Inventory Database Service
PostgreSQL / Supabase backend

v2.1.1  —  import_jobs table added to create_tables().
            New job tracker methods:
              create_job(), update_job(), get_job(), get_recent_jobs(),
              get_active_jobs(), fail_job()
"""

import os
import json
import uuid
import psycopg2
import psycopg2.extras
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

# ── end of imports ────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  CONNECTION HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def get_connection_string() -> str:
    try:
        import streamlit as st
        return st.secrets["SUPABASE_DB_URL"]
    except Exception:
        return os.environ.get("SUPABASE_DB_URL", "")


@contextmanager
def get_conn():
    conn = psycopg2.connect(get_connection_string())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ── end of connection helpers ─────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  INVENTORY DATABASE SERVICE
# ──────────────────────────────────────────────────────────────────────────────

class InventoryDatabase:

    # ──────────────────────────────────────────────────────────────────────────
    #  SERVICE_MANIFEST
    # ──────────────────────────────────────────────────────────────────────────

    SERVICE_MANIFEST = {
        "id":          "database",
        "label":       "Inventory Database",
        "version":     "2.2.0",
        "type":        "service",
        "backend":     "supabase_postgresql",
        "connection":  "session_pooler",
        "secret_key":  "SUPABASE_DB_URL",
        "key_format":  "ITEM NAME||PACKTYPE",
        "db_tables": [
            "items",
            "item_history",
            "price_history",
            "import_jobs",
        ],
        "provides": [
            "add_item(item_data, changed_by)",
            "upsert_item(item_data, doc_date, source_document, changed_by)",
            "get_item(key)",
            "get_last_updated()",
            "get_all_items(record_status)",
            "get_items_by_cost_center(cost_center)",
            "get_low_stock_items()",
            "get_inventory_value()",
            "search_items(term)",
            "count_items(record_status)",
            "item_exists(key)",
            "delete_item(key, changed_by)",
            "update_item_smart(key, incoming, doc_date, source_document, changed_by)",
            "set_override(key, field, value, changed_by)",
            "clear_override(key, field, changed_by)",
            "get_item_history(key, limit)",
            "get_price_history(key, limit)",
            "build_key(item_name, pack_type)",
            "create_job(job_type, source_file, total_rows, triggered_by)",
            "update_job(job_id, **kwargs)",
            "get_job(job_id)",
            "get_recent_jobs(limit)",
            "get_active_jobs()",
            "fail_job(job_id, error)",
        ],
    }

    # ── end of SERVICE_MANIFEST ───────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  SERVICE_DOCS
    # ──────────────────────────────────────────────────────────────────────────

    SERVICE_DOCS = {
        "summary": (
            "Core PostgreSQL/Supabase data layer for all inventory operations. "
            "Injected into dashboard modules via the registry."
        ),
        "usage": (
            "Access via self.db inside any Dashboard subclass. "
            "Never import or instantiate directly inside a module."
        ),
        "demo_ready": True,
        "notes": (
            "v2.1.0 adds import_jobs table for background job tracking. "
            "Must use session pooler endpoint (port 6543). "
            "Canonical item key format is ITEM NAME||PACKTYPE."
        ),
        "known_issues": [
            "Catering cost center requires a separate Supabase connection — not yet wired.",
            "fuzzy_match_description(), score_import_row() not yet ported.",
            "update_quantity_from_count(), log_count_import(), get_import_log() not yet ported.",
        ],
        "changelog": [
            {
                "version": "2.1.0",
                "date":    "2026-03-18",
                "note":    "import_jobs table + job tracker methods added.",
            },
            {
                "version": "2.0.0",
                "date":    "2026-03-17",
                "note":    "SDOA treatment: SERVICE_MANIFEST + SERVICE_DOCS added.",
            },
            {
                "version": "1.0.0",
                "date":    "2025-01-01",
                "note":    "Initial Supabase/PostgreSQL implementation.",
            },
        ],
    }

    # ── end of SERVICE_DOCS ───────────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  INIT
    # ──────────────────────────────────────────────────────────────────────────

    def __init__(self, db_url: str = None, cost_center: str = None):
        if db_url:
            os.environ["SUPABASE_DB_URL"] = db_url
        self._cc = cost_center  # active cost center filter; None = all
        self.create_tables()

    # ── end of init ───────────────────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  COST CENTER FILTER HELPER
    # ──────────────────────────────────────────────────────────────────────────

    def _cc_clause(self, prefix: str = "AND") -> Tuple[str, list]:
        """
        Returns (sql_fragment, params) to append cost_center filtering.
        prefix is "AND" when used after existing WHERE conditions,
        or "WHERE" when it starts the WHERE clause.
        """
        if self._cc:
            return f" {prefix} cost_center = %s", [self._cc]
        return "", []

    # ── end of cost center helper ─────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  SCHEMA
    # ──────────────────────────────────────────────────────────────────────────

    def create_tables(self):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    key                  TEXT PRIMARY KEY,
                    description          TEXT,
                    pack_type            TEXT,
                    cost                 NUMERIC(10,4) DEFAULT 0,
                    per                  TEXT,
                    conv_ratio           NUMERIC(10,4) DEFAULT 1.0,
                    unit                 TEXT,
                    vendor               TEXT,
                    item_number          TEXT,
                    mog                  TEXT,
                    spacer               TEXT,
                    brand                TEXT,
                    last_updated         TIMESTAMPTZ,
                    yield                NUMERIC(10,4) DEFAULT 1.0,
                    gl_code              TEXT,
                    gl_name              TEXT,
                    override_pack_type   TEXT,
                    override_yield       NUMERIC(10,4),
                    override_conv_ratio  NUMERIC(10,4),
                    override_vendor      TEXT,
                    override_item_number TEXT,
                    override_gl          TEXT,
                    status_tag           TEXT DEFAULT 'Standard',
                    quantity_on_hand     NUMERIC(10,4) DEFAULT 0,
                    reorder_point        NUMERIC(10,4) DEFAULT 0,
                    is_chargeable        BOOLEAN DEFAULT TRUE,
                    cost_center          TEXT,
                    record_status        TEXT DEFAULT 'active',
                    created_date         TIMESTAMPTZ DEFAULT NOW(),
                    user_notes           TEXT,
                    gtin                 TEXT
                );

                CREATE TABLE IF NOT EXISTS item_history (
                    history_id      SERIAL PRIMARY KEY,
                    item_key        TEXT REFERENCES items(key),
                    change_date     TIMESTAMPTZ DEFAULT NOW(),
                    change_type     TEXT,
                    field_changed   TEXT,
                    old_value       TEXT,
                    new_value       TEXT,
                    change_source   TEXT,
                    source_document TEXT,
                    changed_by      TEXT,
                    change_reason   TEXT,
                    metadata        JSONB
                );

                CREATE TABLE IF NOT EXISTS price_history (
                    price_id    SERIAL PRIMARY KEY,
                    item_key    TEXT REFERENCES items(key),
                    price       NUMERIC(10,4),
                    doc_date    DATE,
                    source_file TEXT,
                    vendor      TEXT,
                    imported_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS import_jobs (
                    job_id        TEXT PRIMARY KEY,
                    job_type      TEXT NOT NULL DEFAULT 'invoice_import',
                    status        TEXT NOT NULL DEFAULT 'pending',
                    source_file   TEXT,
                    total_rows    INTEGER DEFAULT 0,
                    processed     INTEGER DEFAULT 0,
                    added         INTEGER DEFAULT 0,
                    updated       INTEGER DEFAULT 0,
                    skipped       INTEGER DEFAULT 0,
                    error_count   INTEGER DEFAULT 0,
                    errors        JSONB,
                    triggered_by  TEXT,
                    started_at    TIMESTAMPTZ DEFAULT NOW(),
                    finished_at   TIMESTAMPTZ,
                    notes         TEXT
                );

                CREATE TABLE IF NOT EXISTS count_sessions (
                    session_id    TEXT PRIMARY KEY,
                    cost_center   TEXT NOT NULL,
                    count_date    DATE NOT NULL,
                    status        TEXT DEFAULT 'open',
                    created_by    TEXT,
                    created_at    TIMESTAMPTZ DEFAULT NOW(),
                    committed_at  TIMESTAMPTZ,
                    committed_by  TEXT,
                    notes         TEXT,
                    item_count    INTEGER DEFAULT 0,
                    total_value   NUMERIC(12,4) DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS count_lines (
                    line_id           SERIAL PRIMARY KEY,
                    session_id        TEXT REFERENCES count_sessions(session_id)
                                      ON DELETE CASCADE,
                    item_key          TEXT NOT NULL,
                    description       TEXT,
                    pack_type         TEXT,
                    gl_code           TEXT,
                    gl_name           TEXT,
                    unit_cost         NUMERIC(10,4) DEFAULT 0,
                    quantity_counted  NUMERIC(10,4) DEFAULT 0,
                    extended_value    NUMERIC(12,4) DEFAULT 0,
                    notes             TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_items_description   ON items(description);
                CREATE INDEX IF NOT EXISTS idx_items_gl_code       ON items(gl_code);
                CREATE INDEX IF NOT EXISTS idx_items_vendor        ON items(vendor);
                CREATE INDEX IF NOT EXISTS idx_items_cost_center   ON items(cost_center);
                CREATE INDEX IF NOT EXISTS idx_history_item_key    ON item_history(item_key);
                CREATE INDEX IF NOT EXISTS idx_import_jobs_status  ON import_jobs(status);
                CREATE INDEX IF NOT EXISTS idx_import_jobs_started ON import_jobs(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_count_sessions_cc   ON count_sessions(cost_center);
                CREATE INDEX IF NOT EXISTS idx_count_lines_session ON count_lines(session_id);

                CREATE TABLE IF NOT EXISTS users (
                    username      TEXT PRIMARY KEY,
                    display_name  TEXT,
                    email         TEXT,
                    pin_hash      TEXT,
                    role          TEXT DEFAULT 'editor',
                    auth_method   TEXT DEFAULT 'login_form',
                    is_active     BOOLEAN DEFAULT TRUE,
                    last_login    TIMESTAMPTZ,
                    created_at    TIMESTAMPTZ DEFAULT NOW()
                );
            """)
        

    # ── end of schema ─────────────────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  KEY BUILDER
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def build_key(item_name: str, pack_type: str) -> Optional[str]:
        name = str(item_name or "").strip().upper()
        pack = str(pack_type or "").strip().upper()
        if not name:
            return None
        return f"{name}||{pack}" if pack else f"{name}||CASE"

    # ── end of key builder ────────────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  CRUD
    # ──────────────────────────────────────────────────────────────────────────

    def add_item(self, item_data: Dict[str, Any],
                 changed_by: str = "system") -> bool:
        now = datetime.utcnow()
        item_data.setdefault("created_date",     now)
        item_data.setdefault("last_updated",     now)
        item_data.setdefault("record_status",    "active")
        item_data.setdefault("yield",            1.0)
        item_data.setdefault("conv_ratio",       1.0)
        item_data.setdefault("quantity_on_hand", 0)
        item_data.setdefault("is_chargeable",    True)
        item_data.setdefault("status_tag",       "Standard")
        if self._cc and not item_data.get("cost_center"):
            item_data["cost_center"] = self._cc

        cols         = list(item_data.keys())
        vals         = list(item_data.values())
        placeholders = ", ".join(["%s"] * len(cols))
        col_str      = ", ".join(cols)
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    f"INSERT INTO items ({col_str}) VALUES ({placeholders})",
                    vals
                )
            self._add_history(item_data["key"], "created", "all",
                              new_value="Item created",
                              change_source="import",
                              changed_by=changed_by)
            return True
        except psycopg2.errors.UniqueViolation:
            return False
        except Exception as e:
            print(f"Error adding item: {e}")
            return False

    def bulk_add_items(self, items: list, changed_by: str = "import",
                       batch_size: int = 500) -> Dict[str, int]:
        """
        Insert many items in one transaction per batch.
        Uses execute_values for a single round-trip per batch of batch_size rows.
        Skips items whose key already exists (ON CONFLICT DO NOTHING).
        Writes a single summary history row per batch instead of one per item.

        Returns {"added": int, "skipped": int, "errors": int}
        """
        from psycopg2.extras import execute_values
        now = datetime.utcnow()

        # Canonical column set — must match what items table accepts
        _COLS = [
            "key", "description", "pack_type", "cost", "per", "conv_ratio",
            "yield", "gl_code", "gl_name", "vendor", "item_number", "gtin",
            "cost_center", "quantity_on_hand", "record_status", "is_chargeable",
            "status_tag", "user_notes", "created_date", "last_updated",
        ]

        def _row(item):
            d = dict(item)
            d.setdefault("created_date",     now)
            d.setdefault("last_updated",     now)
            d.setdefault("record_status",    "active")
            d.setdefault("yield",            1.0)
            d.setdefault("conv_ratio",       1.0)
            d.setdefault("quantity_on_hand", 0.0)
            d.setdefault("is_chargeable",    True)
            d.setdefault("status_tag",       "Standard")
            d.setdefault("user_notes",       "")
            d.setdefault("vendor",           "")
            d.setdefault("item_number",      "")
            d.setdefault("gtin",             "")
            d.setdefault("per",              "Case")
            if self._cc and not d.get("cost_center"):
                d["cost_center"] = self._cc
            return tuple(d.get(c) for c in _COLS)

        col_str = ", ".join(_COLS)
        sql     = (
            f"INSERT INTO items ({col_str}) VALUES %s "
            "ON CONFLICT (key) DO NOTHING"
        )

        added = skipped = errors = 0
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            rows  = []
            for item in batch:
                try:
                    rows.append(_row(item))
                except Exception:
                    errors += 1

            if not rows:
                continue
            try:
                with get_conn() as conn:
                    cur = conn.cursor()
                    execute_values(cur, sql, rows)
                    added += cur.rowcount if cur.rowcount >= 0 else len(rows)
                    skipped += len(rows) - max(cur.rowcount, 0)
                # One summary history entry for the whole batch
                self._add_history(
                    batch[0].get("key", "bulk"),
                    "bulk_import",
                    "all",
                    new_value=f"Bulk import: {len(rows)} items",
                    change_source="import",
                    changed_by=changed_by,
                )
            except Exception as exc:
                errors += len(rows)
                print(f"bulk_add_items batch error: {exc}")

        return {"added": added, "skipped": skipped, "errors": errors}

    def upsert_item(self, item_data: Dict[str, Any],
                    doc_date: str = None,
                    source_document: str = None,
                    changed_by: str = "import") -> str:
        key = item_data.get("key") or self.build_key(
            item_data.get("description", ""),
            item_data.get("pack_type", "")
        )
        if not key:
            return "skipped"
        item_data["key"] = key
        if self.item_exists(key):
            self.update_item_smart(key, item_data,
                                   doc_date=doc_date,
                                   source_document=source_document,
                                   changed_by=changed_by)
            return "updated"
        else:
            self.add_item(item_data, changed_by=changed_by)
            return "created"

    def get_item(self, key: str) -> Optional[Dict]:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM items WHERE key = %s", (key,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_items(self, record_status: str = "active") -> List[Dict]:
        cc_sql, cc_p = self._cc_clause("AND")
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            if record_status:
                cur.execute(
                    f"SELECT * FROM items WHERE record_status = %s{cc_sql} ORDER BY description",
                    [record_status] + cc_p,
                )
            else:
                wh, p = ("WHERE" + cc_sql[4:], cc_p) if cc_sql else ("", [])
                cur.execute(f"SELECT * FROM items {wh} ORDER BY description", p)
            return [dict(r) for r in cur.fetchall()]

    def get_last_updated(self) -> Optional[datetime]:
        cc_sql, cc_p = self._cc_clause("AND")
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT MAX(last_updated) FROM items WHERE record_status = 'active'{cc_sql}",
                cc_p,
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    def get_items_by_cost_center(self, cost_center: str) -> List[Dict]:
        """Explicit cost center override — ignores self._cc."""
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM items WHERE cost_center = %s "
                "AND record_status = 'active' ORDER BY description",
                (cost_center,),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_low_stock_items(self) -> List[Dict]:
        cc_sql, cc_p = self._cc_clause("AND")
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(f"""
                SELECT * FROM items
                WHERE quantity_on_hand < reorder_point
                  AND record_status = 'active'
                  AND reorder_point > 0
                  {cc_sql.lstrip()}
                ORDER BY (reorder_point - quantity_on_hand) DESC
            """, cc_p)
            return [dict(r) for r in cur.fetchall()]

    def get_inventory_value(self) -> float:
        cc_sql, cc_p = self._cc_clause("AND")
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                SELECT SUM(
                    quantity_on_hand *
                    CASE
                        WHEN LOWER(COALESCE(per, 'case')) = 'case'
                         AND COALESCE(conv_ratio, 1) > 1
                        THEN cost / conv_ratio
                        ELSE cost
                    END
                )
                FROM items
                WHERE record_status = 'active'{cc_sql}
            """, cc_p)
            result = cur.fetchone()[0]
            return float(result) if result else 0.0

    def search_items(self, term: str) -> List[Dict]:
        p = f"%{term.upper()}%"
        cc_sql, cc_p = self._cc_clause("AND")
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(f"""
                SELECT * FROM items
                WHERE (
                    UPPER(key) LIKE %s
                   OR UPPER(description) LIKE %s
                   OR UPPER(vendor) LIKE %s
                   OR gl_code LIKE %s
                   OR UPPER(brand) LIKE %s
                ){cc_sql}
                ORDER BY description
            """, [p, p, p, p, p] + cc_p)
            return [dict(r) for r in cur.fetchall()]

    def count_items(self, record_status: str = None) -> int:
        cc_sql, cc_p = self._cc_clause("AND" if record_status else "WHERE")
        with get_conn() as conn:
            cur = conn.cursor()
            if record_status:
                cur.execute(
                    f"SELECT COUNT(*) FROM items WHERE record_status = %s{cc_sql}",
                    [record_status] + cc_p,
                )
            else:
                cur.execute(f"SELECT COUNT(*) FROM items{cc_sql}", cc_p)
            return cur.fetchone()[0]

    def item_exists(self, key: str) -> bool:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM items WHERE key = %s", (key,))
            return cur.fetchone() is not None

    def update_item(self, key: str, updates: Dict[str, Any],
                    changed_by: str = "system",
                    change_reason: str = "") -> bool:
        """Public update wrapper — used by GL manager and other services."""
        updates["last_updated"] = datetime.utcnow()
        return self._apply_update(key, updates,
                                  change_source="manual_edit",
                                  changed_by=changed_by)

    def bulk_update_cost_center(self, cost_center: str,
                                 only_unset: bool = True) -> int:
        """Assign cost_center to all items. Returns count updated."""
        with get_conn() as conn:
            cur = conn.cursor()
            if only_unset:
                cur.execute("""
                    UPDATE items SET cost_center = %s
                    WHERE (cost_center IS NULL OR cost_center = '')
                      AND record_status != 'discontinued'
                """, (cost_center,))
            else:
                cur.execute("""
                    UPDATE items SET cost_center = %s
                    WHERE record_status != 'discontinued'
                """, (cost_center,))
            return cur.rowcount

    def bulk_update_gl(self, keys: list, gl_code: str,
                        gl_name: str, changed_by: str = "user") -> int:
        """Assign the same gl_code + gl_name to a list of item keys (one batch SQL)."""
        if not keys:
            return 0
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE items SET gl_code=%s, gl_name=%s, last_updated=%s "
                    "WHERE key = ANY(%s)",
                    (gl_code, gl_name, datetime.utcnow(), keys),
                )
                count = cur.rowcount
            self._add_history(
                keys[0], "bulk_gl_assignment", "gl_code",
                new_value=f"{gl_code} ({gl_name}) — {len(keys)} items",
                change_source="bulk_gl_assignment",
                changed_by=changed_by,
            )
            return count
        except Exception as exc:
            print(f"bulk_update_gl error: {exc}")
            return 0

    def bulk_update_fields(self, rows: list, changed_by: str = "user") -> int:
        """
        Update arbitrary fields for many items in one batch.

        rows: [{"key": str, "gl_code": str, "gl_name": str, ...}, ...]

        Uses a VALUES table joined to items — one round trip for any mix of values.
        Only handles fields that appear in ALL rows (intersection).  Non-common
        fields are silently ignored.
        """
        if not rows:
            return 0
        from psycopg2.extras import execute_values

        # Determine safe field set (exclude key)
        skip = {"key"}
        field_sets = [set(r.keys()) - skip for r in rows]
        fields = sorted(field_sets[0].intersection(*field_sets[1:])) if len(field_sets) > 1 \
                 else sorted(field_sets[0])
        if not fields:
            return 0

        now = datetime.utcnow()
        all_fields = ["key"] + fields + ["last_updated"]

        def _row(r):
            return tuple([r["key"]] + [r.get(f) for f in fields] + [now])

        # Build the UPDATE ... FROM (VALUES ...) form
        col_assigns = ", ".join(f"{f} = v.{f}" for f in fields)
        col_types   = ", ".join(["text"] + ["text"] * len(fields) + ["timestamp"])
        sql = (
            f"UPDATE items SET {col_assigns}, last_updated = v.last_updated "
            f"FROM (VALUES %s) AS v(key, {', '.join(fields)}, last_updated) "
            f"WHERE items.key = v.key"
        )

        try:
            with get_conn() as conn:
                cur = conn.cursor()
                execute_values(cur, sql, [_row(r) for r in rows])
                count = cur.rowcount
            self._add_history(
                rows[0]["key"], "bulk_field_update", "multiple",
                new_value=f"Fields: {fields} — {len(rows)} items",
                change_source="bulk_update",
                changed_by=changed_by,
            )
            return count
        except Exception as exc:
            print(f"bulk_update_fields error: {exc}")
            return 0

    def delete_item(self, key: str, changed_by: str = "system") -> bool:
        return self._apply_update(key, {"record_status": "discontinued"},
                                  change_source="manual_deletion",
                                  changed_by=changed_by)

    # ──────────────────────────────────────────────────────────────────────────
    #  TRANSFER QoH COMMIT  (F-007)
    # ──────────────────────────────────────────────────────────────────────────

    def apply_transfer_qoh(self, transfer_id: str,
                           changed_by: str = "transfer_approve") -> Dict:
        """
        Apply quantity-on-hand adjustments for an approved transfer.

        For each transfer line:
          • source CC  → quantity_on_hand -= qty
          • dest CC    → quantity_on_hand += qty
            (if item does not exist in dest CC, it is cloned from source with qty = transfer qty)

        Returns {"applied": int, "cloned": int, "warnings": list}
        """
        applied, cloned, warnings = 0, 0, []

        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Get header
            cur.execute("SELECT * FROM transfers WHERE transfer_id = %s", (transfer_id,))
            hdr = cur.fetchone()
            if not hdr:
                return {"applied": 0, "cloned": 0,
                        "warnings": [f"Transfer {transfer_id} not found"]}

            from_cc = hdr["from_cc"]
            to_cc   = hdr["to_cc"]

            # Get lines
            cur.execute("SELECT * FROM transfer_lines WHERE transfer_id = %s",
                        (transfer_id,))
            lines = cur.fetchall()

        for line in lines:
            key = line["item_key"]
            qty = float(line["quantity"] or 0)
            if qty <= 0:
                continue

            # ── Deduct from source ─────────────────────────────────────────
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE items SET quantity_on_hand = quantity_on_hand - %s, "
                    "last_updated = %s "
                    "WHERE key = %s AND cost_center = %s",
                    (qty, datetime.utcnow(), key, from_cc),
                )
                if cur.rowcount == 0:
                    warnings.append(
                        f"Source item not found: {key} @ CC {from_cc}"
                    )

            # ── Add to destination ─────────────────────────────────────────
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE items SET quantity_on_hand = quantity_on_hand + %s, "
                    "last_updated = %s "
                    "WHERE key = %s AND cost_center = %s",
                    (qty, datetime.utcnow(), key, to_cc),
                )
                if cur.rowcount == 0:
                    # Item doesn't exist in dest CC — clone from source
                    with get_conn() as conn2:
                        cur2 = conn2.cursor(
                            cursor_factory=psycopg2.extras.RealDictCursor)
                        cur2.execute(
                            "SELECT * FROM items WHERE key = %s "
                            "AND cost_center = %s LIMIT 1",
                            (key, from_cc),
                        )
                        src = cur2.fetchone()
                    if src:
                        src = dict(src)
                        src.pop("id", None)
                        src["cost_center"]    = to_cc
                        src["quantity_on_hand"] = qty
                        src["created_date"]   = datetime.utcnow()
                        src["last_updated"]   = datetime.utcnow()
                        cols = ", ".join(src.keys())
                        vals = list(src.values())
                        ph   = ", ".join(["%s"] * len(vals))
                        with get_conn() as conn3:
                            cur3 = conn3.cursor()
                            try:
                                cur3.execute(
                                    f"INSERT INTO items ({cols}) VALUES ({ph}) "
                                    "ON CONFLICT (key) DO UPDATE "
                                    "SET quantity_on_hand = EXCLUDED.quantity_on_hand",
                                    vals,
                                )
                                cloned += 1
                            except Exception as exc:
                                warnings.append(f"Clone failed for {key}: {exc}")
                    else:
                        warnings.append(
                            f"Could not clone {key} to CC {to_cc} — no source record"
                        )

            applied += 1
            self._add_history(
                key, "transfer", "quantity_on_hand",
                new_value=f"Transfer {transfer_id}: -{qty} from {from_cc}, +{qty} to {to_cc}",
                change_source="transfer_approve",
                changed_by=changed_by,
            )

        return {"applied": applied, "cloned": cloned, "warnings": warnings}

    # ──────────────────────────────────────────────────────────────────────────
    #  COUNT OVERRIDES  (F-031)
    # ──────────────────────────────────────────────────────────────────────────

    def ensure_count_override_tables(self) -> None:
        """Create count_overrides and count_override_settings tables if absent."""
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS count_overrides (
                    id          SERIAL PRIMARY KEY,
                    item_key    TEXT NOT NULL,
                    multiplier  NUMERIC(10,4) NOT NULL DEFAULT 1.0,
                    reason      TEXT,
                    created_by  TEXT,
                    created_at  TIMESTAMPTZ DEFAULT NOW(),
                    active      BOOLEAN DEFAULT TRUE
                );
                CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_count_overrides_key ON count_overrides(item_key);

                CREATE TABLE IF NOT EXISTS count_override_settings (
                    setting_key TEXT PRIMARY KEY,
                    value       TEXT NOT NULL
                );
                INSERT INTO count_override_settings (setting_key, value)
                VALUES ('enabled', 'true')
                ON CONFLICT (setting_key) DO NOTHING;
            """)

    def get_count_overrides(self, active_only: bool = True) -> List[Dict]:
        """Return all count override rules."""
        try:
            self.ensure_count_override_tables()
            with get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                if active_only:
                    cur.execute(
                        "SELECT * FROM count_overrides WHERE active = TRUE "
                        "ORDER BY item_key"
                    )
                else:
                    cur.execute(
                        "SELECT * FROM count_overrides ORDER BY item_key"
                    )
                return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []

    def get_count_override_lookup(self) -> Dict[str, float]:
        """Return {item_key: multiplier} for all active overrides."""
        return {r["item_key"]: float(r["multiplier"])
                for r in self.get_count_overrides(active_only=True)}

    def upsert_count_override(self, item_key: str, multiplier: float,
                               reason: str = "", created_by: str = "user") -> bool:
        """Add or update an override rule for item_key."""
        try:
            self.ensure_count_override_tables()
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO count_overrides
                        (item_key, multiplier, reason, created_by, active)
                    VALUES (%s, %s, %s, %s, TRUE)
                    ON CONFLICT (item_key) DO UPDATE
                        SET multiplier  = EXCLUDED.multiplier,
                            reason      = EXCLUDED.reason,
                            created_by  = EXCLUDED.created_by,
                            active      = TRUE
                """, (item_key.strip().upper(), multiplier, reason, created_by))
            return True
        except Exception as exc:
            print(f"upsert_count_override error: {exc}")
            return False

    def toggle_count_override(self, item_key: str, active: bool) -> bool:
        """Enable or disable an override rule without deleting it."""
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE count_overrides SET active = %s WHERE item_key = %s",
                    (active, item_key.strip().upper()),
                )
            return True
        except Exception as exc:
            print(f"toggle_count_override error: {exc}")
            return False

    def delete_count_override(self, item_key: str) -> bool:
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM count_overrides WHERE item_key = %s",
                    (item_key.strip().upper(),),
                )
            return True
        except Exception:
            return False

    def get_override_settings_enabled(self) -> bool:
        """Returns True if count overrides are globally enabled."""
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT value FROM count_override_settings "
                    "WHERE setting_key = 'enabled'"
                )
                row = cur.fetchone()
                return row and row[0].lower() == "true"
        except Exception:
            return True

    def set_override_settings_enabled(self, enabled: bool) -> None:
        try:
            self.ensure_count_override_tables()
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO count_override_settings (setting_key, value) "
                    "VALUES ('enabled', %s) "
                    "ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value",
                    ("true" if enabled else "false",),
                )
        except Exception:
            pass

    # ── end of CRUD ───────────────────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  SMART UPDATE + OVERRIDES
    # ──────────────────────────────────────────────────────────────────────────

    def update_item_smart(self, key: str, incoming: Dict[str, Any],
                          doc_date: str = None,
                          source_document: str = None,
                          changed_by: str = "import") -> bool:
        current = self.get_item(key)
        if not current:
            return False
        updates: Dict[str, Any] = {}
        now = datetime.utcnow()

        if incoming.get("cost"):
            updates["cost"]       = incoming["cost"]
            updates["status_tag"] = "✅ Updated Today"
        if "quantity_on_hand" in incoming:
            updates["quantity_on_hand"] = incoming["quantity_on_hand"]
        if not current["override_yield"] and "yield" in incoming:
            updates["yield"] = incoming["yield"]
        if not current["override_conv_ratio"] and "conv_ratio" in incoming:
            updates["conv_ratio"] = incoming["conv_ratio"]
        if not current["override_pack_type"] and "pack_type" in incoming:
            updates["pack_type"] = incoming["pack_type"]
        if not current["override_vendor"] and "vendor" in incoming:
            updates["vendor"] = incoming["vendor"]
        if not current["override_gl"] and "gl_code" in incoming:
            updates["gl_code"] = incoming["gl_code"]
            updates["gl_name"] = incoming.get("gl_name", current["gl_name"])
        for f in ("per", "unit", "item_number", "mog", "brand", "gtin",
                  "is_chargeable", "cost_center"):
            if incoming.get(f) is not None:
                updates[f] = incoming[f]
        updates["last_updated"] = now

        if "cost" in updates and doc_date:
            self._add_price_history(key, updates["cost"], doc_date,
                                    source_document, incoming.get("vendor"))
        return self._apply_update(key, updates, change_source="import",
                                  source_document=source_document,
                                  changed_by=changed_by)

    def set_override(self, key: str, field: str, value: Any,
                     changed_by: str = "user") -> bool:
        override_map = {
            "pack_type":  "override_pack_type",
            "yield":      "override_yield",
            "conv_ratio": "override_conv_ratio",
            "vendor":     "override_vendor",
            "gl":         "override_gl",
        }
        if field not in override_map:
            return False
        return self._apply_update(key,
                                  {override_map[field]: value, field: value},
                                  change_source="manual_override",
                                  changed_by=changed_by)

    def clear_override(self, key: str, field: str,
                       changed_by: str = "user") -> bool:
        override_map = {
            "pack_type":  "override_pack_type",
            "yield":      "override_yield",
            "conv_ratio": "override_conv_ratio",
            "vendor":     "override_vendor",
            "gl":         "override_gl",
        }
        if field not in override_map:
            return False
        return self._apply_update(key, {override_map[field]: None},
                                  change_source="clear_override",
                                  changed_by=changed_by)

    # ── end of smart update ───────────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  HISTORY
    # ──────────────────────────────────────────────────────────────────────────

    def get_item_history(self, key: str, limit: int = 100) -> List[Dict]:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT * FROM item_history WHERE item_key = %s
                ORDER BY change_date DESC LIMIT %s
            """, (key, limit))
            return [dict(r) for r in cur.fetchall()]

    def get_price_history(self, key: str, limit: int = 50) -> List[Dict]:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT * FROM price_history WHERE item_key = %s
                ORDER BY doc_date DESC LIMIT %s
            """, (key, limit))
            return [dict(r) for r in cur.fetchall()]

    # ── end of history ────────────────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  IMPORT JOB TRACKER
    # ──────────────────────────────────────────────────────────────────────────

    def create_job(self, job_type: str = "invoice_import",
                   source_file: str = None,
                   total_rows: int = 0,
                   triggered_by: str = "user") -> str:
        """
        Create a new import_jobs record.
        Returns the job_id (UUID string).
        """
        job_id = str(uuid.uuid4())
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO import_jobs
                    (job_id, job_type, status, source_file,
                     total_rows, triggered_by, started_at)
                VALUES (%s, %s, 'running', %s, %s, %s, NOW())
            """, (job_id, job_type, source_file, total_rows, triggered_by))
        return job_id

    def update_job(self, job_id: str, **kwargs) -> None:
        """
        Update any combination of job fields.
        Accepted kwargs: status, processed, added, updated, skipped,
                         error_count, errors, finished_at, notes
        """
        allowed = {"status", "processed", "added", "updated", "skipped",
                   "error_count", "errors", "finished_at", "notes"}
        fields  = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        # Serialize errors list to JSON if provided
        if "errors" in fields and isinstance(fields["errors"], list):
            fields["errors"] = json.dumps(fields["errors"])
        set_clause = ", ".join(f"{k} = %s" for k in fields)
        vals       = list(fields.values()) + [job_id]
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE import_jobs SET {set_clause} WHERE job_id = %s",
                vals
            )

    def get_job(self, job_id: str) -> Optional[Dict]:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM import_jobs WHERE job_id = %s", (job_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_recent_jobs(self, limit: int = 20) -> List[Dict]:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT * FROM import_jobs
                ORDER BY started_at DESC
                LIMIT %s
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    def get_active_jobs(self) -> List[Dict]:
        """Return all jobs with status = 'running'."""
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT * FROM import_jobs
                WHERE status = 'running'
                ORDER BY started_at DESC
            """)
            return [dict(r) for r in cur.fetchall()]

    def fail_job(self, job_id: str, error: str) -> None:
        """Mark a job as failed with an error message."""
        self.update_job(
            job_id,
            status="failed",
            finished_at=datetime.utcnow(),
            notes=error,
        )

    # ── end of import job tracker ─────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  COUNT SESSION METHODS
    # ──────────────────────────────────────────────────────────────────────────

    def create_count_session(self, count_date, created_by: str = "user",
                              notes: str = "") -> str:
        session_id = str(uuid.uuid4())
        cc = self._cc or "all"
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO count_sessions
                    (session_id, cost_center, count_date, status, created_by, notes)
                VALUES (%s, %s, %s, 'open', %s, %s)
            """, (session_id, cc, count_date, created_by, notes))
        return session_id

    def save_count_lines(self, session_id: str, lines: List[Dict]) -> None:
        """Replace all lines for a session (upsert by session_id)."""
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM count_lines WHERE session_id = %s", (session_id,))
            for l in lines:
                cur.execute("""
                    INSERT INTO count_lines
                        (session_id, item_key, description, pack_type,
                         gl_code, gl_name, unit_cost, quantity_counted,
                         extended_value, notes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (session_id, l["item_key"], l.get("description"),
                      l.get("pack_type"), l.get("gl_code"), l.get("gl_name"),
                      l.get("unit_cost", 0), l.get("quantity_counted", 0),
                      l.get("extended_value", 0), l.get("notes", "")))
            total = sum(float(l.get("extended_value", 0)) for l in lines)
            cur.execute("""
                UPDATE count_sessions
                SET item_count = %s, total_value = %s
                WHERE session_id = %s
            """, (len(lines), total, session_id))

    def commit_count_session(self, session_id: str,
                              committed_by: str = "user") -> Dict:
        """Write counted quantities to items.quantity_on_hand, mark session committed."""
        lines = self.get_count_lines(session_id)
        updated, errors = 0, []
        for l in lines:
            try:
                self._apply_update(
                    l["item_key"],
                    {"quantity_on_hand": float(l["quantity_counted"]),
                     "last_updated": datetime.utcnow()},
                    change_source="count_entry",
                    changed_by=committed_by,
                )
                updated += 1
            except Exception as exc:
                errors.append(f"{l['item_key']}: {exc}")
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE count_sessions
                SET status = 'committed', committed_at = NOW(), committed_by = %s
                WHERE session_id = %s
            """, (committed_by, session_id))
        return {"updated": updated, "errors": errors}

    def get_count_session(self, session_id: str) -> Optional[Dict]:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM count_sessions WHERE session_id = %s",
                        (session_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_count_lines(self, session_id: str) -> List[Dict]:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT * FROM count_lines WHERE session_id = %s
                ORDER BY gl_code, description
            """, (session_id,))
            return [dict(r) for r in cur.fetchall()]

    def get_recent_count_sessions(self, limit: int = 20) -> List[Dict]:
        cc_sql, cc_p = self._cc_clause("AND")
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(f"""
                SELECT * FROM count_sessions
                WHERE 1=1{cc_sql}
                ORDER BY created_at DESC LIMIT %s
            """, cc_p + [limit])
            return [dict(r) for r in cur.fetchall()]

    # ── end of count session methods ──────────────────────────────────────────


    # ──────────────────────────────────────────────────────────────────────────
    #  INTERNALS
    # ──────────────────────────────────────────────────────────────────────────

    def _apply_update(self, key: str, updates: Dict[str, Any],
                      change_source: str = "system",
                      source_document: str = None,
                      changed_by: str = "system") -> bool:
        if not updates:
            return True
        current = self.get_item(key)
        if not current:
            return False
        try:
            set_clause = ", ".join([f"{k} = %s" for k in updates])
            vals       = list(updates.values()) + [key]
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    f"UPDATE items SET {set_clause} WHERE key = %s", vals
                )
            for field, new_val in updates.items():
                if field == "last_updated":
                    continue
                old_val = current.get(field)
                if str(old_val) != str(new_val):
                    self._add_history(key, "field_update",
                                      field_changed=field,
                                      old_value=str(old_val) if old_val is not None else "",
                                      new_value=str(new_val) if new_val is not None else "",
                                      change_source=change_source,
                                      source_document=source_document,
                                      changed_by=changed_by)
            return True
        except Exception as e:
            print(f"Error updating {key}: {e}")
            return False

    def _add_history(self, item_key: str, change_type: str,
                     field_changed: str = None, old_value: str = None,
                     new_value: str = None, change_source: str = None,
                     source_document: str = None, changed_by: str = "system",
                     change_reason: str = None, metadata: Dict = None):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO item_history
                (item_key, change_type, field_changed, old_value, new_value,
                 change_source, source_document, changed_by, change_reason, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (item_key, change_type, field_changed, old_value, new_value,
                  change_source, source_document, changed_by, change_reason,
                  json.dumps(metadata) if metadata else None))

    def _add_price_history(self, key: str, price: float, doc_date: str,
                           source_file: str = None, vendor: str = None):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO price_history (item_key, price, doc_date, source_file, vendor)
                VALUES (%s, %s, %s, %s, %s)
            """, (key, price, doc_date, source_file, vendor))
    # ──────────────────────────────────────────────────────────────────────────
    #  USER MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────────

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_users(self) -> List[Dict]:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM users ORDER BY created_at")
            return [dict(r) for r in cur.fetchall()]

    def upsert_user(self, user_data: Dict[str, Any]) -> bool:
        username = user_data.get("username")
        if not username:
            return False
        fields = {k: v for k, v in user_data.items() if k != "username"}
        if not fields:
            return False
        set_clause = ", ".join(f"{k} = EXCLUDED.{k}" for k in fields)
        cols   = ", ".join(["username"] + list(fields.keys()))
        params = ", ".join(["%s"] * (1 + len(fields)))
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                INSERT INTO users ({cols})
                VALUES ({params})
                ON CONFLICT (username) DO UPDATE SET {set_clause}
            """, [username] + list(fields.values()))
        return True

    def update_last_login(self, username: str) -> None:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET last_login = NOW() WHERE username = %s",
                (username,)
            )

    # ── end of user management ────────────────────────────────────────────────
    # ── end of internals ──────────────────────────────────────────────────────

# ── end of InventoryDatabase ──────────────────────────────────────────────────
