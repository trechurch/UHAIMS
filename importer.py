"""
UHA IMS — Inventory Importer Service
v2.3.0  —  Fix: dedup columns AFTER normalization so two source columns
            that both map to the same canonical name (e.g. Pack Type + UOM
            both -> pack_type) get deduplicated before iterrows().
"""

import re
import chardet
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SKIP_PHRASES = [
    "PROPERTY OF COMPASS GROUP", "PRINTED BY", "BILL TO",
    "SHIP TO", "ITEMS ORDERED", "TOTAL COST ORDERED",
]

PACK_NORM = {
    'SLVS': 'SLEEVE', 'SLV': 'SLEEVE',
    'CASE': 'CASE',   'CSE': 'CASE',  'CS': 'CASE', 'CA': 'CASE',
    'CTN':  'CASE',   'CT':  'CASE',
    'EACH': 'EACH',   'EA':  'EACH',  'E': 'EACH',
}

HEADER_REQUIRED = ['ITEM', 'DESC', 'PRODUCT']
HEADER_PACK     = ['PACK', 'UOM']
HEADER_PRICE    = ['PRICE', 'COST', 'INVOICED']

COL_MAP = {
    'ITEM DESCRIPTION': 'description', 'ITEM DESC':  'description',
    'DESCRIPTION':      'description', 'ITEM':       'description',
    'DESC':             'description', 'PRODUCT':    'description',
    'PACK TYPE':        'pack_type',   'PACK':       'pack_type',
    'UOM':              'uom',
    'INVOICED PRICE':   'cost',        'CONFIRMED PRICE': 'cost',
    'CURRENT PRICE':    'cost',        'COST':       'cost',
    'PRICE':            'cost',        'UNIT PRICE': 'cost',
    'INVOICED QUANTITY':'quantity',    'CONFIRMED QUANTITY': 'quantity',
    'QUANTITY':         'quantity',    'INV COUNT':  'quantity',
    'COUNT':            'quantity',    'QTY':        'quantity',
    'LAST INVENTORY QTY': 'last_qty',
    'TOTAL PRICE':      'total_price',
    'LOCATION':         'location',
    'SEQ':              'seq',
    'GL CODE':          'gl_field',    'GL':         'gl_field',
    'ACCOUNT':          'gl_field',
    'VENDOR':           'vendor',      'VENDORS':    'vendor',
    'ITEM NUMBER':      'item_number',
    'MOG':              'mog',         'BRAND':      'brand',
    'MFG':              'brand',       'GTIN':       'gtin',
    'STATUS':           'status',      'CONFIRMATION STATUS': 'status',
    'CATEGORY':         'category',    'DELIVERY DATE': 'delivery_date',
}


def _scalar(val) -> Optional[str]:
    if isinstance(val, pd.Series):
        non_null = val.dropna()
        if non_null.empty:
            return None
        val = non_null.iloc[0]
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    return s if s else None


def normalize_pack_type(raw) -> str:
    s = _scalar(raw)
    if not s:
        return 'CASE'
    s = s.upper()
    s = re.sub(r'[^A-Z0-9/\s\-X.]', '', s)
    s = re.sub(r'/EACH$', '/EA', s)
    s = re.sub(r'/1$',    '/EA', s)
    parts  = re.split(r'([^A-Z0-9])', s)
    normed = [PACK_NORM.get(p, p) for p in parts]
    result = ''.join(normed).strip()
    return result if result else 'CASE'


def build_key(item_name, pack_type) -> Optional[str]:
    name = (_scalar(item_name) or '').upper()
    pack = normalize_pack_type(pack_type)
    if not name:
        return None
    return f"{name}||{pack}"


def clean_price(value) -> Optional[float]:
    s = _scalar(value)
    if not s:
        return None
    s = re.sub(r'[$,\s]', '', s)
    try:
        return float(s)
    except ValueError:
        return None


def split_gl_field(gl_string) -> Tuple[str, str]:
    s = _scalar(gl_string)
    if not s:
        return ('', '')
    m = re.search(r'^(.*?)\s*(\d{6})\s*$', s)
    if m:
        return (m.group(1).strip(), m.group(2))
    if re.fullmatch(r'\d{6}', s):
        return ('', s)
    return (s, '')


def should_skip_row(row_values) -> bool:
    parts = [_scalar(v) for v in row_values if _scalar(v)]
    row_str = ' '.join(parts).upper()
    return any(p in row_str for p in SKIP_PHRASES)


def _is_header_row(row) -> bool:
    vals   = [str(v).upper() for v in row if pd.notna(v)]
    joined = ' '.join(vals)
    has_item  = any(k in joined for k in HEADER_REQUIRED)
    has_pack  = any(k in joined for k in HEADER_PACK)
    has_price = any(k in joined for k in HEADER_PRICE)
    return has_item and (has_pack or has_price)


def find_header_row(df: pd.DataFrame, max_rows: int = 25) -> int:
    for i, row in df.iterrows():
        if i > max_rows:
            break
        if _is_header_row(row.values):
            return i
    return 0


def _dedup_columns(cols) -> List[str]:
    seen:   Dict[str, int] = {}
    result: List[str]      = []
    for c in cols:
        c = str(c).strip() if pd.notna(c) else ''
        if c in seen:
            seen[c] += 1
            result.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            result.append(c)
    return result


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map raw column names to canonical names via COL_MAP,
    then dedup any resulting duplicate canonical names.
    Deduplication happens AFTER mapping so that two source columns
    that map to the same canonical name (e.g. Pack Type + UOM -> pack_type)
    get suffixed rather than creating a duplicate-column Series bug.
    """
    rename = {}
    for col in df.columns:
        key = str(col).strip().upper()
        if key in COL_MAP:
            rename[col] = COL_MAP[key]
    df = df.rename(columns=rename)
    # Dedup after rename — catches cases like pack_type appearing twice
    df.columns = _dedup_columns(list(df.columns))
    return df


class InventoryImporter:

    SERVICE_MANIFEST = {
        "id":      "importer",
        "label":   "Inventory Importer",
        "version": "2.3.1",
        "type":    "service",
        "supported_formats": ["CSV", "XLSX", "XLS"],
        "depends_on": ["database"],
        "db_tables":  ["items", "item_history", "price_history"],
        "provides": [
            "read_file(filepath) -> DataFrame | None",
            "analyze_import(df) -> Dict",
            "execute_import(analysis, changed_by, source_document, doc_date) -> Dict",
            "import_file(filepath, changed_by, auto_approve) -> (analysis, results)",
        ],
    }

    SERVICE_DOCS = {
        "summary": "Parses vendor invoice and count sheet CSV/XLSX files.",
        "usage":   "Instantiate with InventoryDatabase. Call read_file() -> analyze_import() -> execute_import().",
        "demo_ready": True,
        "notes": (
            "v2.3.0: dedup columns AFTER normalization so Pack Type + UOM "
            "both mapping to pack_type no longer creates a Series ambiguity. "
            "UOM now maps to 'uom' (not 'pack_type') to preserve both columns."
        ),
        "known_issues": [
            "PAC inventory PDF import not yet ported.",
        ],
        "changelog": [
            {"version": "2.3.0", "date": "2026-03-18", "note": "Post-normalization column dedup. UOM -> uom not pack_type."},
            {"version": "2.2.0", "date": "2026-03-18", "note": "CSV header auto-detection + count-sheet column mappings."},
            {"version": "2.1.0", "date": "2026-03-18", "note": "chardet encoding + _scalar() + _dedup_columns()."},
        ],
    }

    def __init__(self, database):
        self.db     = database
        self.errors: List[str] = []

    def read_file(self, filepath: str) -> Optional[pd.DataFrame]:
        self.errors = []
        try:
            path = str(filepath).lower()
            if path.endswith('.csv'):
                df = self._read_csv_raw(filepath)
            elif path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(filepath, header=None, dtype=str)
            else:
                self.errors.append(f"Unsupported file type: {filepath}")
                return None
            hdr        = find_header_row(df)
            raw_cols   = df.iloc[hdr].tolist()
            df.columns = _dedup_columns(raw_cols)   # dedup raw names first
            df         = df.iloc[hdr + 1:].reset_index(drop=True)
            df         = normalize_columns(df)       # map + dedup canonical names
            return df
        except Exception as exc:
            self.errors.append(f"Read error: {exc}")
            return None

    def _read_csv_raw(self, filepath: str) -> pd.DataFrame:
        with open(filepath, 'rb') as f:
            raw = f.read(min(65536, Path(filepath).stat().st_size))
        detected = chardet.detect(raw)
        enc      = detected.get('encoding') or 'utf-8'
        fallbacks = [enc, 'utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
        seen = set()
        for encoding in fallbacks:
            if encoding in seen:
                continue
            seen.add(encoding)
            try:
                return pd.read_csv(filepath, encoding=encoding, header=None, dtype=str)
            except (UnicodeDecodeError, LookupError):
                continue
        return pd.read_csv(filepath, encoding='latin-1', header=None, encoding_errors='replace', dtype=str)

    def analyze_import(self, df: pd.DataFrame) -> Dict:
        analysis = {
            'total_rows': len(df),
            'new_items':  [],
            'updates':    [],
            'skipped':    [],
            'errors':     [],
        }
        for idx, row in df.iterrows():
            row = row.where(pd.notna(row), None)
            if should_skip_row(row.values):
                analysis['skipped'].append(idx)
                continue
            status = (_scalar(row.get('status')) or '').upper()
            pack   = _scalar(row.get('pack_type')) or ''
            if 'SUBSTITUTION' in status or pack.strip() == '99':
                analysis['skipped'].append(idx)
                continue
            description = _scalar(row.get('description'))
            if not description:
                analysis['skipped'].append(idx)
                continue
            pack_raw  = _scalar(row.get('pack_type')) or ''
            pack_norm = normalize_pack_type(pack_raw)
            key       = build_key(description, pack_norm)
            if not key:
                analysis['errors'].append(f"Row {idx + 1}: Could not build key")
                continue
            item_data = self._prepare_row(row, key, pack_norm)
            if self.db.item_exists(key):
                current = self.db.get_item(key)
                changes = {
                    f: {'old': current.get(f), 'new': item_data.get(f)}
                    for f in ('cost', 'pack_type', 'vendor', 'gl_code')
                    if item_data.get(f) is not None
                    and str(current.get(f)) != str(item_data.get(f))
                }
                analysis['updates'].append({
                    'key':         key,
                    'description': description,
                    'changes':     changes,
                    'row_data':    item_data,
                })
            else:
                analysis['new_items'].append({
                    'key':         key,
                    'description': description,
                    'row_data':    item_data,
                })
        return analysis

    def execute_import(self, analysis: Dict,
                       changed_by: str = "import",
                       source_document: str = None,
                       doc_date: str = None) -> Dict:
        results = {'new_items_added': 0, 'items_updated': 0, 'errors': []}
        for item in analysis['new_items']:
            try:
                if self.db.add_item(item['row_data'], changed_by=changed_by):
                    results['new_items_added'] += 1
            except Exception as exc:
                results['errors'].append(f"{item['key']}: {exc}")
        for item in analysis['updates']:
            try:
                result = self.db.upsert_item(
                    item['row_data'],
                    doc_date=doc_date,
                    source_document=source_document,
                    changed_by=changed_by,
                )
                if result in ('updated', 'created'):
                    results['items_updated'] += 1
            except Exception as exc:
                results['errors'].append(f"{item['key']}: {exc}")
        return results

    def import_file(self, filepath: str,
                    changed_by: str = "import",
                    auto_approve: bool = True) -> Tuple[Dict, Dict]:
        df = self.read_file(filepath)
        if df is None:
            return {'errors': self.errors}, {}
        analysis = self.analyze_import(df)
        if auto_approve:
            doc_date = datetime.now().strftime('%Y-%m-%d')
            results  = self.execute_import(
                analysis,
                changed_by=changed_by,
                source_document=Path(filepath).name,
                doc_date=doc_date,
            )
            return analysis, results
        return analysis, {}

    def _prepare_row(self, row, key: str, pack_norm: str) -> Dict:
        item = {
            'key':         key,
            'description': (_scalar(row.get('description')) or '').upper(),
            'pack_type':   pack_norm,
        }
        cost = clean_price(row.get('cost'))
        if cost is not None:
            item['cost'] = cost
        for field in ('vendor', 'item_number', 'mog', 'brand', 'gtin'):
            val = _scalar(row.get(field))
            if val:
                item[field] = val
        gl_raw = _scalar(row.get('gl_field')) or _scalar(row.get('gl_code'))
        if gl_raw:
            gl_name, gl_code = split_gl_field(gl_raw)
            if gl_code:
                item['gl_code'] = gl_code
                item['gl_name'] = gl_name
            elif gl_name:
                item['gl_code'] = gl_name
        qty_raw = _scalar(row.get('quantity'))
        if qty_raw:
            try:
                item['quantity_on_hand'] = float(re.sub(r'[^\d.]', '', qty_raw))
            except (ValueError, TypeError):
                pass
        return item
