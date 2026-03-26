# UHA IMS — Future UI Improvements
# Items that require React + FastAPI migration to implement properly.
# Each item includes a detailed plan for post-migration implementation.
# Reference: Engineering Build Spec v1 (2026-03-25)
# Status: [ ] planned  [~] in design  [x] done

---

## SHELL & NAVIGATION

### [ ] U-001 — Dynamic Tiling Engine
**Spec Ref:** Section 8
**Description:** Snap-to-grid window management. Drag dashboard panels into defined zones.
**React Plan:**
- Use `react-grid-layout` or build a custom snap engine with CSS Grid
- Snap zones: 1–6 horizontal columns, 1–10 vertical rows
- Each dashboard module renders as a draggable `<TilePane>` component
- Tile state (position, size, docked/floating) persists to user profile via API
- Snap preview ghost shown on drag near zone boundaries

### [ ] U-002 — Multi-Window Management
**Spec Ref:** Section 3.1 (New Window), Section 8
**Description:** Move all UHA IMS tabs to a new browser window. Track window state.
**React Plan:**
- Use `window.open()` with `postMessage` cross-window communication
- Central window registry in a SharedWorker or BroadcastChannel API
- "New Window" detaches active tab group into new window with same auth session
- Window state synced via server profile on close

### [ ] U-003 — Tab Stacking & Minimize to Tab Bar
**Spec Ref:** Section 8
**Description:** Stack multiple dashboards as tabs in a single pane. Minimize tile to floating tab bar.
**React Plan:**
- Tab bar component with drag-to-reorder (react-dnd or @dnd-kit)
- Max 10 tabs per pane (enforced in TabManager state)
- Minimize: tile animates to 40px-tall strip at bottom of workspace
- Restore on click
- Overflow: tabs collapse into a "+N more" dropdown

### [ ] U-004 — Right-Click Context Menu
**Spec Ref:** Section 8 (Right-Click Menu)
**Description:** Right-click on tile or tab bar to access split, grid, minimize, send-to-comparison actions.
**React Plan:**
- Custom `<ContextMenu>` component using Radix UI Popover or Floating UI
- Binds to `onContextMenu` on tile headers and tab items
- Menu items: Split tabs to grid | Grid all windows | Minimize all | Send to Comparison
- Actions dispatch to TilingEngine context

### [ ] U-005 — Full Top Nav with Real Hotkeys
**Spec Ref:** Section 3
**Description:** Native keyboard shortcut system (not JS injection). Full menu with submenus.
**React Plan:**
- Use `@radix-ui/react-menubar` for accessible, keyboard-navigable menu bar
- Hotkeys bound via `useHotkeys` (react-hotkeys-hook)
- Global hotkeys: CTRL+P (print), ALT+W (new window), ALT+X (exit window)
- Per-menu hotkeys: single letter while menu is open
- Hotkey hints rendered as `<kbd>` elements in menu items

### [ ] U-006 — Left Sidebar — Narrow/Wide with Icon Mode
**Spec Ref:** Section 4
**Description:** Sidebar collapses to 60px icon-only strip. Hover expands temporarily.
**React Plan:**
- CSS transition on sidebar `width`: 240px ↔ 60px
- Icon buttons show `<Tooltip>` with label when narrow
- Persistent state in localStorage + user profile
- Hover: expand with 200ms delay, collapse on mouse leave with 400ms delay
- Active dashboard item highlighted with accent color + left border

### [ ] U-007 — Comparison Pane
**Spec Ref:** Section 4.2, Section 8
**Description:** Side-by-side comparison of up to 5 items or PCA sheets.
**React Plan:**
- Fixed right-side panel (resizable) or bottom tray (toggleable)
- Items dragged or "sent to comparison" populate slots
- Each slot renders a miniaturized item detail card
- Diff highlighting: fields that differ across comparison items shown in amber
- Max 5 slots (enforced in ComparisonPane state)
- "Clear all" and per-slot remove (×) buttons

---

## DESIGN SYSTEM

### [ ] U-008 — Full Design Token System
**Spec Ref:** Section 2.1
**Description:** CSS custom properties for all colors, typography, spacing, border-radius, shadow.
**React Plan:**
- Define tokens in `tokens.css` as `--color-primary`, `--space-4`, `--radius-md`, etc.
- All components reference tokens, never hardcoded values
- Token sets: Light theme, Dark theme, UHA Blue theme, High Contrast theme
- Theme switched by swapping a `data-theme` attribute on `<html>`
- Token values documented in a `/style-guide` dev-only route

### [ ] U-009 — Component Library with Variants & States
**Spec Ref:** Section 2.3
**Description:** Figma-spec component names. All components support variants, states, auto-layout.
**React Plan:**
- Build on shadcn/ui (Radix UI primitives + Tailwind CSS) for accessible base
- Override with UHA design tokens
- Components: Button (primary/secondary/ghost/danger), Badge, Card, DataTable,
  MetricTile, TabBar, Sidebar, MenuBar, Dialog, Toast, Tooltip, EmptyState
- Storybook for component documentation and visual regression testing

### [ ] U-010 — Icon Set (Feather / Fluent)
**Spec Ref:** Section 2.2
**Description:** Consistent icon set across all UI surfaces.
**React Plan:**
- Use `lucide-react` (Feather-compatible, actively maintained)
- All icon usages via `<Icon name="..." size={16} />` wrapper component
- Never inline SVG or use emoji as icons in production UI
- Icon mapping table from spec applied during component build

### [ ] U-011 — Animation & Transition System
**Spec Ref:** General UX quality
**Description:** Consistent motion for panel open/close, tab switch, data load, drag-and-drop.
**React Plan:**
- Framer Motion for all layout animations and presence transitions
- Timing scale: 100ms (micro), 200ms (standard), 350ms (layout)
- Reduced motion: respect `prefers-reduced-motion` media query
- Loading states: skeleton screens (not spinners) for data tables

---

## PERSISTENCE & STATE

### [ ] U-012 — Local Storage + Server Profile Sync
**Spec Ref:** Section 7
**Description:** All persistent view state saved to localStorage immediately; synced to server on change.
**React Plan:**
- Zustand store for all workspace state (layout, tabs, filters, theme, open recipes)
- `zustand/middleware/persist` for automatic localStorage sync
- On auth: fetch server profile, merge with localStorage (server wins for conflicts)
- On change: debounced `PUT /api/profile/workspace` saves to `user_preferences` DB column
- On logout: clear localStorage

### [ ] U-013 — Persistent Filters & Sort
**Spec Ref:** Section 7
**Description:** Inventory filters and sort order persist across navigation.
**React Plan:**
- Filter/sort state lives in Zustand, namespaced per dashboard (`inventory.filters`, `pca.filters`)
- URL query params mirror filter state for shareability (`?gl=411048&vendor=sysco`)
- Filter chips rendered above table — each chip has an × to clear that filter
- "Clear all" button visible when any filter is active

---

## DASHBOARD ENHANCEMENTS

### [ ] U-014 — Advanced Item View Customization
**Spec Ref:** Section 5.3
**Description:** Admin sets default column config; users can customize per-role.
**React Plan:**
- Column config stored in server profile: `{ visible: [], order: [], widths: {} }`
- Drag-to-reorder columns in a settings panel (react-dnd on column chips)
- Each column: visible toggle, sortable toggle, filterable toggle
- Admin sets "default" config; users can override unless `locked: true`
- Admin can "push to all users" to override everyone's column config

### [ ] U-015 — Full PCA AI Helper Interface
**Spec Ref:** Section 4.3
**Description:** Conversational AI panel for PCA cost optimization. Context-aware of active recipe.
**React Plan:**
- Right sideboard panel: `<AIHelper>` component
- Chat-style interface (message thread) using react-virtuoso for long histories
- Pre-built prompt chips: "Reduce cost by 10%", "Find cheaper protein", "Explain this variance"
- AI has full context: current recipe, ingredient list, cost %, available inventory
- Actions: AI suggests swap → user clicks "Apply" → ingredient line updated via API
- Streaming responses via Server-Sent Events (FastAPI StreamingResponse)
- History persisted per recipe in `ai_conversations` DB table

### [ ] U-016 — Import Detection Tool UI
**Spec Ref:** Section 4.4
**Description:** Visual detection tool showing format confidence scores and auto-switching interface.
**React Plan:**
- After file drop: animated detection sequence showing format scores as bar chart
- Confident detection: interface auto-switches with green badge "Detected: FMT_B (92%)"
- Uncertain detection: user shown format picker with confidence scores
- Override always available via dropdown
- Detection result persists as part of import job metadata

### [ ] U-017 — Drag-and-Drop Import
**Spec Ref:** Section 4.4
**Description:** Full drag-and-drop file zone with multi-file queue.
**React Plan:**
- Full-page drop zone (activates when dragging file over window)
- File queue: list of pending files with progress bars
- Each file processed in sequence, results shown inline
- Failed files shown with error badge and retry button

### [ ] U-018 — Full Comparison Pane for Inventory
**Spec Ref:** Section 4.2
**Description:** Select up to 10 items, open 10 detail tabs, send any to comparison pane.
**React Plan:**
- Checkbox column in inventory list (max 10 checked)
- "Compare selected" button opens comparison pane with one column per item
- Diff mode: highlight cells where values differ across items
- Tab stack: each selected item also gets a detail tab in the tiling engine
- Sync scroll: scrolling one comparison column scrolls all

---

## AUTH & SECURITY

### [ ] U-019 — Role-Based Feature Access (visual enforcement)
**Spec Ref:** Section 6
**Description:** All feature-gated UI elements visually disabled (not hidden) for unauthorized roles.
**React Plan:**
- `<FeatureGate feature="..." minRole="admin">` wrapper component
- If role insufficient: renders component with `disabled` + `<Tooltip>Admin only</Tooltip>`
- Admin can toggle features per user or per role group in App Management
- Feature flag config loaded from server on auth, cached in Zustand

### [ ] U-020 — Override User Settings (Admin)
**Spec Ref:** Section 6
**Description:** Admin can see and override any user's customization settings.
**React Plan:**
- In App Management → Users: "View as user" button loads their profile in preview mode
- "Override" button copies admin's current config to selected user
- "Push to all" broadcasts current admin config to all users with specified role
- Audit log: all admin overrides recorded with timestamp + admin username

---

## DIALOGS & SYSTEM UI

### [ ] U-021 — Full Dialog System
**Spec Ref:** Section 11
**Description:** Standardized dialogs for all destructive/important actions.
**React Plan:**
- `<Dialog>` built on Radix UI Dialog primitive
- Dialog types: Print | Share | Export | UnsavedChanges | DeleteConfirm |
  ResetToAdminDefaults | SaveToProfile | OverrideUserSettings | CloseWindow | RestoreLayout
- Each dialog has: title, body copy (from spec), primary CTA, secondary CTA, cancel
- Print dialog: preview pane + printer selection
- Share dialog: copy link button + access level selector
- Export dialog: format selector (Excel/CSV/PDF) + scope selector (current view/full inventory)

### [ ] U-022 — Toast Notification System
**Spec Ref:** General UX
**Description:** Non-blocking success/error/info toasts replacing st.success/st.error.
**React Plan:**
- Use `sonner` or `react-hot-toast`
- Position: bottom-right
- Auto-dismiss: 4s (success), 8s (error), 6s (warning)
- Actions: undo button on destructive toasts (fires within dismiss window)
- Max 3 visible at once; older ones pushed off stack

### [ ] U-023 — Tooltip System (full library)
**Spec Ref:** Section 9
**Description:** Action-oriented, role-aware, context-aware tooltips on all interactive elements.
**React Plan:**
- `<Tooltip>` built on Radix UI Tooltip primitive
- Tooltip content from centralized `tooltips.ts` constant file (spec library)
- Role-aware: different copy for Admin vs User (e.g., "Edit item" vs "View only — contact admin")
- Context-aware: tooltip content changes based on item state (e.g., "Locked by import override")
- Delay: 400ms show, 0ms hide

---

*Last updated: 2026-03-25*
*Items planned: 23*
*Items completed: 0*
*Note: All items in this list require React + FastAPI migration.*
*See FUNCTION_LIST.md for items achievable in the current Streamlit stack.*
