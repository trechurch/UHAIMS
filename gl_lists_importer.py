"""
gl_lists_importer.py  —  GL Lists folder reader and importer service
v1.0.0

Reads CSV files from the "GL Lists" folder where:
  - Filename pattern: "<GL Name> <6-digit code>.csv"
  - Columns: Item Description, GTIN, Pack Type, Price, UOM, Category

Provides two operations:
  1. assign_gl_codes()  — match existing DB items by description → write GL code
  2. import_master()    — upsert ALL items from GL files into DB with GL pre-assigned
"""

import os
import re
import io
import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Path is relative to this file (repo root)
GL_LISTS_DIR = Path(__file__).parent / "GL Lists"


# ──────────────────────────────────────────────────────────────────────────────
#  FILENAME PARSER
# ──────────────────────────────────────────────────────────────────────────────

def parse_gl_filename(filename: str) -> Tuple[str, str]:
    """
    Extract (gl_name, gl_code) from a filename like:
      "Meat & Poultry 411037.csv"  →  ("Meat & Poultry", "411037")
      "Grocery Storeroom 411039.csv" → ("Grocery Storeroom", "411039")
    """
    stem = Path(filename).stem
    m = re.search(r'^(.*?)\s+(\d{6})\s*$', stem)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return stem, "000000"


# ──────────────────────────────────────────────────────────────────────────────
#  PRICE PARSER
# ──────────────────────────────────────────────────────────────────────────────

def _parse_price(price_str: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Returns (case_cost, unit_cost).
    "$34.47/$1.44"  →  (34.47, 1.44)
    "$47.91"        →  (47.91, None)
    "**" / ""       →  (None, None)
    """
    if not price_str:
        return None, None
    price_str = price_str.strip().replace(",", "")

    # Remove currency symbols
    nums = re.findall(r'\d+\.?\d*', price_str)
    if not nums:
        return None, None
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    return float(nums[0]), None


# ──────────────────────────────────────────────────────────────────────────────
#  CSV ROW NORMALISER
# ──────────────────────────────────────────────────────────────────────────────

def _normalize_uom(uom: str) -> str:
    """Map UOM strings to standard 'per' values."""
    if not uom:
        return "Case"
    u = uom.strip().lower()
    if u in ("cs", "case", "ca"):
        return "Case"
    if u in ("ea", "each", "1"):
        return "Each"
    if u in ("keg",):
        return "Keg"
    if u in ("lb", "lbs"):
        return "Lb"
    return uom.strip().title()


def _make_key(description: str) -> str:
    """Generate a stable key from description (uppercase, alphanumeric + spaces)."""
    clean = re.sub(r'[^A-Z0-9 ]', '', description.upper().strip())
    return clean[:64]


def parse_gl_csv(filepath: Path, gl_code: str, gl_name: str) -> List[Dict]:
    """
    Parse a single GL list CSV.  Returns a list of normalized item dicts.
    Skips rows with no description or clearly invalid data.
    """
    items = []
    try:
        raw = filepath.read_bytes()
        # Strip BOM if present
        encoding = "utf-8-sig"
        text = raw.decode(encoding, errors="replace")
        reader = csv.DictReader(io.StringIO(text))

        for row in reader:
            desc = (row.get("Item Description") or "").strip()
            if not desc or desc.upper() == "ITEM DESCRIPTION":
                continue

            gtin      = str(row.get("GTIN") or "").strip()
            pack_type = (row.get("Pack Type") or "").strip()
            price_raw = (row.get("Price") or "").strip()
            uom       = (row.get("UOM") or "").strip()
            category  = (row.get("Category") or "").strip()

            case_cost, unit_cost = _parse_price(price_raw)

            # conv_ratio: if we know case cost and unit cost, ratio = case/unit
            conv_ratio = 1.0
            if case_cost and unit_cost and unit_cost > 0:
                conv_ratio = round(case_cost / unit_cost, 4)

            key = _make_key(desc)

            items.append({
                "key":              key,
                "description":      desc.upper(),
                "gtin":             gtin if gtin and gtin != "0" else "",
                "pack_type":        pack_type,
                "cost":             case_cost or 0.0,
                "per":              _normalize_uom(uom),
                "conv_ratio":       conv_ratio,
                "gl_code":          gl_code,
                "gl_name":          gl_name,
                "status_tag":       category or "Standard",
                "quantity_on_hand": 0.0,
                "record_status":    "active",
                "is_chargeable":    True,
                "_source_file":     filepath.name,
            })
    except Exception as exc:
        logger.error("Error parsing %s: %s", filepath, exc)

    return items


# ──────────────────────────────────────────────────────────────────────────────
#  FOLDER SCANNER
# ──────────────────────────────────────────────────────────────────────────────

def scan_gl_lists_folder(folder: Path = GL_LISTS_DIR) -> List[Dict]:
    """
    Returns a list of category dicts:
    {
      "filename": str,
      "gl_code":  str,
      "gl_name":  str,
      "items":    List[Dict],   # normalized item rows
    }
    """
    if not folder.exists():
        return []

    categories = []
    for f in sorted(folder.glob("*.csv")):
        gl_name, gl_code = parse_gl_filename(f.name)
        if gl_code == "000000":
            continue   # skip the "Unassigned" placeholder file
        items = parse_gl_csv(f, gl_code, gl_name)
        if items:
            categories.append({
                "filename": f.name,
                "gl_code":  gl_code,
                "gl_name":  gl_name,
                "items":    items,
            })

    return categories


# ──────────────────────────────────────────────────────────────────────────────
#  OPERATION 1: Assign GL codes to existing items (fuzzy description match)
# ──────────────────────────────────────────────────────────────────────────────

def assign_gl_codes(db, categories: List[Dict],
                    min_score: int = 75,
                    changed_by: str = "gl_lists_import",
                    only_unassigned: bool = True) -> Dict:
    """
    For each existing DB item, find the best fuzzy description match across
    all GL list items, then write the GL code if score >= min_score.

    Returns {"assigned": int, "skipped": int, "no_match": int, "matches": list}
    """
    from rapidfuzz import process, fuzz

    # Build a flat lookup: UPPER description → (gl_code, gl_name)
    gl_map: Dict[str, Tuple[str, str]] = {}
    for cat in categories:
        for item in cat["items"]:
            gl_map[item["description"].upper()] = (cat["gl_code"], cat["gl_name"])

    descriptions   = list(gl_map.keys())
    db_items       = db.get_all_items("active")
    assigned, skipped, no_match = 0, 0, 0
    matches = []

    for db_item in db_items:
        if only_unassigned and db_item.get("gl_code"):
            skipped += 1
            continue

        query = (db_item.get("description") or "").upper().strip()
        if not query:
            no_match += 1
            continue

        result = process.extractOne(query, descriptions,
                                    scorer=fuzz.WRatio,
                                    score_cutoff=min_score)
        if result is None:
            no_match += 1
            continue

        best_desc, score, _ = result
        gl_code, gl_name    = gl_map[best_desc]

        db.update_item(
            db_item["key"],
            {"gl_code": gl_code, "gl_name": gl_name},
            changed_by=changed_by,
        )
        assigned += 1
        matches.append({
            "item":       db_item.get("description", ""),
            "matched_to": best_desc,
            "score":      score,
            "gl_code":    gl_code,
            "gl_name":    gl_name,
        })

    return {
        "assigned":  assigned,
        "skipped":   skipped,
        "no_match":  no_match,
        "matches":   matches,
    }


# ──────────────────────────────────────────────────────────────────────────────
#  OPERATION 2: Import all GL list items as master inventory
# ──────────────────────────────────────────────────────────────────────────────

def import_as_master(db, categories: List[Dict],
                     cost_center: str = "",
                     changed_by: str = "gl_lists_import",
                     skip_existing: bool = True) -> Dict:
    """
    Upsert every item from every GL list CSV into the database.
    Items that already exist (by key) are skipped or updated depending on
    skip_existing.

    Returns {"added": int, "updated": int, "skipped": int, "errors": list}
    """
    # Pre-load existing keys for fast lookup
    existing = {i["key"] for i in db.get_all_items()}
    added, updated, skipped, errors = 0, 0, 0, []

    for cat in categories:
        for item in cat["items"]:
            if cost_center:
                item["cost_center"] = cost_center
            try:
                if item["key"] in existing:
                    if skip_existing:
                        skipped += 1
                        continue
                    db.update_item(
                        item["key"],
                        {"gl_code":   item["gl_code"],
                         "gl_name":   item["gl_name"],
                         "pack_type": item["pack_type"],
                         "cost":      item["cost"],
                         "gtin":      item.get("gtin", "")},
                        changed_by=changed_by,
                    )
                    updated += 1
                else:
                    db.add_item(item, changed_by=changed_by)
                    existing.add(item["key"])
                    added += 1
            except Exception as exc:
                errors.append(f"{item.get('description','?')}: {exc}")

    return {"added": added, "updated": updated,
            "skipped": skipped, "errors": errors}
