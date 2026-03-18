# ──────────────────────────────────────────────────────────────────────────────
#  modules/pca_dashboard.py  —  PCA Dashboard Module
#  Wraps pca_engine.PCAEngine + pca_dashboard.render_pca_dashboard()
#  v1.0.0
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st
from base import Dashboard

class PCADashboard(Dashboard):

    MANIFEST = {
        "id":       "pca_dashboard",
        "label":    "PCA Tool",
        "version":  "1.0.0",
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
        "session_keys": ["pca_selected_recipe_id"],
        "abilities": [
            "Create and manage PCA recipes",
            "Add food and disposable ingredient lines",
            "Calculate portion cost, EP cost, and cost %",
            "Compare cost % against goal",
            "Duplicate recipes",
            "Export PCA as JSON",
            "AI ingredient suggestions via Anthropic API",
        ],
        "permissions": {"min_role": "user"},
    }

    DOCS = {
        "summary": "Portion Cost Analysis — build recipes, calculate costs, compare to goals.",
        "usage": (
            "Navigate to PCA Tool. Select or create a recipe. "
            "Add ingredients from the inventory. "
            "Review calculated cost % vs goal. Use AI suggestions to optimize."
        ),
        "demo_ready": True,
        "notes": (
            "Wraps pca_engine.PCAEngine and pca_dashboard.render_pca_dashboard(). "
            "AI suggestions require ANTHROPIC_API_KEY in st.secrets. "
            "Recipes and recipe_ingredients tables must exist in Supabase — "
            "created by database.py create_tables()."
        ),
        "known_issues": [
            "recipes and recipe_ingredients tables not yet in database.py create_tables() — need migration.",
            "auth module dependency — using stub get_changed_by until auth is wired.",
        ],
        "changelog": [
            {"version": "1.0.0", "date": "2026-03-18", "note": "Initial SDOA module wrapper."},
        ],
    }

    def on_load(self) -> None:
        self._ensure_tables()

    def _ensure_tables(self):
        """Create recipes/recipe_ingredients tables if not present."""
        try:
            from database import get_conn
            with get_conn() as conn:
                cur = conn.cursor()
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
            st.warning(f"PCA table check: {exc}")

    def sidebar(self) -> None:
        with st.sidebar:
            st.markdown("**🧪 PCA Tool**")
            st.caption("Portion Cost Analysis")

    def render(self) -> None:
        try:
            from pca_dashboard import render_pca_dashboard
            render_pca_dashboard(db=self.db)
        except ImportError:
            # pca_dashboard.py has an auth dependency — render inline fallback
            self._render_inline()
        except Exception as exc:
            import traceback
            st.error(f"PCA Dashboard error: {exc}")
            st.code(traceback.format_exc())

    def _render_inline(self):
        """
        Inline PCA UI — used when pca_dashboard.py can't be imported
        (e.g. auth module missing). Fully functional, no auth dependency.
        """
        import pandas as pd
        from pca_engine import PCAEngine

        st.title("🧪 PCA Tool — Portion Cost Analysis")
        pca = PCAEngine(self.db)

        # ── Recipe selector + actions ──────────────────────────────────────
        recipes    = pca.get_all_recipes()
        recipe_map = {r["name"]: r["recipe_id"] for r in recipes}
        names      = sorted(recipe_map.keys())

        col1, col2 = st.columns([3, 1])
        with col1:
            selected_name = st.selectbox(
                "Recipe", ["— select or create —"] + names, key="pca_sel"
            )
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            create_new = st.button("➕ New Recipe", use_container_width=True)

        selected_id = recipe_map.get(selected_name)

        # ── Create new recipe ──────────────────────────────────────────────
        if create_new:
            with st.form("new_recipe_form"):
                st.subheader("Create New Recipe")
                c1, c2, c3 = st.columns(3)
                name          = c1.text_input("Recipe Name *")
                selling_price = c2.number_input("Selling Price $", value=0.0, format="%.2f")
                cost_pct_goal = c3.number_input("Cost % Goal", value=17.0, format="%.1f") / 100
                category      = st.selectbox("Category", ["Concessions", "Catering", "Other"])
                submitted     = st.form_submit_button("Create Recipe")
            if submitted and name:
                rid = pca.create_recipe(
                    name=name.strip(),
                    category=category,
                    selling_price=selling_price,
                    cost_pct_goal=cost_pct_goal,
                    updated_by="web_user",
                )
                if rid:
                    st.success(f"✅ Recipe '{name}' created!")
                    st.rerun()

        if not selected_id:
            st.info("Select a recipe above or create a new one.")
            return

        # ── PCA Calculation ────────────────────────────────────────────────
        result = pca.calculate_pca(selected_id)
        if not result:
            st.error("Could not calculate PCA for this recipe.")
            return

        recipe  = result["recipe"]
        metrics = result["metrics"]
        totals  = result["totals"]

        # ── Header metrics ─────────────────────────────────────────────────
        st.subheader(f"📊 {recipe['name']}")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Selling Price",  f"${metrics['selling_price']:.2f}")
        c2.metric("Cost / Portion", f"${totals['cost_per_portion']:.4f}")
        c3.metric("Actual Cost %",  f"{metrics['product_cost_pct']*100:.1f}%")
        c4.metric("Goal Cost %",    f"{metrics['cost_pct_goal']*100:.1f}%")
        status_delta = f"{metrics['pct_diff']*100:+.1f}%"
        c5.metric("vs Goal", status_delta,
                  delta_color="inverse" if metrics["over_goal"] else "normal")

        if metrics["over_goal"]:
            st.warning(f"⚠️ Over cost goal by {abs(metrics['pct_diff'])*100:.1f}%")
        else:
            st.success(f"✅ On target — {abs(metrics['pct_diff'])*100:.1f}% under goal")

        st.markdown("---")

        # ── Food ingredients ───────────────────────────────────────────────
        st.subheader("🍽️ Food Ingredients")
        if result["food_lines"]:
            food_df = pd.DataFrame([{
                "Item":       l.get("description", l.get("item_key", "")),
                "EP Amount":  l["ep_amount"],
                "Unit":       l["unit"],
                "Unit Cost":  f"${l['unit_cost']:.4f}",
                "EP Cost":    f"${l['ep_cost']:.4f}",
                "Vendor":     l.get("vendor", ""),
            } for l in result["food_lines"]])
            st.dataframe(food_df, use_container_width=True, hide_index=True)
            st.caption(f"Total food cost: ${totals['total_food_cost']:.4f}")
        else:
            st.info("No food ingredients added yet.")

        # ── Disposables ────────────────────────────────────────────────────
        if result["disposable_lines"]:
            st.subheader("📦 Disposables")
            disp_df = pd.DataFrame([{
                "Item":          l.get("description", l.get("item_key", "")),
                "EP Amount":     l["ep_amount"],
                "Unit":          l["unit"],
                "Cost/Portion":  f"${l.get('cost_per_portion', 0):.4f}",
            } for l in result["disposable_lines"]])
            st.dataframe(disp_df, use_container_width=True, hide_index=True)
            st.caption(f"Total disposable cost: ${totals['total_disposable_cost']:.4f}")

        st.markdown("---")

        # ── Add ingredient ─────────────────────────────────────────────────
        st.subheader("➕ Add Ingredient")
        all_items = self.db.get_all_items()
        if all_items:
            item_options = {
                f"{i['description']} ({i['pack_type']})": i["key"]
                for i in all_items
            }
            with st.form("add_ingredient_form"):
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                item_label = c1.selectbox("Item", list(item_options.keys()))
                ep_amount  = c2.number_input("EP Amount", value=1.0, format="%.4f")
                unit       = c3.selectbox("Unit", ["Each", "Ounce", "Pound", "Case", "Sleeve"])
                ing_type   = c4.selectbox("Type", ["food", "disposable"])
                add_btn    = st.form_submit_button("Add Ingredient")

            if add_btn:
                item_key = item_options[item_label]
                lid = pca.add_ingredient(
                    recipe_id=selected_id,
                    item_key=item_key,
                    ep_amount=ep_amount,
                    unit=unit,
                    ingredient_type=ing_type,
                )
                if lid:
                    st.success(f"✅ Added {item_label}")
                    st.rerun()

        # ── Recipe actions ─────────────────────────────────────────────────
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📋 Duplicate Recipe", use_container_width=True):
                new_name = f"{recipe['name']} (Copy)"
                pca.duplicate_recipe(selected_id, new_name=new_name)
                st.success(f"Duplicated as '{new_name}'")
                st.rerun()
        with col2:
            import json
            export = pca.export_pca_dict(selected_id)
            st.download_button(
                "⬇️ Export JSON",
                data=json.dumps(export, indent=2, default=str),
                file_name=f"pca_{selected_id}.json",
                mime="application/json",
                use_container_width=True,
            )
        with col3:
            if st.button("🗑️ Archive Recipe", use_container_width=True):
                pca.delete_recipe(selected_id, soft=True)
                st.success("Recipe archived.")
                st.rerun()

# ── end of PCADashboard ───────────────────────────────────────────────────────
