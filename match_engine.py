"""
match_engine.py — Multi-phase inventory item matching engine
v1.0.0

Three-pass pipeline:
  Pass 1 — Exact        : key match OR exact normalized-description match  → confidence 1.00
  Pass 2 — Fuzzy        : WRatio ≥ FUZZY_THRESHOLD (85)                   → confidence 0.85–0.99
  Pass 3 — Probabilistic: composite multi-signal score ≥ PROB_THRESHOLD   → confidence 0.60–0.84
  Remainder             : manual review queue

Five scoring signals per candidate:
  • WRatio         (40 %) — holistic string similarity       → maps to SUPERLATIVE degree
  • token_set_ratio(25 %) — word-level, order-insensitive    → maps to POSITIVE degree
  • partial_ratio  (15 %) — substring match                  → maps to COMPARATIVE degree
  • GTIN exact     (10 %) — barcode identity
  • pack_type sim  (10 %) — packaging similarity

Degrees of Comparison (composite score):
  Superlative  ≥ 90 — definitively the best available match
  Comparative  75–89 — better than alternatives
  Positive     60–74 — usable, meets minimum threshold
  Probabilistic < 60 — statistical guess only; recommend manual review
"""

from __future__ import annotations
import re
from typing import Dict, List, Tuple

# ── Thresholds ────────────────────────────────────────────────────────────────
FUZZY_THRESHOLD  = 85     # WRatio for high-confidence auto-assignment
PROB_THRESHOLD   = 60     # composite score for probabilistic auto-assignment
TOP_N_CANDIDATES = 5      # candidates retained per item for review


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Uppercase, collapse non-alphanumeric to spaces."""
    return re.sub(r'[^A-Z0-9 ]+', ' ', (s or '').upper()).strip()


def _make_key(description: str) -> str:
    return re.sub(r'[^A-Z0-9 ]', '', description.upper().strip())[:64]


def _degree(composite: float) -> Tuple[str, str]:
    """Return (degree_label, human note) for a composite score."""
    if composite >= 90:
        return "superlative",  "Best available match — very high confidence"
    if composite >= 75:
        return "comparative",  "Strong match — better than alternatives"
    if composite >= 60:
        return "positive",     "Usable match — meets minimum threshold"
    return     "probabilistic","Low-confidence — statistical estimate only"


def _score_pair(qn: str, cn: str,
                qg: str, cg: str,
                qp: str, cp: str) -> Dict:
    """
    Score one query/candidate pair.
    Returns a dict with all five signal scores + composite + degree info.
    """
    from rapidfuzz import fuzz
    wratio    = fuzz.WRatio(qn, cn)
    token_set = fuzz.token_set_ratio(qn, cn)
    partial   = fuzz.partial_ratio(qn, cn)
    gtin_s    = 100.0 if (qg and cg and qg == cg) else 0.0
    pack_s    = fuzz.token_set_ratio(
        re.sub(r'[^A-Z0-9 ]', ' ', (qp or '').upper()),
        re.sub(r'[^A-Z0-9 ]', ' ', (cp or '').upper()),
    ) if qp and cp else 0.0

    composite = (0.40 * wratio + 0.25 * token_set
               + 0.15 * partial + 0.10 * gtin_s + 0.10 * pack_s)
    deg, note = _degree(composite)

    return {
        "wratio":      round(wratio, 1),
        "token_set":   round(token_set, 1),
        "partial":     round(partial, 1),
        "gtin_score":  round(gtin_s, 1),
        "pack_score":  round(pack_s, 1),
        "composite":   round(composite, 1),
        "degree":      deg,
        "degree_note": note,
    }


# ── Main Engine ───────────────────────────────────────────────────────────────

def run_multiphase_match(db_items: List[Dict],
                         gl_categories: List[Dict],
                         only_unassigned: bool = True) -> Dict:
    """
    Run all three passes against the GL category pool.

    Returns a serializable session dict:

      {
        "exact":         [MatchResult, ...],
        "fuzzy":         [MatchResult, ...],
        "probabilistic": [MatchResult, ...],
        "unmatched":     [MatchResult, ...],
        "stats":         { ... },
      }

    Each MatchResult:
      {
        "db_item":    { ...original DB item dict... },
        "phase":      "exact" | "fuzzy" | "probabilistic" | "unmatched",
        "confidence": float (0.0–1.0),
        "candidates": [ ...up to TOP_N candidate dicts... ],
      }

    Each candidate dict:
      {
        "description", "gl_code", "gl_name", "gtin", "pack_type",
        "wratio",       # → SUPERLATIVE degree axis
        "token_set",    # → POSITIVE degree axis
        "partial",      # → COMPARATIVE degree axis
        "gtin_score", "pack_score",
        "composite",    # → PROBABILISTIC degree axis (weighted composite)
        "degree",       # "superlative" | "comparative" | "positive" | "probabilistic"
        "degree_note",  # human-readable explanation
      }
    """
    from rapidfuzz import process, fuzz

    # ── Build candidate pool (deduplicated by norm) ───────────────────────────
    pool: List[Dict] = []
    seen: set = set()
    for cat in gl_categories:
        for item in cat["items"]:
            norm = _norm(item["description"])
            if norm in seen:
                continue
            seen.add(norm)
            pool.append({
                "description": item["description"].upper(),
                "norm":        norm,
                "key":         _make_key(item["description"]),
                "gl_code":     cat["gl_code"],
                "gl_name":     cat["gl_name"],
                "gtin":        (item.get("gtin") or "").strip(),
                "pack_type":   (item.get("pack_type") or "").strip(),
            })

    pool_norms = [p["norm"] for p in pool]
    by_norm    = {p["norm"]: p for p in pool}
    by_key     = {p["key"]:  p for p in pool}

    exact_r, fuzzy_r, prob_r, unmatched_r = [], [], [], []
    attempted = 0

    for db_item in db_items:
        if only_unassigned and db_item.get("gl_code"):
            continue
        attempted += 1

        query      = (db_item.get("description") or "").upper().strip()
        qkey       = _make_key(query)
        qnorm      = _norm(query)
        qgtin      = (db_item.get("gtin") or "").strip()
        qpack      = (db_item.get("pack_type") or "").strip()

        if not query:
            unmatched_r.append({"db_item": db_item, "phase": "unmatched",
                                "confidence": 0.0, "candidates": []})
            continue

        # ── Pass 1: Exact ─────────────────────────────────────────────────────
        ep = by_key.get(qkey) or by_norm.get(qnorm)
        if ep:
            cand = {
                "description": ep["description"],
                "gl_code":     ep["gl_code"],
                "gl_name":     ep["gl_name"],
                "gtin":        ep["gtin"],
                "pack_type":   ep["pack_type"],
                "wratio":      100.0,
                "token_set":   100.0,
                "partial":     100.0,
                "gtin_score":  100.0 if qgtin and ep["gtin"] == qgtin else 0.0,
                "pack_score":  100.0,
                "composite":   100.0,
                "degree":      "superlative",
                "degree_note": "Exact description / key match",
            }
            exact_r.append({"db_item": db_item, "phase": "exact",
                            "confidence": 1.0, "candidates": [cand]})
            continue

        # ── Pass 2 & 3: Score top-N candidates ───────────────────────────────
        top = process.extract(qnorm, pool_norms, scorer=fuzz.WRatio,
                              limit=TOP_N_CANDIDATES, score_cutoff=40)
        if not top:
            unmatched_r.append({"db_item": db_item, "phase": "unmatched",
                                "confidence": 0.0, "candidates": []})
            continue

        candidates = []
        for norm_str, wratio_raw, _ in top:
            p = by_norm[norm_str]
            s = _score_pair(qnorm, norm_str, qgtin, p["gtin"], qpack, p["pack_type"])
            candidates.append({
                "description": p["description"],
                "gl_code":     p["gl_code"],
                "gl_name":     p["gl_name"],
                "gtin":        p["gtin"],
                "pack_type":   p["pack_type"],
                **s,
            })

        candidates.sort(key=lambda c: c["composite"], reverse=True)
        best = candidates[0]

        if best["wratio"] >= FUZZY_THRESHOLD:
            # Pass 2 — high-confidence fuzzy
            conf = 0.85 + (best["wratio"] - FUZZY_THRESHOLD) / (100 - FUZZY_THRESHOLD) * 0.14
            fuzzy_r.append({"db_item": db_item, "phase": "fuzzy",
                            "confidence": round(conf, 4), "candidates": candidates})

        elif best["composite"] >= PROB_THRESHOLD:
            # Pass 3 — probabilistic
            conf = 0.60 + (best["composite"] - PROB_THRESHOLD) / (FUZZY_THRESHOLD - PROB_THRESHOLD) * 0.24
            prob_r.append({"db_item": db_item, "phase": "probabilistic",
                          "confidence": round(conf, 4), "candidates": candidates})

        else:
            # No phase cleared — manual review
            unmatched_r.append({"db_item": db_item, "phase": "unmatched",
                                "confidence": round(best["composite"] / 100, 4),
                                "candidates": candidates[:3]})

    stats = {
        "attempted":     attempted,
        "exact":         len(exact_r),
        "fuzzy":         len(fuzzy_r),
        "probabilistic": len(prob_r),
        "unmatched":     len(unmatched_r),
        "auto_assigned": len(exact_r) + len(fuzzy_r),
    }

    return {
        "exact":         exact_r,
        "fuzzy":         fuzzy_r,
        "probabilistic": prob_r,
        "unmatched":     unmatched_r,
        "stats":         stats,
    }
