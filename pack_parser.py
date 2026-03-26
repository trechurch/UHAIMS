"""
pack_parser.py — Conv Ratio Parser
v1.0.0

Parses pack type strings into (conv_ratio, unit, confidence, flag_reason).
Confidence: 'high' | 'medium' | 'low'
Flag reason: None if confident, else a human-readable explanation.

Used by importer.py and database_sheet_importer.py.
"""

import re
from typing import Tuple, Optional

# ── Unit conversion to ounces ──────────────────────────────────────────────
OZ_PER = {
    "OZ":  1.0,
    "FL OZ": 1.0,
    "LB":  16.0,
    "GAL": 128.0,
    "QT":  32.0,
    "PT":  16.0,
    "L":   33.814,
    "ML":  0.033814,
    "G":   0.035274,
    "KG":  35.274,
    "GM":  0.035274,
}

# ── Known ambiguous/garbage values → always flag ──────────────────────────
FLAG_PATTERNS = {
    "**", "???", "each", "bottle", "need pack type",
    "tbd", "unknown", "", "n/a",
}

# ── Special named pack formats ────────────────────────────────────────────
NAMED_PACKS = {
    # sleeves
    r'(\d+)\s*slvs?\s*of\s*(\d+)':   lambda m: float(m.group(1)) * float(m.group(2)),
    r'(\d+)\s*slvs?$':                lambda m: float(m.group(1)),
    # "X pack"
    r'^(\d+)\s*pack$':                lambda m: float(m.group(1)),
}


def _to_oz(qty: float, unit: str) -> float:
    """Convert qty in given unit to ounces."""
    u = unit.upper().strip()
    factor = OZ_PER.get(u)
    if factor:
        return qty * factor
    return qty  # unknown unit — return as-is


def parse_pack(pack_str: str, per: str = "Case",
               existing_conv: float = None
               ) -> Tuple[float, str, str, Optional[str]]:
    """
    Parse a pack type string into conv_ratio.

    Returns:
        (conv_ratio, unit, confidence, flag_reason)
        confidence: 'high' | 'medium' | 'low'
        flag_reason: None if confident, string if needs review
    """
    if not pack_str:
        return (1.0, "Each", "low", "Empty pack type string")

    raw = str(pack_str).strip()
    s   = raw.upper()

    # ── Already an Each item ───────────────────────────────────────────────
    if per and str(per).strip().lower() == "each":
        # per=Each means cost is already per-unit — conv_ratio = 1
        # BUT if pack string has a number, that's the pack size
        m = re.match(r'^(\d+\.?\d*)$', s)
        if m:
            return (float(m.group(1)), "Each", "high", None)
        return (1.0, "Each", "high", None)

    # ── Flag known garbage ─────────────────────────────────────────────────
    if s.lower() in FLAG_PATTERNS or '???' in s or s == '**':
        # Use existing conv_ratio if we have a reliable one
        if existing_conv and existing_conv > 1.0:
            return (existing_conv, "Each", "medium",
                    f"Pack type '{raw}' is ambiguous — using existing conv_ratio={existing_conv}")
        return (1.0, "Each", "low",
                f"Pack type '{raw}' is unreadable — conv_ratio unknown, needs review")

    # ── Named pack formats ────────────────────────────────────────────────
    for pattern, fn in NAMED_PACKS.items():
        m = re.match(pattern, s, re.I)
        if m:
            try:
                ratio = fn(m)
                return (ratio, "Each", "high", None)
            except Exception:
                pass

    # ── Weight AVG format: "2/7#AVG" → 2 pieces × 7lb avg
    m = re.match(r'^(\d+)/(\d+\.?\d*)#', s)
    if m:
        count = float(m.group(1))
        weight_lb = float(m.group(2))
        ratio = count * _to_oz(weight_lb, "LB")
        return (ratio, "oz", "high", None)

    # ── Standard N/M formats ──────────────────────────────────────────────
    # e.g. "24/12oz CAN", "1/50 LB", "8/12 CT", "1000/9GM", "10/250CT/Ea"

    m = re.match(r'^(\d+\.?\d*)\s*/\s*(\d+\.?\d*)\s*([A-Z]*).*$', s)
    if m:
        outer = float(m.group(1))
        inner = float(m.group(2))
        unit  = m.group(3).strip() if m.group(3) else ""

        if outer == 1:
            # "1/50 LB" → 1 unit of 50 LB → convert to oz
            if unit in OZ_PER:
                ratio = _to_oz(inner, unit)
                return (ratio, "oz", "high", None)
            elif unit in ("CT", "COUNT", "EA", "EACH", "PC", "PCS", ""):
                return (inner, "Each", "high", None)
            else:
                # Unknown unit — flag it
                return (inner, unit, "medium",
                        f"Unit '{unit}' in '{raw}' not recognized — verify conversion")
        else:
            # "24/12oz CAN" → outer=24 each per case (inner is size of each)
            # "8/12 CT" → 8 × 12 = 96 each
            if unit in ("CT", "COUNT", "EA", "EACH", "PC", "PCS", "CAN", "BTL",
                        "BT", "PKT", "PKG", "BAG", "BOX", "OZ", ""):
                # outer × inner = total each
                total = outer * inner
                # But if inner is a weight (oz/lb), outer is the pack count
                if unit in ("OZ", "FL"):
                    return (outer, "Each", "high", None)
                return (total if inner > 1 else outer, "Each", "high", None)
            else:
                # outer is most likely the count
                return (outer, "Each", "medium",
                        f"Assumed outer={outer} each from '{raw}' — verify")

    # ── Single number ─────────────────────────────────────────────────────
    m = re.match(r'^(\d+\.?\d*)$', s)
    if m:
        ratio = float(m.group(1))
        if ratio == 1.0:
            return (1.0, "Each", "medium",
                    f"Pack type is '1' — may be a single unit or placeholder")
        return (ratio, "Each", "high", None)

    # ── Weight formats: "1 LB", "1.5 GAL", "2/7#AVG" ─────────────────────
    m = re.match(r'^(\d+\.?\d*)\s*(LB|GAL|OZ|QT|PT|L|G|KG|GM)$', s)
    if m:
        qty  = float(m.group(1))
        unit = m.group(2)
        ratio = _to_oz(qty, unit)
        return (ratio, "oz", "high", None)

    # "#AVG" weight format e.g. "2/7#AVG"
    m = re.match(r'^(\d+)/(\d+\.?\d*)#', s)
    if m:
        count = float(m.group(1))
        weight_lb = float(m.group(2))
        ratio = count * _to_oz(weight_lb, "LB")
        return (ratio, "oz", "high", None)

    # ── BIB format: "1/5GAL", "1/2.5Gal" ────────────────────────────────
    m = re.match(r'^1/(\d+\.?\d*)\s*(GAL|L|QT)$', s, re.I)
    if m:
        qty  = float(m.group(1))
        unit = m.group(2).upper()
        ratio = _to_oz(qty, unit)
        return (ratio, "oz", "high", None)

    # ── Fallback: use existing if reliable ────────────────────────────────
    if existing_conv and existing_conv > 1.0:
        return (existing_conv, "Each", "medium",
                f"Could not parse '{raw}' — using existing conv_ratio={existing_conv}")

    return (1.0, "Each", "low",
            f"Could not parse pack type '{raw}' — needs manual review")


# ── Test harness ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        ("24/12oz CAN",     "Case",  24.0),
        ("15/25oz CAN",     "Case",  15.0),
        ("1/50 LB",         "Case",  800.0),
        ("1/5GAL",          "Case",  640.0),
        ("1/2.5GAL",        "Case",  320.0),
        ("1000/1",          "Case",  1000.0),
        ("15slvsOf25",      "Case",  375.0),
        ("8/12 CT",         "Case",  96.0),
        ("1/60 CT",         "Case",  60.0),
        ("4/250ct",         "Case",  1000.0),
        ("2/7#AVG",         "Case",  224.0),
        ("50/5 OZ",         "Case",  50.0),
        ("24 pack",         "Case",  24.0),
        ("12/80",           "Case",  960.0),
        ("6",               "Each",  6.0),
        ("1",               "Case",  1.0),
        ("**",              "Each",  1.0),
        ("bottle",          "Case",  1.0),
        ("need pack type",  "Case",  1.0),
        ("1/10 LB",         "Case",  160.0),
        ("1/12 LB",         "Case",  192.0),
        ("1/1000 ct",       "Case",  1000.0),
        ("10/250 CT",       "Case",  2500.0),
        ("12/3.1 OZ",       "Case",  12.0),
    ]

    print(f"{'Pack Type':<22} {'Per':<6} {'Expected':>10} {'Got':>10} {'Conf':<8} {'Flag'}")
    print("-" * 90)
    passed = failed = flagged = 0
    for pack, per, expected in test_cases:
        ratio, unit, conf, flag = parse_pack(pack, per)
        ok = abs(ratio - expected) < 0.1
        status = "✅" if ok else "❌"
        if ok: passed += 1
        else:  failed += 1
        if flag: flagged += 1
        flag_short = (flag[:40] + "…") if flag and len(flag) > 40 else (flag or "")
        print(f"{status} {pack:<22} {per:<6} {expected:>10.1f} {ratio:>10.1f} {conf:<8} {flag_short}")

    print(f"\n{passed} passed, {failed} failed, {flagged} flagged for review")
