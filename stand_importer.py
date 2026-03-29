"""
stand_importer.py  —  Import stand/sub-location definitions from Excel stand sheets.

Supported files:
  NewestStandSheets -TDECU.xlsx   → cost_center 57231 (TDECU Concessions)
  FertittaStandsheets2.xlsx       → cost_center 57232 (Warehouse / Fertitta)

Each worksheet tab = one physical stand.
Columns (TDECU format):
  A: Stand name label   B: Description   C: Sort order
  D: Opening count      E: Closing count  F: $unit/$case
  G: Extended value     H: Pack type      J: C/C or I/I

Usage:
  from stand_importer import import_stand_sheets
  results = import_stand_sheets(db, filepath, cost_center="57231")
"""

__version__ = "1.0.0"

import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional


# ── Tabs to skip (not real stands) ────────────────────────────────────────────
SKIP_TABS = {
    "date and team sheet", "inventory breakdown", "order sheet (all)",
    "master", "summary", "cover",
}


def _slugify(name: str) -> str:
    """Convert stand name to a stable ID slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _stand_id(cost_center: str, tab_name: str, venue_code: str = "") -> str:
    """
    Build stand ID in canonical format: {slug}_{venue_code}_{cost_center}
    e.g. '103_FB_57231', '119_bar_FB_57231'
    """
    slug = _slugify(tab_name)
    if venue_code:
        return f"{slug}_{venue_code}_{cost_center}"
    return f"{slug}_{cost_center}"   # fallback if venue unknown


def _parse_cost_col(val) -> Tuple[Optional[float], Optional[float]]:
    """
    Parse '$X.XX/$Y.YY' → (case_cost, unit_cost).
    Returns (None, None) on failure.
    """
    if not val:
        return None, None
    s = str(val).replace(",", "").replace(" ", "")
    parts = s.split("/")
    try:
        case_cost = float(parts[0].replace("$", "")) if len(parts) > 0 else None
        unit_cost = float(parts[1].replace("$", "")) if len(parts) > 1 else case_cost
        return case_cost, unit_cost
    except (ValueError, IndexError):
        return None, None


def _find_data_start(ws) -> int:
    """Find the first row that looks like actual data (has a value in col B)."""
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row[1] and str(row[1]).strip():
            return i
    return 5  # fallback


def parse_stand_sheet(ws, tab_name: str, cost_center: str,
                      venue_code: str = "") -> Dict:
    """
    Parse one worksheet into a stand dict:
    {
        stand_id, stand_name, cost_center, venue_code,
        items: [{description, sort_order, pack_type, unit_cost, par_qty}]
    }
    """
    stand_id   = _stand_id(cost_center, tab_name, venue_code)
    data_start = _find_data_start(ws)
    items      = []

    for row in ws.iter_rows(min_row=data_start, values_only=True):
        desc = row[1] if len(row) > 1 else None
        if not desc or not str(desc).strip():
            continue

        desc_clean = str(desc).strip()

        # Sort order from col C
        try:
            sort_order = int(float(str(row[2]).replace(",", ""))) if len(row) > 2 and row[2] else 0
        except (ValueError, TypeError):
            sort_order = 0

        # Pack type from col H
        pack_type = str(row[7]).strip() if len(row) > 7 and row[7] else ""

        # Unit cost from col F ($case/$unit)
        _, unit_cost = _parse_cost_col(row[5] if len(row) > 5 else None)

        # Par qty: use closing count col E, col qty part (before the unit label)
        par_qty = 0.0
        try:
            close_raw = str(row[4]).strip() if len(row) > 4 and row[4] else ""
            # Format: "X.XX case_qty/Y.YY EA" → take first number
            num_match = re.match(r"([\d,]+\.?\d*)", close_raw)
            if num_match:
                par_qty = float(num_match.group(1).replace(",", ""))
        except (ValueError, TypeError):
            par_qty = 0.0

        items.append({
            "description": desc_clean,
            "sort_order":  sort_order,
            "pack_type":   pack_type,
            "unit_cost":   unit_cost,
            "par_qty":     par_qty,
        })

    return {
        "stand_id":    stand_id,
        "stand_name":  tab_name,
        "cost_center": cost_center,
        "venue_code":  venue_code,
        "items":       items,
    }


def fuzzy_match_items(stand_items: List[Dict], db_items: List[Dict],
                      min_score: int = 72) -> List[Dict]:
    """
    Fuzzy-match stand item descriptions to DB item keys.
    Returns stand_items with item_key added where matched.
    """
    try:
        from rapidfuzz import process, fuzz
        have_rapidfuzz = True
    except ImportError:
        have_rapidfuzz = False

    # Build lookup: normalized description → key
    desc_map = {}
    for item in db_items:
        desc = (item.get("description") or "").upper().strip()
        if desc:
            desc_map[desc] = item["key"]

    db_descriptions = list(desc_map.keys())
    matched = []

    for si in stand_items:
        raw = si["description"].upper().strip()

        # Exact match first
        if raw in desc_map:
            matched.append({**si, "item_key": desc_map[raw], "match_score": 100})
            continue

        # Fuzzy
        item_key = None
        score    = 0
        if have_rapidfuzz and db_descriptions:
            result = process.extractOne(
                raw, db_descriptions,
                scorer=fuzz.WRatio,
                score_cutoff=min_score,
            )
            if result:
                item_key = desc_map[result[0]]
                score    = result[1]

        matched.append({**si, "item_key": item_key, "match_score": score})

    return matched


def import_stand_sheets(
    db,
    filepath: str,
    cost_center: str,
    venue_code: str = "",
    min_score: int = 72,
    dry_run: bool = False,
) -> Dict:
    """
    Parse an Excel stand sheet file and import stands + stand_items into DB.

    Returns:
    {
        stands_created: int,
        items_linked:   int,
        items_unmatched: int,
        unmatched: [(stand_name, description), ...],
        errors: [str],
    }
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        return {"error": "openpyxl required — pip install openpyxl"}

    errors          = []
    stands_created  = 0
    items_linked    = 0
    unmatched_list  = []

    try:
        wb = load_workbook(filepath, read_only=True, data_only=True, keep_vba=False)
    except Exception as e:
        return {"error": str(e)}

    # Load all DB items once for matching
    try:
        db_items = db.get_all_items("active") or []
        if not db_items:
            # Try without cost center filter
            from database import InventoryDatabase
            import os
            tmp_db = InventoryDatabase(db_url=os.environ.get("SUPABASE_DB_URL"))
            db_items = tmp_db.get_all_items("active") or []
    except Exception as e:
        errors.append(f"Could not load DB items: {e}")
        db_items = []

    for tab_name in wb.sheetnames:
        if tab_name.lower().strip() in SKIP_TABS:
            continue

        try:
            ws    = wb[tab_name]
            stand = parse_stand_sheet(ws, tab_name, cost_center, venue_code)

            if not stand["items"]:
                continue

            # Fuzzy-match descriptions → item keys
            matched_items = fuzzy_match_items(stand["items"], db_items, min_score)

            linked    = [m for m in matched_items if m.get("item_key")]
            unmatched = [m for m in matched_items if not m.get("item_key")]

            for u in unmatched:
                unmatched_list.append((tab_name, u["description"]))

            if not dry_run:
                db.upsert_stand(
                    stand["stand_id"],
                    stand["stand_name"],
                    cost_center=cost_center,
                    venue_code=venue_code,
                )
                db.upsert_stand_items(stand["stand_id"], [
                    {
                        "item_key":  m["item_key"],
                        "sort_order": m["sort_order"],
                        "par_qty":   m["par_qty"],
                    }
                    for m in linked
                ])

            stands_created += 1
            items_linked   += len(linked)

        except Exception as e:
            errors.append(f"{tab_name}: {e}")

    wb.close()

    return {
        "stands_created":  stands_created,
        "items_linked":    items_linked,
        "items_unmatched": len(unmatched_list),
        "unmatched":       unmatched_list[:50],  # cap for display
        "errors":          errors,
    }
