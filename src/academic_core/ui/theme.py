# SPDX-License-Identifier: MIT
"""AcademicCore visual system (DESIGN.md tokens, Qt binding).

Apple-workbench world, code-led contract ``src-academic-core-ui``:
Restrained color (neutrals + one accent), system sans, tabular figures for
data, mono quarantined to netlists/digests/code, 150-250ms state motion.

Only PySide6 here — no domain, no infrastructure (architecture boundary).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication

ORG = "Academic Core"
APP = "Academic Core"
APPEARANCE_KEY = "appearance"  # system | light | dark

FONT_STACK = '"Segoe UI", "SF Pro Text", -apple-system, "Helvetica Neue", Arial, sans-serif'
MONO_STACK = '"Cascadia Mono", "SF Mono", Consolas, "Courier New", monospace'


@dataclass(frozen=True)
class Tokens:
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


LIGHT = Tokens(
    mode="light",
    sidebar="#F5F5F7",
    ground="#F2F2F6",
    card="#FFFFFF",
    hairline="#E2E2E8",
    ink="#1D1D1F",
    secondary="#6E6E73",
    tertiary="#AEAEB2",
    accent="#007AFF",
    accent_ink="#FFFFFF",
    accent_soft="#E5F0FF",
    accent_text="#0066CC",
    field="#FFFFFF",
    success_bg="#E3F5E9",
    success_ink="#187038",
    warning_bg="#FFF2D2",
    warning_ink="#8A5A00",
    error_bg="#FDE7E7",
    error_ink="#B3261E",
    info_bg="#E5F0FF",
    info_ink="#0B5CAD",
    idle_bg="#E9E9EE",
    idle_ink="#6E6E73",
    shadow="rgba(0, 0, 0, 0.08)",
)

DARK = Tokens(
    mode="dark",
    sidebar="#232328",
    ground="#1C1C1F",
    card="#2C2C31",
    hairline="#3C3C43",
    ink="#F5F5F7",
    secondary="#AEAEB2",
    tertiary="#6E6E73",
    accent="#0A84FF",
    accent_ink="#FFFFFF",
    accent_soft="rgba(10, 132, 255, 0.18)",
    accent_text="#7AB8FF",
    field="#2C2C31",
    success_bg="rgba(52, 199, 89, 0.16)",
    success_ink="#7EE2A0",
    warning_bg="rgba(255, 204, 0, 0.14)",
    warning_ink="#FFD60A",
    error_bg="rgba(255, 69, 58, 0.16)",
    error_ink="#FF9D97",
    info_bg="rgba(10, 132, 255, 0.18)",
    info_ink="#7AB8FF",
    idle_bg="#3A3A40",
    idle_ink="#AEAEB2",
    shadow="rgba(0, 0, 0, 0.45)",
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
    label.setProperty("role", "pill")
    label.setProperty("state", name.upper())
    if isinstance(label, QWidget):
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()


def stylesheet(tokens: Tokens) -> str:
    """Full application QSS for ``tokens`` (Fusion base)."""
    t = tokens
    return f"""
* {{ font-family: {FONT_STACK}; font-size: 9pt; }}
QMainWindow, QDialog {{ background: {t.ground}; }}
QWidget[objectName="Sidebar"] {{ background: {t.sidebar}; }}
QLabel[objectName="SidebarHeader"] {{ color: {t.secondary}; font-size: 8pt; font-weight: 600; }}
QLabel[objectName="AppTitle"] {{ color: {t.ink}; font-size: 15pt; font-weight: 700; }}
QLabel[objectName="CardTitle"] {{ color: {t.ink}; font-size: 11pt; font-weight: 600; }}
QLabel[objectName="SectionTitle"] {{ color: {t.ink}; font-size: 10pt; font-weight: 600; }}
QLabel[objectName="Caption"] {{ color: {t.secondary}; font-size: 8.5pt; }}
QLabel[objectName="CardStatus"] {{ color: {t.secondary}; font-size: 8.5pt; }}
QLabel[objectName="Mono"] {{ font-family: {MONO_STACK}; }}
QLabel[role="pill"] {{
    border-radius: 8px; padding: 3px 10px; font-weight: 600; font-size: 8.5pt;
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
    padding: 7px 14px; margin: 4px 2px 0 2px; border-radius: 7px;
}}
QTabBar::tab:hover {{ color: {t.ink}; background: {t.idle_bg}; }}
QTabBar::tab:selected {{ color: {t.ink}; font-weight: 600; background: {t.accent_soft}; }}
QTreeWidget[objectName="SidebarTree"], QListWidget {{
    background: transparent; border: 0; color: {t.ink}; outline: 0;
}}
QTreeWidget[objectName="SidebarTree"]::item, QListWidget::item {{
    padding: 6px 8px; border-radius: 7px; color: {t.ink};
}}
QTreeWidget[objectName="SidebarTree"]::item:selected, QListWidget::item:selected {{
    background: {t.accent_soft}; color: {t.ink}; font-weight: 600;
}}
QTreeWidget, QTableWidget, QTextEdit[objectName="Output"] {{
    background: {t.card}; border: 1px solid {t.hairline}; border-radius: 8px;
    color: {t.ink}; selection-background-color: {t.accent_soft};
}}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDateEdit {{
    background: {t.field}; border: 1px solid {t.hairline}; border-radius: 7px;
    padding: 5px 8px; color: {t.ink}; selection-background-color: {t.accent};
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus {{
    border: 1px solid {t.accent};
}}
QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled {{
    color: {t.tertiary}; background: {t.ground};
}}
QPushButton {{
    background: {t.card}; border: 1px solid {t.hairline}; border-radius: 7px;
    padding: 6px 14px; color: {t.ink};
}}
QPushButton:hover {{ border-color: {t.accent}; }}
QPushButton:pressed {{ background: {t.accent_soft}; }}
QPushButton:disabled {{ color: {t.tertiary}; background: {t.ground}; }}
QPushButton[class="primary"] {{
    background: {t.accent}; border: 1px solid {t.accent}; color: {t.accent_ink};
    font-weight: 600;
}}
QPushButton[class="primary"]:hover {{ border-color: {t.accent_ink}; }}
QPushButton[class="primary"]:disabled {{ background: {t.idle_bg}; border-color: {t.idle_bg}; color: {t.tertiary}; }}
QPushButton[class="subtle"] {{
    background: transparent; border: 1px solid transparent; color: {t.accent_text}; font-weight: 600;
}}
QPushButton[class="subtle"]:hover {{ background: {t.accent_soft}; }}
QHeaderView::section {{
    background: {t.card}; color: {t.secondary}; border: 0;
    border-bottom: 1px solid {t.hairline}; padding: 6px 8px; font-weight: 600;
}}
QTableWidget {{ gridline-color: {t.hairline}; }}
QTableWidget::item:selected {{ background: {t.accent_soft}; color: {t.ink}; }}
QMenuBar {{ background: {t.sidebar}; color: {t.ink}; }}
QMenuBar::item:selected {{ background: {t.accent_soft}; border-radius: 6px; }}
QMenu {{ background: {t.card}; border: 1px solid {t.hairline}; color: {t.ink}; }}
QMenu::item:selected {{ background: {t.accent_soft}; }}
QToolTip {{ background: {t.card}; color: {t.ink}; border: 1px solid {t.hairline}; padding: 4px; }}
QStatusBar {{ background: {t.sidebar}; color: {t.secondary}; }}
QStatusBar::item {{ border: 0; }}
QDockWidget {{ color: {t.ink}; }}
QDockWidget::title {{
    background: {t.sidebar}; color: {t.secondary}; padding: 6px; font-weight: 600;
}}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.tertiary}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.tertiary}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QCheckBox, QRadioButton {{ color: {t.ink}; spacing: 6px; }}
QGroupBox {{ color: {t.ink}; border: 1px solid {t.hairline}; border-radius: 10px; margin-top: 12px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; color: {t.secondary}; }}
"""


def apply_theme(qapp, mode: str) -> Tokens:
    """Apply Fusion + the world QSS for ``mode`` (light|dark|system)."""
    from PySide6.QtWidgets import QApplication

    concrete = resolve_mode(mode) if mode in ("light", "dark", "system") else "light"
    tokens = DARK if concrete == "dark" else LIGHT
    if isinstance(qapp, QApplication):
        qapp.setStyle("Fusion")
        qapp.setStyleSheet(stylesheet(tokens))
    return tokens


def apply_saved_theme(qapp) -> Tokens:
    """Apply the persisted appearance choice (default: follow the OS)."""
    settings = QSettings(ORG, APP)
    return apply_theme(qapp, settings.value(APPEARANCE_KEY, "system"))


def save_mode(mode: str) -> None:
    QSettings(ORG, APP).setValue(APPEARANCE_KEY, mode)
