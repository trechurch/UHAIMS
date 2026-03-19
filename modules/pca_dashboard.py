# ──────────────────────────────────────────────────────────────────────────────
#  modules/pca_dashboard.py  —  PCA Dashboard Module
#  v1.1.0  —  Full UI matching prototype:
#              Header | Food Ingredients | Disposables | Cost Summary
#              All fields pulled/calculated from DB on item selection.
# ──────────────────────────────────────────────────────────────────────────────

import json
import streamlit as st
import pandas as pd
from base import Dashboard

class PCADashboard(Dashboard):

    MANIFEST = {
        "id":       "pca_dashboard",
        "label":    "PCA Tool",
        "version":  "1.1.0",
        "icon":     "🧪",
        "status":   "active",
        "page_key": "pca",
        "menu": {
            "parent":   "Dashboards",
            "label":    "PCA Dashboard",
            "shortcut": "P",
            "position": 60,
        },
        "sidebar": {
            "section":  "",
            "position": 60,
            "show":     True,
        },
        "depends_on":   ["database", "pca_engine"],
        "db_tables":    ["items", "recipes", "recipe_ingredients"],
        "session_keys": ["pca_recipe_id"],
        "abilities": [
            "Create and manage PCA recipes",
            "Add food ingredients and disposables from inventory",
            "Calculate EP cost, ES cost, cost per portion",
            "Compare product cost % against goal",
            "Duplicate and export recipes",
        ],
        "permissions": {"min_role": "user"},
    }

    DOCS = {
        "summary": "Portion Cost Analysis — build recipes from inventory items, calculate and compare costs.",
        "usage": "Select or create a recipe. Add ingredients from the inventory database. Review cost % vs goal.",
        "demo_ready": True,
        "notes": "v1.1.0: Full UI matching the Excel prototype. All calculated fields mirror prototype formulas.",
        "known_issues": [],
        "changelog": [
            {"version": "1.1.0", "date": "2026-03-19", "note": "Full prototype-matching UI."},
            {"version": "1.0.2", "date": "2026-03-19", "note": "Schema detection + rebuild."},
            {"version": "1.0.0", "date": "2026-03-18", "note": "Initial implementation."},
        ],
    }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_load(self) -> None:
        self._ensure_tables()

    def _ensure_tables(self):
        try:
            from database import get_conn
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'recipes' AND column_name = 'name'
                """)
                if not cur.fetchone():
                    cur.execute("DROP TABLE IF EXISTS recipe_ingredients CASCADE;")
                    cur.execute("DROP TABLE IF EXISTS recipes CASCADE;")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS recipes (
                        recipe_id            SERIAL PRIMARY KEY,
                        name                 TEXT NOT NULL,
                        category             TEXT DEFAULT 'Concessions',
                        component_name       TEXT DEFAULT 'Default',
                        selling_price        NUMERIC(10,4) DEFAULT 0,
                        cost_pct_goal        NUMERIC(6,4)  DEFAULT 0.17,
                        servings_per_portion INTEGER DEFAULT 1,
                        portions             INTEGER DEFAULT 1,
                        recipe_date          DATE,
                        updated_by           TEXT,
                        notes                TEXT,
                        record_status        TEXT DEFAULT 'active',
                        created_at           TIMESTAMPTZ DEFAULT NOW(),
                        last_updated         TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE TABLE IF NOT EXISTS recipe_ingredients (
                        line_id         SERIAL PRIMARY KEY,
                        recipe_id       INTEGER REFERENCES recipes(recipe_id) ON DELETE CASCADE,
                        item_key        TEXT,
                        ingredient_type TEXT DEFAULT 'food',
                        ep_amount       NUMERIC(10,4) DEFAULT 1.0,
                        unit            TEXT DEFAULT 'Each',
                        sort_order      INTEGER DEFAULT 0,
                        notes           TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_recipe_id
                        ON recipe_ingredients(recipe_id);
                """)
        except Exception as exc:
            st.warning(f"PCA table setup: {exc}")

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**🧪 PCA Tool**")
            st.caption("Portion Cost Analysis")

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> None:
        from pca_engine import PCAEngine
        pca = PCAEngine(self.db)

        st.title("🧪 Portion Cost Analysis")

        # ── Recipe selector ───────────────────────────────────────────────────
        recipes    = pca.get_all_recipes()
        recipe_map = {r["name"]: r["recipe_id"] for r in recipes}
        names      = sorted(recipe_map.keys())

        col_sel, col_new, col_dup, col_del = st.columns([4, 1, 1, 1])
        with col_sel:
            selected_name = st.selectbox(
                "Recipe", ["— select or create new —"] + names,
                key="pca_sel", label_visibility="collapsed"
            )
        selected_id = recipe_map.get(selected_name)

        with col_new:
            if st.button("➕ New", use_container_width=True):
                self.set_state("pca_recipe_id", None)
                st.session_state["pca_creating"] = True
        with col_dup:
            if selected_id and st.button("📋 Copy", use_container_width=True):
                new_id = pca.duplicate_recipe(selected_id, new_name=f"{selected_name} (Copy)")
                st.success("Duplicated.")
                st.rerun()
        with col_del:
            if selected_id and st.button("🗑️ Archive", use_container_width=True):
                pca.delete_recipe(selected_id, soft=True)
                st.success("Archived.")
                st.rerun()

        # ── New recipe form ───────────────────────────────────────────────────
        if st.session_state.get("pca_creating"):
            with st.form("new_pca_form", clear_on_submit=True):
                st.subheader("New Recipe")
                c1, c2 = st.columns(2)
                name     = c1.text_input("Menu Item Name *")
                category = c2.selectbox("Category", ["Concessions", "Catering", "Premium", "Other"])
                c3, c4, c5, c6 = st.columns(4)
                price    = c3.number_input("Selling Price $", value=0.0,  format="%.2f")
                goal_pct = c4.number_input("Cost % Goal",    value=17.0, format="%.1f")
                servings = c5.number_input("Servings/Portion", value=1, min_value=1, step=1)
                portions = c6.number_input("Portions",          value=1, min_value=1, step=1)
                submitted = st.form_submit_button("Create Recipe", type="primary")
            if submitted and name:
                rid = pca.create_recipe(
                    name=name.strip(), category=category,
                    selling_price=price, cost_pct_goal=goal_pct / 100,
                    servings_per_portion=int(servings), portions=int(portions),
                    updated_by="web_user",
                )
                if rid:
                    st.success(f"✅ '{name}' created!")
                    st.session_state["pca_creating"] = False
                    st.rerun()
            st.stop()

        if not selected_id:
            st.info("Select a recipe above or create a new one.")
            return

        # ── Load recipe + calculate ───────────────────────────────────────────
        result = pca.calculate_pca(selected_id)
        if not result:
            st.error("Could not load recipe.")
            return

        recipe  = result["recipe"]
        metrics = result["metrics"]
        totals  = result["totals"]

        # ── HEADER ────────────────────────────────────────────────────────────
        with st.expander("📋 Recipe Header", expanded=True):
            hc1, hc2, hc3, hc4 = st.columns(4)
            hc1.markdown(f"**Menu Item**  \n{recipe['name']}")
            hc2.markdown(f"**Category**  \n{recipe.get('category','—')}")
            hc3.markdown(f"**Date**  \n{str(recipe.get('recipe_date') or '—')[:10]}")
            hc4.markdown(f"**Updated By**  \n{recipe.get('updated_by') or '—'}")

            hc5, hc6, hc7, hc8 = st.columns(4)
            hc5.markdown(f"**Selling Price**  \n${metrics['selling_price']:.2f}")
            hc6.markdown(f"**Cost % Goal**  \n{metrics['cost_pct_goal']*100:.1f}%")
            hc7.markdown(f"**Servings/Portion**  \n{recipe.get('servings_per_portion',1)}")
            hc8.markdown(f"**Portions**  \n{recipe.get('portions',1)}")

        # ── COST SUMMARY ─────────────────────────────────────────────────────
        over = metrics["over_goal"]
        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
        sc1.metric("Cost / Portion",  f"${totals['cost_per_portion']:.4f}")
        sc2.metric("Cost / Serving",  f"${totals['cost_per_serving']:.4f}")
        sc3.metric("Product Cost %",  f"{metrics['product_cost_pct']*100:.2f}%")
        sc4.metric("Goal Cost %",     f"{metrics['cost_pct_goal']*100:.1f}%")
        sc5.metric("Per Serving Goal",f"${metrics['per_serving_cost_goal']:.4f}")

        if over:
            st.error(f"⚠️  Over cost goal by **{abs(metrics['pct_diff'])*100:.2f}%** — target is {metrics['cost_pct_goal']*100:.1f}%, actual is {metrics['product_cost_pct']*100:.2f}%")
        else:
            st.success(f"✅  On target — {abs(metrics['pct_diff'])*100:.2f}% under goal")

        st.markdown("---")

        # ── FOOD INGREDIENTS ──────────────────────────────────────────────────
        st.subheader("🍽️ Food Ingredients")
        if result["food_lines"]:
            food_df = pd.DataFrame([{
                "Food Ingredient":         l.get("description") or l.get("item_key",""),
                "EP Amount":               l["ep_amount"],
                "Unit":                    l["unit"],
                "Invoice Amount":          f"${float(l.get('invoice_amount') or 0):.2f}",
                "Conv Ratio":              l.get("conv_ratio",""),
                "Yield %":                 f"{float(l.get('yield_pct') or 1)*100:.0f}%",
                "ES Amount":               l.get("es_amount",""),
                "ES Cost":                 f"${l.get('es_cost',0):.4f}",
                "EP Cost":                 f"${l['ep_cost']:.4f}",
                "Vendor":                  l.get("vendor",""),
            } for l in result["food_lines"]])
            st.dataframe(food_df, use_container_width=True, hide_index=True)
            st.markdown(f"**Total Food Cost: ${totals['total_food_cost']:.4f}**")
        else:
            st.info("No food ingredients yet.")

        # Add food ingredient
        with st.expander("➕ Add Food Ingredient"):
            self._add_ingredient_form(pca, selected_id, "food")

        st.markdown("---")

        # ── DISPOSABLES ───────────────────────────────────────────────────────
        st.subheader("📦 Disposables")
        if result["disposable_lines"]:
            disp_df = pd.DataFrame([{
                "Disposable":              l.get("description") or l.get("item_key",""),
                "Units/Serving":           l["ep_amount"],
                "Unit":                    l["unit"],
                "Invoice Amount":          f"${float(l.get('invoice_amount') or 0):.2f}",
                "Conv Ratio":              l.get("conv_ratio",""),
                "Yield %":                 f"{float(l.get('yield_pct') or 1)*100:.0f}%",
                "Units/Portion":           l.get("es_amount",""),
                "Cost/Portion":            f"${l.get('cost_per_portion',0):.4f}",
                "Cost/Serving":            f"${l.get('cost_per_serving',0):.4f}",
                "Vendor":                  l.get("vendor",""),
            } for l in result["disposable_lines"]])
            st.dataframe(disp_df, use_container_width=True, hide_index=True)
            st.markdown(f"**Total Disposable Cost: ${totals['total_disposable_cost']:.4f}**")
        else:
            st.info("No disposables yet.")

        with st.expander("➕ Add Disposable"):
            self._add_ingredient_form(pca, selected_id, "disposable")

        st.markdown("---")

        # ── REMOVE INGREDIENT ─────────────────────────────────────────────────
        all_lines = result["food_lines"] + result["disposable_lines"]
        if all_lines:
            with st.expander("🗑️ Remove Ingredient"):
                line_options = {
                    f"{l.get('description') or l.get('item_key','')} ({l['ingredient_type']})": l["line_id"]
                    for l in all_lines
                }
                to_remove = st.selectbox("Select line to remove", list(line_options.keys()), key="pca_remove_sel")
                if st.button("Remove", key="pca_remove_btn"):
                    pca.remove_ingredient(line_options[to_remove])
                    st.success("Removed.")
                    st.rerun()

        # ── EXPORT ────────────────────────────────────────────────────────────
        export = pca.export_pca_dict(selected_id)
        st.download_button(
            "⬇️ Export PCA as JSON",
            data=json.dumps(export, indent=2, default=str),
            file_name=f"pca_{recipe['name'].replace(' ','_')}.json",
            mime="application/json",
        )

    # ── Add ingredient form ───────────────────────────────────────────────────

    def _add_ingredient_form(self, pca, recipe_id: int, ing_type: str):
        """Shared form for adding food ingredients and disposables."""
        all_items = self.db.get_all_items()
        if not all_items:
            st.warning("No inventory items found.")
            return

        # Build display label → item dict lookup
        item_map = {
            f"{i['description']}  ({i['pack_type']})": i
            for i in all_items
        }

        form_key = f"add_{ing_type}_{recipe_id}"
        with st.form(form_key):
            c1, c2, c3 = st.columns([4, 1, 1])
            item_label = c1.selectbox(
                "Item from Inventory",
                list(item_map.keys()),
                key=f"{form_key}_item"
            )
            item       = item_map[item_label]

            # Default unit from item pack_type
            default_unit = "Each"
            pack = (item.get("pack_type") or "").upper()
            if "OZ" in pack or "OUNCE" in pack:
                default_unit = "Ounce"
            elif "LB" in pack or "POUND" in pack:
                default_unit = "Pound"
            elif "CASE" in pack or "CS" in pack:
                default_unit = "Case"

            ep_amount = c2.number_input(
                "EP Amount" if ing_type == "food" else "Units/Serving",
                value=1.0, format="%.4f", key=f"{form_key}_ep"
            )
            unit = c3.selectbox(
                "Unit",
                ["Each", "Ounce", "Pound", "Case", "Sleeve", "Oz", "Fl Oz"],
                index=["Each","Ounce","Pound","Case","Sleeve","Oz","Fl Oz"].index(default_unit)
                      if default_unit in ["Each","Ounce","Pound","Case","Sleeve","Oz","Fl Oz"] else 0,
                key=f"{form_key}_unit"
            )

            # Show pulled values from DB as reference
            inv_amount = float(item.get("cost") or 0)
            conv_ratio = float(item.get("conv_ratio") or 1)
            yield_pct  = float(item.get("yield") or 1)
            vendor     = item.get("vendor") or "—"

            st.caption(
                f"📦 From DB — Invoice: **${inv_amount:.2f}** · "
                f"Conv Ratio: **{conv_ratio}** · "
                f"Yield: **{yield_pct*100:.0f}%** · "
                f"Vendor: **{vendor}**"
            )

            submitted = st.form_submit_button(
                f"Add {ing_type.title()}", type="primary"
            )

        if submitted:
            lid = pca.add_ingredient(
                recipe_id=recipe_id,
                item_key=item["key"],
                ep_amount=ep_amount,
                unit=unit,
                ingredient_type=ing_type,
            )
            if lid:
                st.success(f"✅ Added {item['description']}")
                st.rerun()

    # ── end of render ─────────────────────────────────────────────────────────

# ── end of PCADashboard ───────────────────────────────────────────────────────
