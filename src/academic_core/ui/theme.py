# SPDX-License-Identifier: MIT
"""AcademicCore visual system (DESIGN.md tokens, Qt binding).

DESIGN-SYSTEM-2026: warm neutrals + one cyan accent, Segoe UI Variable,
mono quarantined to netlists/digests/code, 100-180ms functional motion.

Only PySide6 here — no domain, no infrastructure (architecture boundary).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication

ORG = "Academic Core"
APP = "Academic Core"
APPEARANCE_KEY = "appearance"  # system | light | dark

FONT_STACK = '"Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", sans-serif'
MONO_STACK = '"Cascadia Mono", Consolas, "Courier New", monospace'


@dataclass(frozen=True)
class Tokens:
    """DESIGN-SYSTEM-2026 tokens. Legacy names kept; see the mapping in §8.

    ground=bg, card=surface, field=elevated, hairline=divider, ink=text,
    tertiary=text-disabled. ``sidebar`` is the bg tone used by menus/status.
    """

    mode: str  # light | dark
    sidebar: str
    ground: str
    card: str
    hairline: str
    ink: str
    secondary: str
    tertiary: str
    accent: str
    accent_ink: str
    accent_soft: str
    accent_text: str
    field: str
    success_bg: str
    success_ink: str
    warning_bg: str
    warning_ink: str
    error_bg: str
    error_ink: str
    info_bg: str
    info_ink: str
    idle_bg: str
    idle_ink: str
    shadow: str
    border_control: str
    disabled_bg: str
    hover: str
    pressed: str
    accent_hover: str
    popover: str
    series: tuple  # categorical data colours (DESIGN-SYSTEM-2026 3.6)


LIGHT = Tokens(
    mode="light",
    sidebar="#F7F7F5",
    ground="#F7F7F5",
    card="#FFFFFF",
    hairline="#E6E6E3",
    ink="#111111",
    secondary="#6B6B6B",
    tertiary="#A3A3A0",
    accent="#0A6A7C",
    accent_ink="#FFFFFF",
    accent_soft="#E1F1F4",
    accent_text="#0A6A7C",
    field="#F2F2F0",
    success_bg="#E6F4EA",
    success_ink="#166534",
    warning_bg="#FFF1D6",
    warning_ink="#8A5300",
    error_bg="#FDE8E6",
    error_ink="#B42318",
    info_bg="#E3F3F7",
    info_ink="#0B6478",
    idle_bg="#ECECE9",
    idle_ink="#5C5C5A",
    shadow="rgba(17, 17, 17, 0.12)",
    border_control="#949490",
    disabled_bg="#ECECE9",
    hover="#E9E9E6",
    pressed="#E0E0DC",
    accent_hover="#085A69",
    popover="#FFFFFF",
    series=("#0A6A7C", "#B45309", "#6D4AAE", "#B4234A", "#2F7D32", "#52616B"),
)

DARK = Tokens(
    mode="dark",
    sidebar="#111111",
    ground="#111111",
    card="#1A1A1A",
    hairline="#2E2E2E",
    ink="#F5F5F5",
    secondary="#A0A0A0",
    tertiary="#5A5A5A",
    accent="#4CC9E0",
    accent_ink="#0A1A1F",
    accent_soft="rgba(76, 201, 224, 0.16)",
    accent_text="#4CC9E0",
    field="#202020",
    success_bg="#17301F",
    success_ink="#6FD08C",
    warning_bg="#3A2A0B",
    warning_ink="#F2B84B",
    error_bg="#3D1917",
    error_ink="#FF8A80",
    info_bg="#0F2E36",
    info_ink="#5CCFE6",
    idle_bg="#262626",
    idle_ink="#A0A0A0",
    shadow="rgba(0, 0, 0, 0.55)",
    border_control="#6A6A6A",
    disabled_bg="#1E1E1E",
    hover="#2C2C2C",
    pressed="#363636",
    accent_hover="#6ED6EA",
    popover="#262626",
    series=("#4CC9E0", "#F2A03D", "#B79CF0", "#F27A9A", "#6FD08C", "#9FB0BA"),
)

_STATE_BG = {
    "IDLE": ("idle_bg", "idle_ink"),
    "RUNNING": ("info_bg", "info_ink"),
    "SUCCESS": ("success_bg", "success_ink"),
    "WARNING": ("warning_bg", "warning_ink"),
    "ERROR": ("error_bg", "error_ink"),
}


def resolve_mode(saved: str) -> str:
    """Map a saved appearance choice to a concrete mode."""
    if saved in ("light", "dark"):
        return saved
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return "dark" if scheme.value == 1 else "light"
    except Exception:
        return "light"


def current_tokens() -> Tokens:
    settings = QSettings(ORG, APP)
    return DARK if resolve_mode(settings.value(APPEARANCE_KEY, "system")) == "dark" else LIGHT


def status_colors(state: str, tokens: Tokens) -> tuple[str, str]:
    """(background, foreground) for a UiState name. Unknown states stay idle."""
    bg_attr, fg_attr = _STATE_BG.get(str(state).upper(), ("idle_bg", "idle_ink"))
    return getattr(tokens, bg_attr), getattr(tokens, fg_attr)


def apply_status_style(label, state) -> None:
    """Dress a status QLabel as a pill for ``state`` (UiState or name).

    Additive: keeps text and objectName, only sets dynamic properties and
    repolishes so the ``[state=...]`` QSS selectors apply.
    """
    from PySide6.QtWidgets import QWidget

    name = state.value if hasattr(state, "value") else str(state)
    changed = label.property("state") not in (None, name.upper())
    label.setProperty("role", "pill")
    label.setProperty("state", name.upper())
    if isinstance(label, QWidget):
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()
        if changed and label.isVisible():
            from academic_core.ui import motion
            motion.flash(label)


def stylesheet(tokens: Tokens) -> str:
    """Full application QSS for ``tokens`` (Fusion base)."""
    t = tokens
    return f"""
QWidget {{ font-family: {FONT_STACK}; font-size: 14px; }}
QMainWindow, QDialog {{ background: {t.ground}; }}
QWidget[objectName="Sidebar"] {{ background: {t.ground}; }}
QLabel[objectName="SidebarHeader"] {{ color: {t.secondary}; font-size: 12px; font-weight: 600; }}
QLabel[objectName="AppTitle"] {{ color: {t.ink}; font-size: 28px; font-weight: 600; }}
QLabel[objectName="CardTitle"] {{ color: {t.ink}; font-size: 20px; font-weight: 600; }}
QLabel[objectName="SectionTitle"] {{ color: {t.ink}; font-size: 20px; font-weight: 600; }}
QLabel[objectName="Display"] {{ color: {t.ink}; font-size: 40px; font-weight: 600; }}
QLabel[objectName="Lead"] {{ color: {t.secondary}; font-size: 16px; }}
QFrame[objectName="ContinueBlock"] {{ background: {t.card}; border-radius: 12px; }}
QPushButton[role="row"] {{
    background: transparent; border: 2px solid transparent; border-radius: 8px; text-align: left;
}}
QPushButton[role="row"]:hover {{ background: {t.hover}; }}
QPushButton[role="row"]:focus {{ border: 2px solid {t.accent}; }}
QPushButton[role="row"]:disabled {{ background: transparent; }}
QLabel[role="date"] {{ color: {t.ink}; font-weight: 600; }}
QLabel[role="danger"] {{ color: {t.error_ink}; font-weight: 600; }}
QLabel[objectName="Caption"] {{ color: {t.secondary}; font-size: 12px; }}
QLabel[objectName="CardStatus"] {{ color: {t.secondary}; font-size: 13px; }}
QLabel[objectName="Mono"] {{ font-family: {MONO_STACK}; }}
QLabel[role="pill"] {{
    border-radius: 12px; padding: 3px 10px; font-weight: 600; font-size: 12px;
    background: {t.idle_bg}; color: {t.idle_ink};
}}
QLabel[role="pill"][state="RUNNING"] {{ background: {t.info_bg}; color: {t.info_ink}; }}
QLabel[role="pill"][state="SUCCESS"] {{ background: {t.success_bg}; color: {t.success_ink}; }}
QLabel[role="pill"][state="WARNING"] {{ background: {t.warning_bg}; color: {t.warning_ink}; }}
QLabel[role="pill"][state="ERROR"] {{ background: {t.error_bg}; color: {t.error_ink}; }}
QFrame[objectName="Card"] {{
    background: {t.card}; border: 1px solid {t.hairline}; border-radius: 12px;
}}
QTabWidget::pane {{ border: 0; background: {t.ground}; }}
QTabBar::tab {{
    background: transparent; color: {t.secondary};
    padding: 8px 14px; margin: 4px 2px 0 2px; border-radius: 8px;
}}
QTabBar::tab:hover {{ color: {t.ink}; background: {t.hover}; }}
QTabBar::tab:selected {{ color: {t.accent_text}; font-weight: 600; background: {t.accent_soft}; }}
QTreeWidget[objectName="SidebarTree"], QListWidget {{
    background: transparent; border: 0; color: {t.ink};
}}
QTreeWidget[objectName="SidebarTree"]::item, QListWidget::item {{
    padding: 6px 8px; border-radius: 8px; color: {t.ink};
}}
QTreeWidget[objectName="SidebarTree"]::item:hover, QListWidget::item:hover {{ background: {t.hover}; }}
QTreeWidget[objectName="SidebarTree"]::item:selected, QListWidget::item:selected {{
    background: {t.accent_soft}; color: {t.ink}; font-weight: 600;
}}
QTreeWidget, QTableWidget, QTextEdit[objectName="Output"] {{
    background: {t.card}; border: 1px solid {t.hairline}; border-radius: 8px;
    color: {t.ink}; selection-background-color: {t.accent_soft}; selection-color: {t.ink};
}}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDateEdit {{
    background: {t.field}; border: 1px solid {t.border_control}; border-radius: 8px;
    padding: 7px 11px; color: {t.ink}; selection-background-color: {t.accent};
    selection-color: {t.accent_ink}; min-height: 20px;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus {{
    border: 2px solid {t.accent}; padding: 6px 10px;
}}
QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled {{
    color: {t.tertiary}; background: {t.disabled_bg}; border-color: {t.hairline};
}}
QPushButton {{
    background: {t.field}; border: 2px solid transparent; border-radius: 8px;
    padding: 6px 14px; color: {t.ink}; min-height: 20px;
}}
QPushButton:hover {{ background: {t.hover}; }}
QPushButton:pressed {{ background: {t.pressed}; }}
QPushButton:focus {{ border: 2px solid {t.accent}; }}
QPushButton:disabled {{ color: {t.tertiary}; background: {t.disabled_bg}; }}
QPushButton[class="primary"] {{
    background: {t.accent}; color: {t.accent_ink}; font-weight: 600;
}}
QPushButton[class="primary"]:hover, QPushButton[class="primary"]:pressed {{ background: {t.accent_hover}; }}
QPushButton[class="primary"]:focus {{ border: 2px solid {t.ink}; }}
QPushButton[class="primary"]:disabled {{ background: {t.disabled_bg}; color: {t.tertiary}; }}
QPushButton[class="danger"] {{ background: {t.error_ink}; color: {t.ground}; font-weight: 600; }}
QPushButton[class="danger"]:hover, QPushButton[class="danger"]:pressed {{ background: {t.error_ink}; border: 2px solid {t.ink}; }}
QPushButton[class="danger"]:focus {{ border: 2px solid {t.ink}; }}
QLabel[objectName="DialogTitle"] {{ color: {t.ink}; font-size: 18px; font-weight: 600; }}
QLabel[objectName="DialogContext"] {{ color: {t.secondary}; font-size: 13px; }}
QPushButton[class="subtle"] {{
    background: transparent; color: {t.accent_text}; font-weight: 600;
}}
QPushButton[class="subtle"]:hover {{ background: {t.accent_soft}; }}
QHeaderView::section {{
    background: {t.field}; color: {t.secondary}; border: 0;
    border-bottom: 1px solid {t.hairline}; padding: 6px 8px; font-weight: 600; font-size: 13px;
}}
QTableWidget {{ gridline-color: {t.hairline}; }}
QTableWidget::item:selected {{ background: {t.accent_soft}; color: {t.ink}; }}
QMenuBar {{ background: {t.card}; color: {t.ink}; }}
QMenuBar::item {{ padding: 4px 10px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {t.hover}; }}
QMenu {{ background: {t.popover}; border: 1px solid {t.hairline}; color: {t.ink}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t.accent_soft}; }}
QToolTip {{ background: {t.popover}; color: {t.ink}; border: 1px solid {t.hairline}; padding: 6px 10px; font-size: 12px; }}
QStatusBar {{ background: {t.card}; color: {t.secondary}; font-size: 12px; }}
QStatusBar::item {{ border: 0; }}
QDockWidget {{ color: {t.ink}; }}
QDockWidget::title {{
    background: {t.card}; color: {t.secondary}; padding: 6px; font-weight: 600;
}}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.tertiary}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.tertiary}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QCheckBox, QRadioButton {{ color: {t.ink}; spacing: 8px; }}
QCheckBox::indicator, QListWidget::indicator {{
    width: 14px; height: 14px; border: 2px solid {t.border_control}; border-radius: 4px; background: {t.card};
}}
QCheckBox::indicator:checked, QListWidget::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
QGroupBox {{ color: {t.ink}; border: 1px solid {t.hairline}; border-radius: 12px; margin-top: 14px; padding-top: 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; color: {t.secondary}; font-weight: 600; }}

/* -- product shell (UX IA 2026 section 4) ------------------------------ */
QFrame[objectName="NavRail"] {{ background: {t.card}; border-right: 1px solid {t.hairline}; }}
QLabel[objectName="RailBrand"] {{ color: {t.ink}; font-size: 16px; font-weight: 600; padding: 4px 12px; }}
QToolButton[role="nav"] {{
    background: transparent; border: 2px solid transparent; border-radius: 8px;
    padding: 8px 12px; color: {t.secondary}; font-weight: 600; text-align: left;
}}
QToolButton[role="nav"]:hover {{ background: {t.hover}; color: {t.ink}; }}
QToolButton[role="nav"]:checked {{ background: {t.accent_soft}; color: {t.accent_text}; }}
QToolButton[role="nav"]:focus {{ border: 2px solid {t.accent}; }}
QFrame[objectName="TopBar"] {{ background: {t.card}; border-bottom: 1px solid {t.hairline}; }}
QPushButton[role="crumb"] {{
    background: transparent; color: {t.secondary}; padding: 4px 6px; border-radius: 6px;
}}
QPushButton[role="crumb"]:hover {{ background: {t.hover}; color: {t.ink}; }}
QLabel[role="crumb-current"] {{ color: {t.ink}; font-weight: 600; font-size: 16px; padding: 4px 6px; }}
QLabel[role="crumb-sep"] {{ color: {t.secondary}; }}
QPushButton[objectName="ContextChip"] {{ background: {t.field}; color: {t.ink}; padding: 6px 12px; }}
QPushButton[objectName="SearchButton"] {{
    background: {t.field}; color: {t.secondary}; padding: 6px 12px; text-align: left; min-width: 220px;
}}
QFrame[objectName="SectionBar"] {{ background: {t.ground}; }}
QPushButton[role="section"] {{
    background: transparent; color: {t.secondary}; font-weight: 600; padding: 6px 14px;
}}
QPushButton[role="section"]:hover {{ background: {t.hover}; color: {t.ink}; }}
QPushButton[role="section"]:checked {{ background: {t.accent_soft}; color: {t.accent_text}; }}
QScrollArea[objectName="PageScroll"], QScrollArea[objectName="PageScroll"] > QWidget > QWidget {{ background: transparent; }}
/* -- engineering workspace kit (DESIGN-SYSTEM-2026 section 4.4) ---------- */
QFrame[objectName="Panel"] {{ background: {t.card}; border-radius: 12px; }}
QLabel[objectName="PanelTitle"] {{ color: {t.ink}; font-size: 14px; font-weight: 600; }}
QFrame[objectName="Metric"] {{ background: {t.field}; border-radius: 8px; }}
QLabel[role="metric-label"] {{ color: {t.secondary}; font-size: 12px; }}
QLabel[role="metric-value"] {{ color: {t.ink}; font-size: 24px; font-weight: 600; }}
QLabel[role="metric-unit"] {{ color: {t.secondary}; font-size: 13px; }}
QLabel[role="key"] {{ color: {t.secondary}; font-size: 13px; }}
QLabel[role="value"] {{ color: {t.ink}; }}
QFrame[objectName="EmptyState"] {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {t.hover}; }}
QTextEdit[objectName="Mono"], QTextEdit[role="mono"] {{ font-family: {MONO_STACK}; font-size: 13px; }}
QListWidget[objectName="PaletteList"]::item {{ padding: 8px 12px; }}
"""


def build_palette(t: Tokens):
    """Qt palette from tokens, so unstyled widgets and custom painting follow
    the theme instead of the OS scheme (light theme on a dark Windows)."""
    from PySide6.QtGui import QColor, QPalette

    pal = QPalette()
    R = QPalette.ColorRole
    for role, value in ((R.Window, t.ground), (R.WindowText, t.ink), (R.Base, t.card),
                        (R.AlternateBase, t.field), (R.Text, t.ink), (R.Button, t.field),
                        (R.ButtonText, t.ink), (R.ToolTipBase, t.popover), (R.ToolTipText, t.ink),
                        (R.Highlight, t.accent), (R.HighlightedText, t.accent_ink),
                        (R.PlaceholderText, t.secondary), (R.Mid, t.secondary),
                        (R.Link, t.accent_text)):
        pal.setColor(role, QColor(value))
    for role in (R.WindowText, R.Text, R.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.tertiary))
    return pal


def apply_theme(qapp, mode: str) -> Tokens:
    """Apply Fusion + the world QSS for ``mode`` (light|dark|system)."""
    from PySide6.QtWidgets import QApplication

    concrete = resolve_mode(mode) if mode in ("light", "dark", "system") else "light"
    tokens = DARK if concrete == "dark" else LIGHT
    if isinstance(qapp, QApplication):
        qapp.setStyle("Fusion")
        qapp.setPalette(build_palette(tokens))
        qapp.setStyleSheet(stylesheet(tokens))
    return tokens


def apply_saved_theme(qapp) -> Tokens:
    """Apply the persisted appearance choice (default: follow the OS)."""
    settings = QSettings(ORG, APP)
    return apply_theme(qapp, settings.value(APPEARANCE_KEY, "system"))


def save_mode(mode: str) -> None:
    QSettings(ORG, APP).setValue(APPEARANCE_KEY, mode)
