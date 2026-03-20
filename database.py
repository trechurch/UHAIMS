"""
UHA IMS — Inventory Database Service
PostgreSQL / Supabase backend

v2.1.0  —  import_jobs table added to create_tables().
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
        "version":     "2.1.1",
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

    def __init__(self, db_url: str = None):
        if db_url:
            os.environ["SUPABASE_DB_URL"] = db_url
        self.create_tables()

    # ── end of init ───────────────────────────────────────────────────────────


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

                CREATE INDEX IF NOT EXISTS idx_items_description  ON items(description);
                CREATE INDEX IF NOT EXISTS idx_items_gl_code      ON items(gl_code);
                CREATE INDEX IF NOT EXISTS idx_items_vendor       ON items(vendor);
                CREATE INDEX IF NOT EXISTS idx_history_item_key   ON item_history(item_key);
                CREATE INDEX IF NOT EXISTS idx_import_jobs_status ON import_jobs(status);
                CREATE INDEX IF NOT EXISTS idx_import_jobs_started ON import_jobs(started_at DESC);
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
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            if record_status:
                cur.execute(
                    "SELECT * FROM items WHERE record_status = %s ORDER BY description",
                    (record_status,)
                )
            else:
                cur.execute("SELECT * FROM items ORDER BY description")
            return [dict(r) for r in cur.fetchall()]

    def get_items_by_cost_center(self, cost_center: str) -> List[Dict]:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM items WHERE cost_center = %s "
                "AND record_status = 'active' ORDER BY description",
                (cost_center,)
            )
            return [dict(r) for r in cur.fetchall()]

    def get_low_stock_items(self) -> List[Dict]:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT * FROM items
                WHERE quantity_on_hand < reorder_point
                  AND record_status = 'active'
                  AND reorder_point > 0
                ORDER BY (reorder_point - quantity_on_hand) DESC
            """)
            return [dict(r) for r in cur.fetchall()]

    def get_inventory_value(self) -> float:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT SUM(
                    quantity_on_hand *
                    CASE
                        WHEN per = 'Case' AND COALESCE(conv_ratio, 1) > 1
                        THEN cost / conv_ratio
                        ELSE cost
                    END
                )
                FROM items
                WHERE record_status = 'active'
            """)
            result = cur.fetchone()[0]
            return float(result) if result else 0.0

    def search_items(self, term: str) -> List[Dict]:
        p = f"%{term.upper()}%"
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT * FROM items
                WHERE UPPER(key) LIKE %s
                   OR UPPER(description) LIKE %s
                   OR UPPER(vendor) LIKE %s
                   OR gl_code LIKE %s
                   OR UPPER(brand) LIKE %s
                ORDER BY description
            """, (p, p, p, p, p))
            return [dict(r) for r in cur.fetchall()]

    def count_items(self, record_status: str = None) -> int:
        with get_conn() as conn:
            cur = conn.cursor()
            if record_status:
                cur.execute(
                    "SELECT COUNT(*) FROM items WHERE record_status = %s",
                    (record_status,)
                )
            else:
                cur.execute("SELECT COUNT(*) FROM items")
            return cur.fetchone()[0]

    def item_exists(self, key: str) -> bool:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM items WHERE key = %s", (key,))
            return cur.fetchone() is not None

    def delete_item(self, key: str, changed_by: str = "system") -> bool:
        return self._apply_update(key, {"record_status": "discontinued"},
                                  change_source="manual_deletion",
                                  changed_by=changed_by)

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

    # ── end of internals ──────────────────────────────────────────────────────

# ── end of InventoryDatabase ──────────────────────────────────────────────────
