"""
database_sheet_importer.py  —  Hidden admin import tool
Access via: ?page=db_import

Step 1: Import DATABASE sheet (item details + locked overrides)
Step 2: Import combined count sheet (quantities)
Step 3: Verify totals vs MyOrders
"""

import re
import io
import openpyxl
import streamlit as st
import pandas as pd
from datetime import datetime


def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def build_key(name, pack):
    n = str(name or "").strip().upper()
    p = str(pack or "").strip().upper()
    if not n:
        return None
    return f"{n}||{p}" if p else f"{n}||CASE"


def load_database_sheet(file_bytes):
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb['DATABASE']
    items = []
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
        if not row[0]:
            continue
        item_name  = str(row[0]).strip()
        pack_type  = str(row[1] or "").strip()
        cost       = safe_float(row[2])
        per        = str(row[3] or "Case").strip()
        conv_ratio = safe_float(row[4], 1.0)
        units      = str(row[5] or "Each").strip()
        vendor     = str(row[6] or "").strip()
        item_num   = str(row[7] or "").strip()
        mog        = str(row[8] or "").strip()
        brand      = str(row[10] or "").strip()
        yield_val  = safe_float(row[13], 1.0)
        key = build_key(item_name, pack_type)
        if not key:
            continue
        items.append({
            "key":                 key,
            "description":         item_name.upper(),
            "pack_type":           pack_type,
            "cost":                cost,
            "per":                 per,
            "conv_ratio":          conv_ratio,
            "unit":                units,
            "vendor":              vendor,
            "item_number":         item_num,
            "mog":                 mog,
            "brand":               brand,
            "yield":               yield_val,
            "override_conv_ratio": conv_ratio if conv_ratio != 1.0 else None,
            "override_yield":      yield_val  if yield_val  != 1.0 else None,
            "override_pack_type":  pack_type  if pack_type  else None,
            "override_vendor":     vendor     if vendor     else None,
            "status_tag":          "📋 DATABASE Import",
            "record_status":       "active",
            "cost_center":         "57231",
            "quantity_on_hand":    0,
            "is_chargeable":       True,
            "last_updated":        datetime.utcnow(),
            "created_date":        datetime.utcnow(),
        })
    return items


def load_count_sheet(file_bytes):
    wb  = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws  = wb['CurrentInventory']
    counts = {}
    prices = {}
    for row in ws.iter_rows(min_row=5, max_row=ws.max_row, values_only=True):
        desc = row[2]
        if not desc or desc == 'Item Description':
            continue
        count_raw = str(row[3] or "0")
        pack_type = str(row[4] or "").strip()
        price_raw = str(row[5] or "0")

        case_qty = each_qty = 0.0
        cm = re.match(r'([\d.]+)\s*Case.*?/([\d.]+)\s*Each', count_raw, re.I)
        if cm:
            case_qty = float(cm.group(1))
            each_qty = float(cm.group(2))
        else:
            try:
                each_qty = float(re.sub(r'[^\d.]', '', count_raw.split('/')[0]))
            except Exception:
                pass

        each_price = 0.0
        pm = re.match(r'\$([\d.]+)/\$([\d.]+)', price_raw)
        if pm:
            each_price = float(pm.group(2))

        conv = 1.0
        cnm  = re.match(r'^(\d+)/', pack_type)
        if cnm:
            conv = float(cnm.group(1))

        total_each = case_qty * conv + each_qty
        key = build_key(desc, pack_type)
        if not key:
            continue
        counts[key] = counts.get(key, 0.0) + total_each
        if each_price > 0:
            prices[key] = each_price

    return counts, prices


# ── UI ────────────────────────────────────────────────────────────────────────

def render():
    from database import InventoryDatabase, get_conn

    @st.cache_resource
    def get_db():
        return InventoryDatabase()

    st.title("📋 Concessions Database Import")
    st.caption("Hidden admin tool — access via `?page=db_import`")

    st.subheader("Upload Files")
    c1, c2 = st.columns(2)
    db_file    = c1.file_uploader("2026_UH__2_.xlsx  (DATABASE sheet)",
                                   type=["xlsx"], key="dbi_db")
    count_file = c2.file_uploader("TDECUcombinedvaluesseperatstands.xlsx",
                                   type=["xlsx"], key="dbi_cnt")

    if not db_file or not count_file:
        st.info("Upload both files to continue.")
        return

    db_bytes    = db_file.read()
    count_bytes = count_file.read()

    # ── Preview ───────────────────────────────────────────────────────────────
    if st.button("🔍 Preview — analyze, no writes", type="secondary"):
        with st.spinner("Reading files…"):
            db_items         = load_database_sheet(db_bytes)
            counts, prices   = load_count_sheet(count_bytes)

        db_keys  = {i["key"] for i in db_items}
        cnt_keys = set(counts.keys())
        matched  = db_keys & cnt_keys
        cnt_only = cnt_keys - db_keys
        db_only  = db_keys - cnt_keys

        total_count_val = sum(counts[k] * prices.get(k, 0) for k in counts)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("DATABASE items",     len(db_items))
        c2.metric("Count items",        len(cnt_keys))
        c3.metric("Matched (exact key)",len(matched))
        c4.metric("Count-only (new)",   len(cnt_only))
        st.metric("Count sheet total value", f"${total_count_val:,.2f}")

        if cnt_only:
            with st.expander(f"📋 {len(cnt_only)} in count but not in DATABASE"):
                st.dataframe(pd.DataFrame([
                    {"Key": k,
                     "Total Qty": f"{counts[k]:.1f}",
                     "Each Price": f"${prices.get(k,0):.2f}",
                     "Est Value":  f"${counts[k]*prices.get(k,0):.2f}"}
                    for k in sorted(cnt_only)
                ]), use_container_width=True, hide_index=True)

        if db_only:
            with st.expander(f"📋 {len(db_only)} DATABASE items with no count (zero qty)"):
                st.dataframe(pd.DataFrame([{"Key": k} for k in sorted(db_only)]),
                             use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── Step 1 ────────────────────────────────────────────────────────────────
    st.subheader("Step 1 — DATABASE sheet → item details + overrides")
    if st.button("▶️ Run Step 1", type="primary", key="s1"):
        db_inst  = get_db()
        db_items = load_database_sheet(db_bytes)
        added = updated = errors = 0
        prog  = st.progress(0)
        for i, item in enumerate(db_items):
            try:
                r = db_inst.upsert_item(
                    item,
                    doc_date=datetime.utcnow().strftime("%Y-%m-%d"),
                    source_document="2026_UH__2_.xlsx DATABASE",
                    changed_by="db_import",
                )
                if r == "created":   added   += 1
                elif r == "updated": updated += 1
            except Exception:
                errors += 1
            prog.progress((i+1)/len(db_items))
        prog.empty()
        st.success(f"✅ Step 1 — **{added}** added · **{updated}** updated · **{errors}** errors")

    st.markdown("---")

    # ── Step 2 ────────────────────────────────────────────────────────────────
    st.subheader("Step 2 — Count sheet → quantities")
    if st.button("▶️ Run Step 2", type="primary", key="s2"):
        db_inst        = get_db()
        counts, prices = load_count_sheet(count_bytes)
        updated = created = errors = 0
        prog    = st.progress(0)
        keys    = list(counts.keys())
        for i, key in enumerate(keys):
            qty        = counts[key]
            each_price = prices.get(key, 0.0)
            try:
                existing = db_inst.get_item(key)
                if existing:
                    with get_conn() as conn:
                        cur = conn.cursor()
                        cur.execute(
                            "UPDATE items SET quantity_on_hand=%s, "
                            "last_updated=%s WHERE key=%s",
                            (qty, datetime.utcnow(), key)
                        )
                    updated += 1
                else:
                    parts = key.split("||")
                    db_inst.add_item({
                        "key":              key,
                        "description":      parts[0],
                        "pack_type":        parts[1] if len(parts) > 1 else "CASE",
                        "cost":             each_price,
                        "quantity_on_hand": qty,
                        "cost_center":      "57231",
                        "status_tag":       "📦 Count Import",
                        "record_status":    "active",
                        "conv_ratio":       1.0,
                        "yield":            1.0,
                        "is_chargeable":    True,
                        "last_updated":     datetime.utcnow(),
                        "created_date":     datetime.utcnow(),
                    }, changed_by="count_import")
                    created += 1
            except Exception:
                errors += 1
            prog.progress((i+1)/len(keys))
        prog.empty()
        st.success(
            f"✅ Step 2 — **{updated}** qty updated · "
            f"**{created}** new items · **{errors}** errors"
        )

    st.markdown("---")

    # ── Step 3 ────────────────────────────────────────────────────────────────
    st.subheader("Step 3 — Verify totals")
    myorders_target = 114371.81
    if st.button("🔍 Check Totals", key="s3"):
        db_inst     = get_db()
        total_value = db_inst.get_inventory_value()
        total_items = db_inst.count_items("active")

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Active Items",  total_items)
        c2.metric("Our Total Value",     f"${total_value:,.2f}")
        c3.metric("MyOrders Target",     f"${myorders_target:,.2f}")

        diff = total_value - myorders_target
        if abs(diff) < 100:
            st.success(f"✅ Within $100 — variance: ${diff:+,.2f}")
        elif abs(diff) < 2000:
            st.warning(f"⚠️ Variance: ${diff:+,.2f} — review unmatched items")
        else:
            st.error(f"❌ Variance: ${diff:+,.2f} — check for missing items or wrong costs")


render()
