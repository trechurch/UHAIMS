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
#  OPERATION 1: Assign GL codes — multi-phase matching engine
# ──────────────────────────────────────────────────────────────────────────────

def assign_gl_codes(db, categories: List[Dict],
                    min_score: int = 75,
                    changed_by: str = "gl_lists_import",
                    only_unassigned: bool = True) -> Dict:
    """
    Run the multi-phase matching engine against all existing DB items.

    Phase 1 (Exact) and Phase 2 (Fuzzy, WRatio ≥ min_score) are auto-committed.
    Phase 3 (Probabilistic) and Unmatched items are returned in "pending_review"
    for the Match Review Dashboard.

    Returns a session dict compatible with match_engine.run_multiphase_match():
      {
        "exact":          [...],
        "fuzzy":          [...],
        "probabilistic":  [...],   ← awaiting manual review
        "unmatched":      [...],   ← awaiting manual review
        "stats":          {...},
        "assigned":       int,     # items auto-committed this run
        "skipped":        int,     # items already had a GL code
        "matches":        [...],   # legacy compat — auto-committed matches
      }
    """
    from match_engine import run_multiphase_match, FUZZY_THRESHOLD

    # Items already assigned are counted as skipped (not fed to engine)
    db_items = db.get_all_items("active")
    skipped  = sum(1 for i in db_items if only_unassigned and i.get("gl_code"))

    session = run_multiphase_match(db_items, categories,
                                   only_unassigned=only_unassigned)

    # Auto-commit exact + fuzzy matches
    assigned = 0
    matches  = []
    for mr in session["exact"] + session["fuzzy"]:
        best = mr["candidates"][0] if mr["candidates"] else None
        if not best:
            continue
        # For fuzzy pass, enforce min_score on WRatio
        if mr["phase"] == "fuzzy" and best["wratio"] < min_score:
            session["probabilistic"].append(
                {**mr, "phase": "probabilistic"}
            )
            continue
        try:
            db.update_item(
                mr["db_item"]["key"],
                {"gl_code": best["gl_code"], "gl_name": best["gl_name"]},
                changed_by=changed_by,
            )
            assigned += 1
            matches.append({
                "item":       mr["db_item"].get("description", ""),
                "matched_to": best["description"],
                "score":      best["wratio"],
                "gl_code":    best["gl_code"],
                "gl_name":    best["gl_name"],
                "phase":      mr["phase"],
            })
        except Exception as exc:
            logger.error("update_item failed for %s: %s",
                         mr["db_item"].get("key"), exc)

    session["assigned"] = assigned
    session["skipped"]  = skipped
    session["matches"]  = matches

    # Update stats to reflect actual commit count
    session["stats"]["auto_assigned"] = assigned

    return session


# ──────────────────────────────────────────────────────────────────────────────
#  OPERATION 2: Import all GL list items as master inventory
# ──────────────────────────────────────────────────────────────────────────────

def import_as_master(db, categories: List[Dict],
                     cost_center: str = "",
                     changed_by: str = "gl_lists_import",
                     skip_existing: bool = True,
                     progress_task_id: str = "gl_import") -> Dict:
    """
    Upsert every item from every GL list CSV into the database.
    Items that already exist (by key) are skipped or updated depending on
    skip_existing.

    Writes live progress to /tmp/uha_progress/{progress_task_id}.json so the
    Streamlit UI can poll it with render_bg_progress(progress_task_id).

    Returns {"added": int, "updated": int, "skipped": int, "errors": list}
    """
    try:
        from progress_tracker import ProgressTracker
        total_items = sum(len(c["items"]) for c in categories)
        tracker = ProgressTracker(
            progress_task_id, total=total_items,
            label="GL Master List Import",
            write_every=50,          # write to disk every 50 items
        )
    except Exception:
        tracker = None

    # Pre-load existing keys for fast lookup
    existing = {i["key"] for i in db.get_all_items()}
    added, updated, skipped, errors = 0, 0, 0, []
    processed = 0

    for cat in categories:
        cat_label = cat.get("gl_name", "")
        for item in cat["items"]:
            processed += 1
            if cost_center:
                item["cost_center"] = cost_center
            try:
                if item["key"] in existing:
                    if skip_existing:
                        skipped += 1
                    else:
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
                    db_item = {k: v for k, v in item.items() if not k.startswith("_")}
                    db.add_item(db_item, changed_by=changed_by)
                    existing.add(item["key"])
                    added += 1
            except Exception as exc:
                errors.append(f"{item.get('description','?')}: {exc}")

            if tracker:
                tracker.update(
                    processed,
                    f"{cat_label} — added {added:,} · skipped {skipped:,}",
                )

    if tracker:
        tracker.done(
            f"Complete — added {added:,} · updated {updated} "
            f"· skipped {skipped:,} · errors {len(errors)}"
        )

    return {"added": added, "updated": updated,
            "skipped": skipped, "errors": errors}
