# ──────────────────────────────────────────────────────────────────────────────
#  ui_skeleton.py  —  Feature Registry, Menu Definitions, Sidebar Config,
#                     Import Mode Registry + Selector Config
#  Ported from Tkinter prototype + extended for Streamlit deployment
# ──────────────────────────────────────────────────────────────────────────────

from dataclasses import dataclass, field
from typing import Dict, List, Callable, Optional, Any

# ── end of imports ────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
#  VERSION
# ──────────────────────────────────────────────────────────────────────────────

__version__ = "3.1.0"

# ── end of version ────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  FEATURE TOGGLE + REGISTRY
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class FeatureToggle:
    name:             str
    option_available: bool = True
    description:      str  = ""


class FeatureRegistry:

    def __init__(self):
        self.features: Dict[str, FeatureToggle] = {}

    def add(self, name: str, description: str = "", default: bool = True):
        self.features[name] = FeatureToggle(name, default, description)

    def is_enabled(self, name: str) -> bool:
        return self.features.get(
            name, FeatureToggle(name, False)
        ).option_available

    def set(self, name: str, value: bool):
        if name in self.features:
            self.features[name].option_available = value

    def all_features(self) -> List[FeatureToggle]:
        return list(self.features.values())

# ── end of feature toggle + registry ─────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  MENU ITEM
#
#  page_key   → renders as a plain href="?page=<key>" link (no JS needed,
#               works inside Streamlit's iframe without restriction)
#  js_action  → renders as an onclick= handler for browser-native calls
#               (window.open, window.print, navigator.share, etc.)
#               These two are mutually exclusive — page_key wins if both set.
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MenuItem:
    label:        str
    page_key:     str               = ""
    db_key:       str               = ""      # cost center code for switcher items
    js_action:    str               = ""      # raw JS for browser-native actions
    icon:         str               = ""
    shortcut:     str               = ""      # keyboard shortcut key (Alt+key)
    action:       Optional[Callable] = None
    feature_flag: str               = ""
    separator:    bool              = False
    children:     List["MenuItem"]  = field(default_factory=list)

    @property
    def full_label(self) -> str:
        label = f"{self.icon} &nbsp;{self.label}" if self.icon else self.label
        if self.shortcut:
            label += f' <span class="uha-nav-shortcut">Alt+{self.shortcut}</span>'
        return label

# ── end of menu item ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  MENU BAR DEFINITION
# ──────────────────────────────────────────────────────────────────────────────

def _cc_js(code: str) -> str:
    """JS snippet to switch cost center via ?db= URL param, preserving ?page=."""
    return (
        f"var u=new URL(window.location.href);"
        f"u.searchParams.set('db','{code}');"
        f"window.location.href=u.toString();"
    )


class MenuBar:

    def __init__(self, registry: FeatureRegistry):
        self.registry = registry
        self.menus: List[MenuItem] = self._build()

    def _build(self) -> List[MenuItem]:
        return [

            # ── File  (spec 3.1) ──────────────────────────────────────────────
            MenuItem(label="File", children=[
                MenuItem("New Tab",
                         icon="🗋",
                         js_action="window.open(window.location.href,'_blank');"),
                MenuItem("New Window",
                         icon="⬜",
                         js_action="window.open(window.location.href,'_blank','width=1400,height=900');"),
                MenuItem("", separator=True),
                MenuItem("Print",
                         icon="🖨",
                         js_action="window.print();"),
                MenuItem("Share",
                         icon="↗",
                         js_action=(
                             "if(navigator.share){"
                             "  navigator.share({title:'UHA Inventory',url:window.location.href})"
                             "} else {"
                             "  navigator.clipboard.writeText(window.location.href);"
                             "  alert('Link copied to clipboard');"
                             "}"
                         )),
                MenuItem("Export",  page_key="export", icon="📤",
                         feature_flag="export"),
                MenuItem("", separator=True),
                MenuItem("Close Tab",
                         icon="✕",
                         js_action="window.close();"),
                MenuItem("Exit Window",
                         icon="⏻",
                         js_action=(
                             "if(confirm('Close UHA Inventory?')){"
                             "  window.close();"
                             "}"
                         )),
            ]),

            # ── Dashboards  (spec 3.2) ────────────────────────────────────────
            # "Database" here = the stats overview for the active cost center,
            # not a separate DB connection. Switching cost center is in Settings.
            MenuItem(label="Dashboards", children=[
                MenuItem("Database",      page_key="dashboard",  icon="🏠",
                         shortcut="D", feature_flag="dashboard"),
                MenuItem("Inventory",     page_key="inventory",  icon="📦",
                         shortcut="I", feature_flag="inventory"),
                MenuItem("PCA",           page_key="pca",        icon="🧪",
                         shortcut="P", feature_flag="pca_engine"),
                MenuItem("Import",        page_key="import",     icon="📥",
                         shortcut="M", feature_flag="vendor_import"),
                MenuItem("", separator=True),
                MenuItem("Count Import",  page_key="count",       icon="📋",
                         shortcut="C", feature_flag="count_import"),
                MenuItem("Count Entry",   page_key="count_entry", icon="📝",
                         feature_flag="count_entry"),
                MenuItem("Transfer",      page_key="transfer",   icon="🔀",
                         shortcut="T", feature_flag="transfer_engine"),
                MenuItem("App Management", page_key="app_management", icon="⚙️",
                         shortcut="A", feature_flag="app_management"),
            ]),

            # ── View  (spec 3.3) ──────────────────────────────────────────────
            MenuItem(label="View", children=[
                MenuItem("Full Screen",
                         icon="⛶",
                         js_action="document.documentElement.requestFullscreen();"),
                MenuItem("", separator=True),
                MenuItem("Zoom 75%",  icon="🔍",
                         js_action="document.body.style.zoom='0.75';"),
                MenuItem("Zoom 90%",  icon="🔍",
                         js_action="document.body.style.zoom='0.90';"),
                MenuItem("Zoom 100%", icon="🔍",
                         js_action="document.body.style.zoom='1.0';"),
                MenuItem("Zoom 125%", icon="🔍",
                         js_action="document.body.style.zoom='1.25';"),
                MenuItem("Zoom 150%", icon="🔍",
                         js_action="document.body.style.zoom='1.5';"),
                MenuItem("", separator=True),
                MenuItem("Style",     page_key="settings", icon="🎨",
                         feature_flag="settings"),
                MenuItem("", separator=True),
                MenuItem("Toggle Sidebar",
                         icon="◀",
                         shortcut="B",
                         js_action=(
                             "var u=new URL(window.location.href);"
                             "u.searchParams.set('_sb_cycle','1');"
                             "window.location.href=u.toString();"
                         )),
                MenuItem("", separator=True),
                MenuItem("GL Codes",  page_key="gl_codes", icon="🏷️",
                         feature_flag="gl_codes"),
                MenuItem("History",   page_key="history",  icon="📜",
                         feature_flag="history"),
                MenuItem("Export",    page_key="export",   icon="📤",
                         feature_flag="export"),
            ]),

            # ── Import  (operational shortcut menu) ───────────────────────────
            MenuItem(label="Import", children=[
                MenuItem("Vendor Invoice / Auto-Detect", page_key="import", icon="📥",
                         feature_flag="vendor_import"),
                MenuItem("Count Import (file)",   page_key="count",       icon="📋",
                         feature_flag="count_import"),
                MenuItem("Count Entry (manual)",  page_key="count_entry", icon="📝",
                         feature_flag="count_entry"),
            ]),

            # ── Tools  (gated; hidden until features are enabled) ─────────────
            MenuItem(label="Tools", children=[
                MenuItem("PCA Creator",       page_key="pca",       icon="🧪",
                         feature_flag="pca_engine"),
                MenuItem("Transfer Sheet",    page_key="transfer",  icon="🔀",
                         feature_flag="transfer_engine"),
                MenuItem("Waste Tracking",    page_key="waste",     icon="♻️",
                         feature_flag="pca_waste_calc"),
                MenuItem("Historical Inject", page_key="historical",icon="🕰️",
                         feature_flag="mode_historical"),
                MenuItem("In-House Promo",    page_key="promo",     icon="🏠",
                         feature_flag="pca_recursive"),
            ]),

            # ── Settings ──────────────────────────────────────────────────────
            MenuItem(label="Settings", children=[
                MenuItem("Feature Toggles",  page_key="settings",          icon="🔧",
                         feature_flag="settings"),
                MenuItem("", separator=True),
                # Cost center switcher — uses ?db= param, handled in app.py main()
                MenuItem("🏢  Overhead",            db_key="57230",
                         js_action=_cc_js("57230")),
                MenuItem("🏟️  TDECU Concessions",   db_key="57231",
                         js_action=_cc_js("57231")),
                MenuItem("📦  Warehouse",            db_key="57232",
                         js_action=_cc_js("57232")),
                MenuItem("⚾  Schroeder Park",       db_key="57233",
                         js_action=_cc_js("57233")),
                MenuItem("🥎  Softball Stadium",     db_key="57234",
                         js_action=_cc_js("57234")),
                MenuItem("🍽️  Team Dining",          db_key="57235",
                         js_action=_cc_js("57235")),
                MenuItem("🎉  Catering",             db_key="57236",
                         js_action=_cc_js("57236")),
            ]),

            # ── Help  (spec 3.4) ──────────────────────────────────────────────
            MenuItem(label="Help", children=[
                MenuItem("About",
                         icon="ℹ️",
                         js_action=(
                             "alert('UHA IMS\\n"
                             "Inventory Management System\\n"
                             "Compass Group · UH Athletics');"
                         )),
                MenuItem("What's New",       page_key="changelog",  icon="🆕",
                         feature_flag="changelog"),
                MenuItem("Keyboard Shortcuts", page_key="help",     icon="⌨️"),
                MenuItem("", separator=True),
                MenuItem("Report Issue",
                         icon="🐛",
                         js_action=(
                             "window.open('https://github.com/trechurch/UHAIMS/issues/new','_blank');"
                         )),
            ]),
        ]

    def is_item_enabled(self, item: MenuItem) -> bool:
        if not item.feature_flag:
            return True
        return self.registry.is_enabled(item.feature_flag)

# ── end of menu bar definition ────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  SIDEBAR CONFIG
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SidebarConfig:
    visible:          bool = True
    show_nav:         bool = True
    show_cost_center: bool = True
    show_recent:      bool = True
    show_mode_widget: bool = True
    custom_label:     str  = "UHA TDECU Stadium"

# ── end of sidebar config ─────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  IMPORT MODE — PIPELINE STEP DESCRIPTOR
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PipelineStep:
    key:         str
    label:       str
    icon:        str  = ""
    timing:      str  = "flexible"
    repeatable:  bool = False
    description: str  = ""
    sub_options: List[Dict[str, Any]] = field(default_factory=list)

# ── end of pipeline step descriptor ──────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  IMPORT MODE DESCRIPTOR
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ImportMode:
    key:             str
    label:           str
    icon:            str  = ""
    description:     str  = ""
    pipeline_steps:  List[str] = field(default_factory=list)

# ── end of import mode descriptor ────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  MODE REGISTRY
# ──────────────────────────────────────────────────────────────────────────────

class ModeRegistry:

    def __init__(self):
        self.modes:  Dict[str, ImportMode]   = {}
        self.steps:  Dict[str, PipelineStep] = {}
        self._build_steps()
        self._build_modes()

    def _build_steps(self):
        steps = [
            PipelineStep(
                key="duplicate_detection", label="Duplicate Detection", icon="🔍",
                timing="flexible", description="Find exact and near-duplicate records before ingestion.",
            ),
            PipelineStep(
                key="error_filter", label="Error Filter", icon="🚨",
                timing="flexible", description="Show only rows with missing fields, bad values, or formatting issues.",
            ),
            PipelineStep(
                key="cluster_by_similarity", label="Cluster by Similarity", icon="🧩",
                timing="flexible", repeatable=True,
                description="Group similar items for bulk resolution.",
                sub_options=[
                    {"key": "description", "label": "Description",  "default": True},
                    {"key": "pack_size",   "label": "Pack Size",    "default": True},
                    {"key": "vendor",      "label": "Vendor",       "default": False},
                    {"key": "brand",       "label": "Brand",        "default": True},
                    {"key": "gtin",        "label": "GTIN",         "default": False},
                    {"key": "gl_code",     "label": "GL Code",      "default": False},
                ],
            ),
            PipelineStep(
                key="panel_build", label="Dynamic Panel Build", icon="📐",
                timing="flexible", description="Build issue-specific panels.",
            ),
            PipelineStep(
                key="fix_inline", label="Fix Errors Inline", icon="✏️",
                timing="flexible", repeatable=True,
                description="Let the user correct flagged rows directly in the review table.",
            ),
            PipelineStep(
                key="ai_smart_chooser", label="AI Smart Chooser", icon="🤖",
                timing="flexible", description="AI-assisted resolution of ambiguous items.",
            ),
            PipelineStep(
                key="manual_verification", label="Manual Verification of Flagged Items", icon="👁️",
                timing="fixed", description="Pause after analysis — user must review flagged records.",
            ),
            PipelineStep(
                key="require_panel_complete", label="Require Panel Completion", icon="✅",
                timing="fixed", description="User must resolve all dynamic panels before proceeding.",
            ),
            PipelineStep(
                key="revalidate_loop", label="Re-Validate After Inline Fixes", icon="🔄",
                timing="fixed", description="After inline edits, re-run validation. Loop until clean.",
            ),
        ]
        for s in steps:
            self.steps[s.key] = s

    def _build_modes(self):
        modes = [
            ImportMode(key="validation",  label="Validation Mode",   icon="🌐",
                       description="Load → analyze → review → approve → write.",
                       pipeline_steps=["duplicate_detection","manual_verification","require_panel_complete"]),
            ImportMode(key="selection",   label="Selection Mode",    icon="🧭",
                       description="Choose exactly which rows and fields to import.",
                       pipeline_steps=["duplicate_detection","manual_verification"]),
            ImportMode(key="data_driven", label="Data-Driven Mode",  icon="📊",
                       description="The data decides what panels the user sees.",
                       pipeline_steps=["panel_build","require_panel_complete"]),
            ImportMode(key="cluster",     label="Cluster-Driven Mode",icon="🧩",
                       description="Group similar items → resolve in bulk.",
                       pipeline_steps=["duplicate_detection","cluster_by_similarity","manual_verification"]),
            ImportMode(key="error_driven",label="Error-Driven Mode", icon="🚨",
                       description="Show only what's broken. Fix inline. Re-validate.",
                       pipeline_steps=["error_filter","fix_inline","revalidate_loop"]),
        ]
        for m in modes:
            self.modes[m.key] = m

    def mode_list(self)     -> List[ImportMode]:   return list(self.modes.values())
    def step_list(self)     -> List[PipelineStep]: return self.flexible_steps() + self.fixed_steps()
    def flexible_steps(self)-> List[PipelineStep]: return [s for s in self.steps.values() if s.timing=="flexible"]
    def fixed_steps(self)   -> List[PipelineStep]: return [s for s in self.steps.values() if s.timing=="fixed"]

    def steps_for_mode(self, mode_key: str) -> List[PipelineStep]:
        mode = self.modes.get(mode_key)
        if not mode:
            return []
        return [self.steps[k] for k in mode.pipeline_steps if k in self.steps]

# ── end of mode registry ──────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  IMPORT MODE SELECTOR CONFIG
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ImportModeSelectorConfig:
    tier:    str  = "single"
    display: str  = "sidebar"
    kiss:    bool = False

    @classmethod
    def from_session(cls, state: Dict) -> "ImportModeSelectorConfig":
        im = state.get("import_mode", {})
        return cls(tier=im.get("tier","single"), display=im.get("display","sidebar"), kiss=False)

# ── end of import mode selector config ───────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  DATABASE MANAGEMENT CONFIG
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DbOperation:
    key:              str
    label:            str
    icon:             str  = ""
    requires_confirm: bool = False
    destructive:      bool = False
    description:      str  = ""


DB_OPERATIONS: List[DbOperation] = [
    DbOperation("backup",         "Backup Database",      icon="💾"),
    DbOperation("restore",        "Restore from Backup",  icon="⏪", requires_confirm=True,  destructive=True),
    DbOperation("duplicate",      "Duplicate Database",   icon="📋"),
    DbOperation("create_new",     "Create New Database",  icon="➕"),
    DbOperation("rename",         "Rename / Relabel",     icon="✏️"),
    DbOperation("assign_cc",      "Assign Cost Center(s)",icon="🏷️"),
    DbOperation("set_thresholds", "Set Variance Thresholds",icon="🎚️"),
    DbOperation("clear_qty",      "Clear All Quantities", icon="🔢", requires_confirm=True,  destructive=True),
    DbOperation("clear_all",      "Clear All Items",      icon="🗑️", requires_confirm=True,  destructive=True),
    DbOperation("full_reset",     "Full Reset",           icon="☢️", requires_confirm=True,  destructive=True),
]

# ── end of database management config ────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  DEFAULT REGISTRY
# ──────────────────────────────────────────────────────────────────────────────

def build_default_registry() -> FeatureRegistry:
    reg = FeatureRegistry()
    reg.add("inventory",            "Inventory Items View",          True)
    reg.add("history",              "Change History",                True)
    reg.add("gl_codes",             "GL Code Manager",               True)
    reg.add("vendor_import",        "Vendor Invoice Import",         True)
    reg.add("count_import",         "Inventory Count Import",        True)
    reg.add("export",               "Export Inventory",              True)
    reg.add("settings",             "Settings & Feature Toggles",    True)
    reg.add("dashboard",            "Dashboard",                     True)
    # ── Enabled modules ──────────────────────────────────────────────────────
    reg.add("pca_engine",           "PCA Creator & Build Sandbox",   True)
    reg.add("transfer_engine",      "Transfer Sheet Generator",      True)
    reg.add("count_entry",          "Physical Count Entry",          True)
    reg.add("match_review",         "Intelligent Match Review",      True)
    reg.add("overrides",            "Count Override Rule Manager",   True)
    reg.add("pos_map",              "POS ↔ Inventory Mapping",       True)
    reg.add("app_management",       "App Management Dashboard",      True)
    # ── Disabled until modules are built ─────────────────────────────────────
    reg.add("changelog",            "What's New / Changelog",        False)
    reg.add("compare_counts",       "Compare Count Files",           False)
    reg.add("import_mode_selector", "Import Mode Selector",          False)
    reg.add("pca_waste_calc",       "Advanced Waste Tracking",       False)
    reg.add("mode_historical",      "Chronological Data Injection",  False)
    reg.add("pca_recursive",        "In-House Product Promotion",    False)
    return reg

# ── end of default registry ───────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
#  MODULE-LEVEL SINGLETONS
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_REGISTRY  = build_default_registry()
DEFAULT_MODE_REG  = ModeRegistry()

# ── end of module-level singletons ───────────────────────────────────────────
