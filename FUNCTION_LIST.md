# UHA IMS — Function Fixes & Improvements
# Streamlit-achievable items only. Each item includes a proposed solution.
# Update this file as items are completed or discovered.
# Status: [ ] pending  [x] done  [~] in progress  [!] blocked

---

## CRITICAL / HIGH PRIORITY

### [x] F-001 — AI Sidebar / AI Helper Panel
**Area:** PCA Dashboard, Global
**Problem:** `generate_ai_suggestions()` in pca_engine.py is wired to real Anthropic SDK
but the PCA dashboard UI has no way to trigger it or display results.
**Proposed Solution:**
- Add an "AI Helper" expander or st.sidebar section in pca_dashboard.py
- Wire a "Suggest Alternatives" button that calls `engine.generate_ai_suggestions(recipe_id)`
- Display results as a styled dataframe with ingredient, alternate, cost delta, new cost %
- Add `ANTHROPIC_API_KEY` read from `st.secrets` (fallback to env var — already in code)
- Gate behind `auth.is_editor()` check

### [x] F-002 — Import Variance Report
**Area:** Import Dashboard
**Problem:** After import commit, there is no variance summary showing what changed vs prior state.
**Proposed Solution:**
- In `import_dashboard.py`, after `execute_import()` succeeds, query `item_history`
  for the job's `source_document` to get all field changes in that batch
- Render a collapsible variance table: item key | field | old value | new value | delta
- Add a cost-delta summary metric: total cost impact of this import

### [x] F-003 — User Override During Import
**Area:** Import Dashboard
**Problem:** No mechanism for user to override a flagged/ambiguous row before committing.
**Proposed Solution:**
- After `analyze_import()`, render flagged rows in an editable `st.data_editor`
- Allow user to correct description, pack_type, cost, or mark as "skip"
- Pass corrected rows back into `execute_import()` via the existing `analysis` dict

### [x] F-004 — PCA AI Helper UI
**Area:** PCA Dashboard
**Problem:** `pca_engine._call_anthropic()` is wired (F-001 above) but pca_dashboard.py
has no UI surface for it.
**Proposed Solution:**
- Add "💡 AI Suggestions" button to PCA cost summary section
- On click: call `engine.generate_ai_suggestions(recipe_id, api_key=st.secrets.get("ANTHROPIC_API_KEY"))`
- Show spinner while waiting
- Display results in expander: one row per suggestion with swap button
- Swap button calls `engine.update_ingredient()` to apply the substitution

### [x] F-005 — PCA Sheet Tabs (multi-recipe workspace)
**Area:** PCA Dashboard
**Problem:** Only one recipe can be active at a time.
**Proposed Solution:**
- Use `st.tabs()` to support up to 5 open recipes simultaneously
- Store open recipe IDs in session state: `pca_open_recipes: List[int]`
- Each tab renders the full PCA view for its recipe_id
- Add "Open in new tab" button on recipe list rows
- Add close (×) affordance via a session state pop + st.rerun()

### [x] F-006 — Import Reporting Dashboard
**Area:** New module
**Problem:** No aggregate reporting across import jobs exists.
**Proposed Solution:**
- Create `modules/import_reporting_dashboard.py` (SDOA module, page_key: "import_reporting")
- Pull from `import_jobs` table via `db.get_recent_jobs(limit=200)`
- Metrics: total imports, rows processed, items added, items updated, error rate
- Column chooser: st.multiselect to toggle visible columns
- Mode selector: by job / by date / by source file
- Filter by job_type (invoice, count, db_import)

### [x] F-007 — Transfer Dashboard — commit to DB
**Area:** Transfer Dashboard
**Problem:** transfer_dashboard.py collects transfer data but has no DB write path.
**Proposed Solution:**
- Add `inventory_transactions` table to database.py (if not exists):
  `transaction_id, from_cc, to_cc, item_key, qty, unit_cost, total_value, transferred_by, transfer_date, notes`
- Add `record_transfer()` method to InventoryDatabase
- Wire "Commit Transfer" button in transfer_dashboard.py
- Update quantity_on_hand on both source and destination cost center DBs

---

## MEDIUM PRIORITY

### [x] F-008 — FMT_D Known Discrepancy (20oz Dasani)
**Area:** count_importer.py
**Problem:** One known math discrepancy on 20oz Dasani Bottled Water in FMT_D slash-delimited format.
**Proposed Solution:**
- Add the specific item to a test case
- Trace through `_verify()` and `_qty2()` / `_price2()` for FMT_D rows
- Likely a conv_ratio mismatch — check if the slash-delimited price cell
  is case price vs each price and whether the pack_type conv is being applied twice

### [ ] F-009 — Sideboard Customization (per-user column/widget visibility)
**Area:** App Management Dashboard
**Problem:** No per-user control over which sidebar widgets are shown or pinned.
**Proposed Solution:**
- Add `user_preferences` JSONB column to `users` table (or a new `user_prefs` table)
- Store: `{ sidebar_pinned: [], sidebar_hidden: [], sidebar_order: [] }`
- Add "Customize Sidebar" section in App Management → User Components
- Admin can set defaults; users can override unless locked
- `render_sidebar()` in app.py reads preferences and filters/reorders accordingly

### [ ] F-010 — Item View Customization (column visibility + sort preferences)
**Area:** Inventory Browser, Database Dashboard
**Problem:** Column set is hardcoded in every dashboard module.
**Proposed Solution:**
- Store column prefs in `user_preferences`: `{ inventory_columns: [], inventory_sort: "" }`
- Add "Customize Columns" button (gear icon) above inventory list
- Renders st.multiselect of available columns; selection persists to DB
- On load, filter display_cols to user preference intersection with available columns

### [x] F-011 — App Management Dashboard (new SDOA module)
**Area:** New module
**Problem:** Admin settings are buried in a Settings page (app.py `_page_settings`).
Admin components are not a proper SDOA module.
**Proposed Solution:**
- Create `modules/app_management_dashboard.py` (page_key: "app_management")
- Sections (tabs): Users | Features | Sideboard | Item View | Import Reporting
- Migrate existing `_page_settings()` content here
- Add admin-only gate in MANIFEST: `"permissions": {"min_role": "admin"}`
- Remove `_page_settings()` from app.py, add "app_management" to dispatch

### [x] F-012 — Recent Items Section (Database Dashboard)
**Area:** Database Dashboard
**Problem:** "Recently Updated" shows items sorted by last_updated but has no
"recently viewed" tracking (items you personally clicked on).
**Proposed Solution:**
- Add `recent_views` to session state: a deque of last 10 item keys viewed
- Update on every item detail load in inventory_browser.py
- Render a "Recently Viewed" section in dashboard_module.py using the session deque
- Optionally persist to `user_preferences` for cross-session memory

### [x] F-013 — Item List Toggle (show/hide list, preserve filters)
**Area:** Inventory Browser
**Problem:** No way to hide the item list to expand the detail panel.
**Proposed Solution:**
- Add a toggle button (collapse icon) above the item list in inventory_browser.py
- Store `show_list: bool` in module session state
- When False: render `st.columns([0, 1])` (zero-width left, full-width right)
- Filters/sort state preserved in session state regardless of toggle

### [x] F-014 — Database Picker (multi-DB switching UX)
**Area:** App shell / Sidebar
**Problem:** DB switcher is functional but has no visual feedback about which
cost center is active or its connection health.
**Proposed Solution:**
- Show active cost center icon + label prominently at top of sidebar
- Add a green/red connection status dot (try a lightweight `db.count_items()` ping)
- Cache ping result for 60 seconds to avoid hammering the DB

### [ ] F-015 — Print / Export from active dashboard
**Area:** Top Nav → File Menu
**Problem:** Print and Export menu items are declared in ui_skeleton.py but
are context-unaware (no active-dashboard routing).
**Proposed Solution:**
- Add `export()` abstract method to `Dashboard` base class (optional override, default: None)
- Modules that support export implement it (inventory_browser, pca_dashboard, etc.)
- Top nav Export triggers `registry.get_active().export()` if implemented
- Print → `st.components.html('<script>window.print()</script>')` or js_action already in MenuItem

### [x] F-016 — Zoom / Fullscreen Menu
**Area:** Top Nav → View Menu
**Problem:** Zoom and Fullscreen menu items are declared but not wired.
**Proposed Solution:**
- Fullscreen → `js_action` already supports `onclick` — inject `document.documentElement.requestFullscreen()`
- Zoom → submenu with 75% / 100% / 125% / 150% options
  → inject `document.body.style.zoom = '1.25'` via `st.components.v1.html`
- Store zoom level in session state so it re-applies on rerun

### [x] F-017 — Toggle Sidebar (narrow/wide)
**Area:** Top Nav → View Menu
**Problem:** Sidebar toggle is declared in menu but has no working implementation.
**Proposed Solution:**
- Streamlit has no native sidebar collapse API but `st.set_page_config` can set `initial_sidebar_state`
- Inject CSS to set `section[data-testid="stSidebar"]` width to 60px when collapsed
- Show only icons (no labels) when narrow; full labels when wide
- Store `sidebar_collapsed: bool` in session state

### [x] F-018 — UI Styling (theme selector)
**Area:** App Management → UI Styling
**Problem:** No theme switching exists beyond Streamlit's built-in light/dark.
**Proposed Solution:**
- Define 3-4 CSS variable sets (Light, Dark, UHA Blue, High Contrast)
- Inject via `st.components.v1.html` with `<style>:root { --primary: ... }</style>`
- Store selection in session state + user_preferences
- Admin can set org-wide default; users can override

### [x] F-019 — ANTHROPIC_API_KEY from st.secrets
**Area:** pca_engine.py
**Problem:** `generate_ai_suggestions()` reads `os.environ.get("ANTHROPIC_API_KEY")`
but Streamlit deployments use st.secrets, not env vars.
**Proposed Solution:**
- In `pca_dashboard.py`, pass key as:
  ```python
  key = st.secrets.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
  engine.generate_ai_suggestions(recipe_id, api_key=key)
  ```
- No change needed to pca_engine.py (api_key param already exists)

### [ ] F-020 — Split count_importer.py
**Area:** count_importer.py (~1400 lines)
**Problem:** All four format parsers (FMT_A/B/C/D) in a single file — hard to maintain.
**Proposed Solution:**
- Extract each format parser into `count_formats/fmt_a.py`, `fmt_b.py`, `fmt_c.py`, `fmt_d.py`
- Each exposes a `parse(rows) -> List[CountRecord]` function
- `count_importer.py` becomes a thin dispatcher: detects format, imports correct module, calls parse()
- `FormatDetector`, `CountRecord`, `ParseResult` dataclasses stay in count_importer.py
- Zero behavior change — pure refactor

### [x] F-021 — Transfer Dashboard receive-side logic
**Area:** transfer_dashboard.py
**Problem:** Transfer dashboard lets you pick source/destination and items,
but has no "receive" workflow for the destination cost center.
**Proposed Solution:**
- Add "Incoming Transfers" tab to transfer_dashboard.py
- Query `inventory_transactions` for transfers TO current cost center with status "pending"
- "Accept" button: adds qty to destination DB, marks transaction "completed"
- "Reject" button: marks transaction "rejected", sends note back

### [x] F-022 — Empty States (all dashboards)
**Area:** All modules
**Problem:** Empty states are inconsistent — some show `st.info()`, some show nothing.
**Proposed Solution:**
- Define a shared `render_empty_state(icon, title, message, action_label=None, action_key=None)`
  helper in base.py or a new `ui_helpers.py`
- Replace ad-hoc `st.info()` calls across all modules with this helper
- Ensures consistent look, icon, and CTA across the app

### [x] F-023 — Unsaved Changes Warning (PCA)
**Area:** PCA Dashboard
**Problem:** Navigating away from a PCA recipe with unsaved edits gives no warning.
**Proposed Solution:**
- Track `pca_dirty: bool` in module session state whenever a field is edited
- On page change (detected via query param shift), if dirty: show `st.warning` with
  "You have unsaved changes — Save or Discard?" before allowing navigation
- Streamlit cannot intercept browser navigation, so this only works for in-app nav

### [x] F-024 — Delete Confirmation Dialog
**Area:** Inventory Browser, PCA Dashboard
**Problem:** Delete/archive actions execute immediately with no confirmation step.
**Proposed Solution:**
- Add `confirm_delete: str | None` to session state (stores item key pending deletion)
- On first "Delete" click: set `confirm_delete = key`, rerun
- On rerender: show `st.warning("Delete X? This cannot be undone.")` with Confirm/Cancel
- Confirm executes delete, Cancel clears `confirm_delete`

### [ ] F-025 — Import Mode Auto-Switcher
**Area:** Import Dashboard
**Problem:** Spec requires detection tool to auto-switch import interface
(invoice vs count vs transfer vs receipt). Currently only invoice is supported.
**Proposed Solution:**
- Add `detect_import_type(filename, content) -> str` to importer.py
  Rules: filename contains "count" → count, "transfer" → transfer, else → invoice
- On file upload in import_dashboard.py, call detector and `st.tabs()` to the correct tab
- Show detection result + confidence to user with override selector

### [x] F-032 — Tax Adjustment Factor in PCA cost % calculation
**Area:** pca_engine.py
**Problem:** `calc_product_cost_pct()` divided cost by raw selling price.
Texas selling prices include 8.25% sales tax, so the denominator must be the
pre-tax price. Without this, every PCA cost % is understated by ~8.25%.
**Proposed Solution:**
- Add `TAX_ADJUSTMENT_FACTOR = 1.0825` constant
- Change formula to `cost_per_portion / (selling_price / TAX_ADJUSTMENT_FACTOR)`
**Status: DONE — implemented in pca_engine.py**

### [x] F-031 — Port count_overrides / Override Rule Manager
**Area:** count_importer.py, database.py, new module
**Problem:** The v3.0.x codebase had `count_overrides` and `count_override_settings` tables
for items with wrong pack ratios (MOG tray items). This feature was dropped in the SDOA
migration. Without it, tray item counts are silently wrong.
Three known required rules:
```
1LB TRAY||1/1000  →  multiply count by 12
2LB TRAY||1/1000  →  multiply count by 6
3LB TRAY||1/500   →  multiply count by 24
```
**Proposed Solution:**
- Add `count_overrides` table: `item_key, multiplier, reason, created_by, active`
- Add `count_override_settings` table: `setting_key, value` (e.g. `enabled=true`)
- In `count_importer.py`, after parsing each row, check if `item_key` has an active override
  and apply multiplier to quantity before returning the `CountRecord`
- Add a management UI in a new `overrides_dashboard.py` SDOA module: list rules, add, toggle active

### [x] F-033 — Per-Field Override Lock UI
**Area:** Inventory Browser / Item Detail
**Problem:** `database.py` fully supports per-field override locking (`override_pack_type`,
`override_yield`, `override_conv_ratio`, `override_vendor`, `override_gl`), but there is
no UI surface to set or clear individual field locks. Users currently cannot lock yield
while letting price update freely — the override system is invisible to them.
**Proposed Solution:**
- In item detail view, add a lock icon toggle next to each overridable field
- Lock icon = override set, unlock icon = follows incoming data
- On lock: call `db.set_override(key, field, value)` with the current field value
- On unlock: call `db.clear_override(key, field)`
- Show locked fields with distinct background color to make override state obvious

### [x] F-034 — recipe_alternates Cache Table for AI Suggestions
**Area:** pca_engine.py, database.py
**Problem:** Every call to `generate_ai_suggestions()` hits the Anthropic API. There is
no caching, so the same recipe generates redundant API calls and costs money.
**Proposed Solution:**
- Add `recipe_alternates` table: `recipe_id, ingredient_key, alternate_key,
  alternate_description, cost_delta, estimated_pct, suggested_at, accepted, rejected`
- In `generate_ai_suggestions()`, check cache first; return cached results if they exist
  and are < 7 days old
- On user "Apply" action in the AI suggestions UI, mark the row `accepted=true`
  and call `update_ingredient()` to apply the substitution

### [x] F-035 — Import Confidence Scoring (0.0–1.0)
**Area:** count_importer.py, importer.py
**Problem:** The import engine treats every match as binary (matched / not matched).
There is no way to distinguish a perfect exact match from a fuzzy guess, so the UI
cannot surface low-confidence rows for operator review without flagging everything.
**Proposed Solution:**
- Add `confidence: float` field to `CountRecord` and import row dicts
- Weighted scoring model:
  - Exact key match: 1.0
  - Exact description match (normalized): +0.30
  - Fuzzy description match ≥ 85%: +0.20
  - Vendor match: +0.10
  - All required fields present: +0.10
- Items with confidence < 0.85 → `status = "review"` in the import preview
- Display confidence as a colored badge in the import variance table

### [x] F-036 — Price Volatility Check on Import
**Area:** importer.py, import_dashboard.py
**Problem:** No check for abnormal price swings during import. A $54 item that arrives
as $540 (common OCR error) imports silently, corrupting PCA costs.
**Proposed Solution:**
- In `importer.py`, after matching an existing item, compute:
  `abs((new_cost - old_cost) / old_cost) > 0.20`
- If true, add the row to a `price_alerts` list in the analysis object
- In `import_dashboard.py`, render a yellow warning section at the top of the
  import preview: "⚠️ X items have price changes > 20% — review before committing"
- Still allow import — just surfaces the alert for operator judgment

### [x] F-037 — POS ↔ Inventory Item Mapping Table
**Area:** database.py, new module
**Problem:** `compare product lists.txt` contains a direct mapping of POS menu item names
to inventory item keys. This reconciliation is done manually today. Without a formal
mapping, the "Chargeable Principle" — verifying counts against POS sales 1:1 — cannot
be automated.
**Proposed Solution:**
- Add `pos_item_map` table: `pos_item_name, inventory_key, is_chargeable, sort_order, notes`
- Seed from `compare product lists.txt` — asterisked items are chargeable, tilde = inventory name
- Add a management UI tab to the Import Dashboard or a new `pos_map_dashboard.py` module
- Use this table in the count reconciliation logic to auto-match count rows to POS line items

---

## LOW PRIORITY / POLISH

### [x] F-026 — Version Syncer: show per-module changelog on hover
**Area:** Sidebar version shield
**Problem:** Version panel shows live vs repo but not what changed.
**Proposed Solution:** Fetch changelog from repo MANIFEST and render in expander on mismatch.

### [x] F-027 — Search history / saved searches
**Area:** Inventory Browser, History Dashboard
**Problem:** Search field resets on every rerun.
**Proposed Solution:** Store last 5 searches in session state, render as clickable chips above search input.

### [x] F-028 — Keyboard shortcuts reference page
**Area:** Help Menu → Help Center
**Problem:** Hotkeys are defined in ui_skeleton.py but never shown to users.
**Proposed Solution:** Auto-generate a hotkey reference table from `MenuItem.shortcut` values
and render at `?page=help`.

### [x] F-029 — GL Dashboard: manual GL mapping entry
**Area:** GL Dashboard
**Problem:** GL codes can only be loaded from OneDrive or auto-assigned.
No way to manually add or edit a GL mapping.
**Proposed Solution:** Add a form (code, name, description) above the summary table
with Add / Update / Delete buttons wired to `gl_manager.add_gl_mapping()`.

### [x] F-038 — 3-State Sidebar (full → narrow → hidden)
**Area:** App shell / Sidebar
**Problem:** Current sidebar toggle only shows full or completely hidden. No intermediate
"icon-only" narrow mode for working on smaller screens without losing navigation context.
**Proposed Solution:**
- Track `sidebar_state: "full" | "narrow" | "hidden"` in session state (cycles on each toggle click)
- CSS injection via `st.components.v1.html` into parent DOM:
  - **Full:** `section[data-testid="stSidebar"] { width: 240px; }` (default)
  - **Narrow:** `width: 60px` — hide all text via `overflow:hidden; white-space:nowrap`, show only emojis/icons
  - **Hidden:** click Streamlit's native collapse button (already wired in F-017)
- Update "Toggle Sidebar" View menu item to cycle through all three states
- Persist state across reruns via session state; reset to full on page switch

### [ ] F-030 — Inventory export: filtered subset
**Area:** Export Dashboard
**Problem:** Export always dumps the full inventory. No way to export a filtered subset.
**Proposed Solution:**
- Add filter controls (GL code, vendor, status, cost center) above download buttons
- Apply filters to the DataFrame before passing to ExcelWriter/to_csv

### [x] F-039 — History Dashboard Redesign
**Area:** modules/history_dashboard.py
**Problem:** Current history view is a blank screen with no entries. Needs a fully functional
sortable/filterable list that is never empty, with popup detail view for each entry.
**Proposed Solution:**
- Load all history entries on open (no blank state)
- Sortable by: date, item, type of change, user, value impact
- Filterable by: time range, group (item/supplier/brand/GL), change type, cost effect
- Searchable by item name, user, notes
- Selecting a row opens a modal/popup covering most of the list showing:
  field-level diff, who changed it, when, and what triggered it (import job, manual edit, etc.)

### [ ] F-040 — Importer: Recently Imported Section
**Area:** modules/import_dashboard.py
**Problem:** No visibility into what was recently imported — user must check history dashboard.
**Proposed Solution:**
- Add a "Recently Imported" section at the bottom (or collapsible expander) showing
  last 5–10 import jobs: filename, date, items added/updated, errors, cost delta
- Clicking a job row shows the full variance report for that import
- Pull from `import_jobs` table (already exists)

### [x] F-041 — Count Module Complete Retool
**Area:** modules/count_entry_dashboard.py, modules/count_dashboard.py
**Problem:** Current count interface is inadequate. Needs three distinct workflows:
Print Count Sheets, Enter Manual Counts, Scan Count Sheets (OCR).
**Proposed Solution:**
- Rename module page to "Count" (done); combine count_entry + count_dashboard into one module
- **Print Count Sheets tab:**
  - Show list of stands/locations (by cost center); toggle-select which to include
  - Options: portrait/landscape, sort order, items per sheet, column selector
    (description, unit, value/unit, total cost, last count, case entry, unit entry)
  - Columns selectable and re-orderable
  - Generated sheet encodes config as QR/barcode for Scan tab auto-recognition
- **Enter Manual Counts tab:**
  - Same layout options as Print tab so user can match their printed sheet
  - Ten-key friendly: # → Enter → # → Enter → Enter (skip) → etc.
  - GL-grouped rows with case and unit entry points side by side
- **Scan Count Sheets tab:**
  - File upload (drag & drop) + camera/scanner interface
  - OCR reads sheet, auto-populates count data
  - If QR/barcode present on sheet: auto-applies the original print configuration
    (eliminates mis-reads from column-order mismatches)
  - Preview panel shows OCR result before commit

### [ ] F-042 — Combine App Management + Settings
**Area:** modules/app_management_dashboard.py, app.py (_page_settings)
**Problem:** App Management and Settings are separate pages but serve overlapping purposes.
Users find it confusing to navigate two admin areas.
**Proposed Solution:**
- Merge Settings (feature toggles, user management) into App Management as additional tabs
- App Management becomes the single admin hub: Users | Features | Appearance | DB Ops | About
- Remove standalone Settings page from sidebar and nav
- Keep ?page=settings as a redirect alias to ?page=app_management for backward compat

### [ ] F-043 — Audit Count Overrides + POS Mapping Modules
**Area:** modules/overrides_dashboard.py, modules/pos_map_dashboard.py
**Problem:** Both modules exist but are unclear in purpose/value to new users.
Count Overrides manages tray-item pack-ratio correction rules.
POS Mapping manages POS menu item ↔ inventory item reconciliation.
**Proposed Solution:**
- Add clear help text / onboarding to each module explaining what it does and why
- Count Overrides: surface the 3 known required tray rules (1LB/2LB/3LB), make it obvious
  these are active and being applied during count imports
- POS Mapping: show a sample of mapped vs unmapped items so purpose is immediately clear
- Evaluate whether either should be folded into another module (e.g., overrides into Count,
  POS map into Inventory Management)

---

*Last updated: 2026-03-28*
*Items completed: 32 (F-001, F-002, F-003, F-004, F-005, F-006, F-007, F-008, F-011, F-012, F-013, F-014, F-016, F-017, F-019, F-021, F-022, F-023, F-024, F-026, F-027, F-028, F-029, F-030, F-031, F-032, F-033, F-034, F-035, F-036, F-037, F-038)*
*Items pending: 11*
