# SPDX-License-Identifier: MIT
"""Home (UX IA 2026 §5.1): where you are, what you can continue, what is coming.

Everything shown is real facade or UI state; a section with nothing to
show says so and offers the honest next step. No fictitious activity.
Composition: greeting, one primary action (Continue), coming-up list,
recent work and a compact tools list (no card grid).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from academic_core import __version__
from academic_core.ui import routes, state_store

STACK_BELOW = 860  # px: columns stack vertically under this width
RECENT_SHOWN = 5
DEADLINES_SHOWN = 5


def _safe(fn, fallback):
    try:
        value = fn()
    except Exception:
        return fallback
    return value if value or value == 0 else fallback


def greeting_for(hour: int) -> str:
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _stamp(iso: str) -> datetime:
    """Sortable timestamp; unparseable values sort oldest."""
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.astimezone()


def ago(iso: str, now: datetime) -> str:
    """Short relative time for an ISO timestamp; '' when unparseable."""
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = (_aware(now) - dt).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} h ago"
    if seconds < 172800:
        return "yesterday"
    return dt.astimezone().strftime("%d %b")


def due_text(due: date, today: date) -> str:
    days = (due - today).days
    if days < 0:
        return f"{-days} day{'s' if days != -1 else ''} overdue"
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


class RowButton(QPushButton):
    """Flat list row: title on the left, quiet caption on the right."""

    def __init__(self, title: str, caption: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("role", "row")
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(36)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        self.title_label = QLabel(title)
        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("CardStatus")
        for w in (self.title_label, self.caption_label):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.title_label, 1)
        lay.addWidget(self.caption_label, 0, Qt.AlignmentFlag.AlignRight)
        self.setAccessibleName(f"{title}, {caption}" if caption else title)


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


class DashboardPanel(QWidget):
    """Landing view. Emits ``navigate(key)`` for a route/legacy key and
    ``open_subject(stable_id)`` for a subject."""

    navigate = Signal(str)
    open_subject = Signal(str)

    def __init__(self, app, parent=None, now=None):
        super().__init__(parent)
        self.app = app
        self._now = now or (lambda: datetime.now().astimezone())
        self._continue_action: tuple[str, str] | None = None
        self._cards: dict[str, RowButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(48, 32, 48, 24)
        root.setSpacing(24)
        # Let the page shrink below the two-column layout minimum so it can restack.
        root.setSizeConstraint(QVBoxLayout.SizeConstraint.SetNoConstraint)

        header = QVBoxLayout()
        header.setSpacing(4)
        self.greeting_label = QLabel("")
        self.greeting_label.setObjectName("Display")
        self.greeting_label.setAccessibleName("Greeting")
        header.addWidget(self.greeting_label)
        self.greeting_sub = QLabel("")
        self.greeting_sub.setObjectName("Lead")
        self.greeting_sub.setWordWrap(True)
        header.addWidget(self.greeting_sub)
        root.addLayout(header)

        self._columns = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._columns.setSpacing(48)
        main = QVBoxLayout()
        main.setSpacing(24)
        side = QVBoxLayout()
        side.setSpacing(24)
        self._columns.addLayout(main, 3)
        self._columns.addLayout(side, 2)
        root.addLayout(self._columns, 1)

        # -- main: continue + coming up ---------------------------------------
        block = QFrame()
        block.setObjectName("ContinueBlock")
        bl = QVBoxLayout(block)
        bl.setContentsMargins(24, 24, 24, 24)
        bl.setSpacing(8)
        self.continue_title = QLabel("")
        self.continue_title.setObjectName("SectionTitle")
        self.continue_title.setWordWrap(True)
        self.continue_caption = QLabel("")
        self.continue_caption.setObjectName("CardStatus")
        self.continue_caption.setWordWrap(True)
        self.continue_button = QPushButton("Continue")
        self.continue_button.setProperty("class", "primary")
        self.continue_button.clicked.connect(self._on_continue)
        bl.addWidget(self.continue_title)
        bl.addWidget(self.continue_caption)
        bl.addSpacing(8)
        bl.addWidget(self.continue_button, 0, Qt.AlignmentFlag.AlignLeft)
        main.addWidget(block)

        due_head = QLabel("Coming up")
        due_head.setObjectName("SectionTitle")
        main.addWidget(due_head)
        self.deadlines_box = QVBoxLayout()
        self.deadlines_box.setSpacing(4)
        main.addLayout(self.deadlines_box)
        self.deadlines_empty = QLabel("")
        self.deadlines_empty.setObjectName("CardStatus")
        self.deadlines_empty.setWordWrap(True)
        main.addWidget(self.deadlines_empty)
        main.addStretch(1)

        # -- side: recent + tools -----------------------------------------------
        recent_head = QLabel("Recent")
        recent_head.setObjectName("SectionTitle")
        side.addWidget(recent_head)
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(0)
        side.addLayout(self.recent_box)
        self.recent_label = QLabel("")
        self.recent_label.setObjectName("CardStatus")
        self.recent_label.setWordWrap(True)
        side.addWidget(self.recent_label)
        tools_head = QLabel("Tools")
        tools_head.setObjectName("SectionTitle")
        side.addWidget(tools_head)
        self.tools_box = QVBoxLayout()
        self.tools_box.setSpacing(0)
        side.addLayout(self.tools_box)
        side.addStretch(1)

        self.state_label = QLabel("")
        self.state_label.setObjectName("Caption")
        root.addWidget(self.state_label)
        self.refresh_state()

    # -- responsive ----------------------------------------------------------------
    def minimumSizeHint(self) -> QSize:  # noqa: N802 — Qt override
        # The two-column hint would keep the page wider than STACK_BELOW and the
        # stacked layout could never engage; content fits a single column at 420.
        return QSize(420, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        direction = (QBoxLayout.Direction.TopToBottom if self.width() < STACK_BELOW
                     else QBoxLayout.Direction.LeftToRight)
        if self._columns.direction() != direction:
            self._columns.setDirection(direction)
        super().resizeEvent(event)

    # -- real data -------------------------------------------------------------------
    def _work_items(self) -> list[dict]:
        """Recently opened subjects (certified history) + sections (UI log), newest first."""
        items = []
        for r in _safe(lambda: self.app.search_history.list_recents(), []):
            items.append({"at": r.accessed, "kind": r.kind, "ref": r.ref,
                          "label": r.label, "url": r.url})
        for r in state_store.recent_routes():
            items.append({"at": r["at"], "kind": "route", "ref": r["route"],
                          "label": r["label"], "url": r["route"]})
        return sorted(items, key=lambda i: _stamp(i["at"]), reverse=True)

    def _action_for(self, item: dict) -> tuple[str, str] | None:
        """``("subject", id)`` | ``("route", id)`` | None when there is no destination."""
        if item["kind"] == "asignatura":
            if _safe(lambda: self.app.academic.get_subject(item["ref"]), None) is not None:
                return ("subject", item["ref"])
            return None
        route = routes.resolve(item["url"])
        return ("route", route.id) if route is not None else None

    def _subject_count(self) -> int:
        return len(_safe(lambda: self.app.academic.all_subjects(), []))

    # -- render ----------------------------------------------------------------------
    def refresh_state(self) -> None:
        now = self._now()
        self.greeting_label.setText(greeting_for(now.hour))
        self.state_label.setText(f"Academic Core v{__version__} · offline · your data stays on this computer")
        items = self._work_items()
        first = next(((i, a) for i in items if (a := self._action_for(i)) is not None), None)
        self._render_continue(first, now)
        used = first[0] if first else None
        self._render_recent([i for i in items if i is not used], items, now)
        self._render_deadlines(now)
        self._render_tools()

    def _render_continue(self, first, now: datetime) -> None:
        if first is not None:
            item, action = first
            self._continue_action = action
            title = item["label"].split(" › ")[-1]
            where = "Subject" if action[0] == "subject" else item["label"].split(" › ")[0]
            when = ago(item["at"], now)
            self.continue_title.setText(title)
            self.continue_caption.setText(f"{where} · opened {when}" if when else where)
            self.continue_button.setText("Continue")
            self.continue_button.setAccessibleName(f"Continue: {title}")
            self.greeting_sub.setText("Continue where you left off.")
            return
        self._continue_action = ("route", "learn/subject/summary")
        if self._subject_count():
            self.continue_title.setText("Nothing to continue yet")
            self.continue_caption.setText("Open a subject or one of the tools to get going.")
            self.continue_button.setText("Open Learn")
            self.greeting_sub.setText("Nothing to continue yet — pick a subject or open a tool.")
        else:
            self.continue_title.setText("Set up your first subject")
            self.continue_caption.setText("Add a subject to plan deadlines and keep track of grades.")
            self.continue_button.setText("Add a subject")
            self.greeting_sub.setText("Welcome. Start by adding a subject.")
        self.continue_button.setAccessibleName(self.continue_button.text())

    def _render_recent(self, rest: list[dict], all_items: list[dict], now: datetime) -> None:
        _clear(self.recent_box)
        rows = rest[:RECENT_SHOWN]
        for item in rows:
            action = self._action_for(item)
            row = RowButton(item["label"], ago(item["at"], now))
            if action is None:
                row.setEnabled(False)
                row.setToolTip("No destination available")
            else:
                row.clicked.connect(lambda _c=False, a=action: self._go(a))
            self.recent_box.addWidget(row)
        if rows:
            self.recent_label.hide()
            return
        self.recent_label.show()
        self.recent_label.setText(
            "No recent activity yet — open a subject or a tool." if not all_items
            else "No other recent activity.")

    def _render_deadlines(self, now: datetime) -> None:
        _clear(self.deadlines_box)
        today = now.date()
        q = self.app.queries
        overdue = _safe(lambda: list(q.overdue_deadlines(today, 2)), [])
        upcoming = _safe(lambda: list(q.upcoming_deadlines(today, DEADLINES_SHOWN)), [])
        shown = (overdue + upcoming)[:DEADLINES_SHOWN]
        for d in shown:
            self.deadlines_box.addWidget(self._deadline_row(d, today))
        if shown:
            self.deadlines_empty.hide()
            return
        self.deadlines_empty.show()
        self.deadlines_empty.setText(
            "Nothing due. Tasks and exams you add to a subject appear here."
            if self._subject_count() else "No subjects yet, so nothing is scheduled.")

    def _deadline_row(self, d, today: date) -> QWidget:
        row = QFrame()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(16)
        try:
            due = date.fromisoformat(d.due[:10])
        except ValueError:
            due = today
        date_label = QLabel(due.strftime("%a %d %b"))
        date_label.setProperty("role", "date")
        date_label.setMinimumWidth(96)
        try:
            font = date_label.font()
            font.setFeature("tnum", 1)
            date_label.setFont(font)
        except Exception:
            pass
        lay.addWidget(date_label)
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(QLabel(d.title))
        subject = _safe(lambda: self.app.academic.get_subject(d.subject_id).name, "")
        caption = QLabel(f"{subject} · {d.kind}" if subject else d.kind)
        caption.setObjectName("CardStatus")
        text.addWidget(caption)
        lay.addLayout(text, 1)
        status = QLabel(due_text(due, today))
        if due < today:
            status.setProperty("role", "danger")
        else:
            status.setObjectName("CardStatus")
        lay.addWidget(status, 0, Qt.AlignmentFlag.AlignRight)
        row.setAccessibleName(f"{d.title}, {status.text()}")
        return row

    def _tools(self) -> list[tuple[str, str, str]]:
        app = self.app
        return [
            ("exercises", "Exercises",
             _safe(lambda: f"{len(list(app.exercises.library_keys()))} in the library", "Engineering library")),
            ("simulation", "Analysis", "OP, transient, AC, DC sweep"),
            ("lab", "Lab", "Sessions, instruments, replay"),
            ("logic", "Digital Logic",
             _safe(lambda: f"{len(tuple(app.digital.demos()))} demo circuits", "Capture and trigger")),
            ("aerospace", "Aerospace", "Circular Earth orbit"),
            ("resources", "Library",
             _safe(lambda: f"{len(app.records.all_ids())} records", "Indexed records")),
            ("documents", "Documents",
             _safe(lambda: f"{len(app.authoring_store.authored_ids())} authored", "Notes and write-ups")),
            ("settings", "Settings", "Appearance and data"),
        ]

    def _render_tools(self) -> None:
        _clear(self.tools_box)
        self._cards = {}
        for key, title, caption in self._tools():
            row = RowButton(title, caption)
            row.clicked.connect(lambda _c=False, k=key: self.navigate.emit(k))
            self.tools_box.addWidget(row)
            self._cards[key] = row

    # -- actions ---------------------------------------------------------------------
    def _go(self, action: tuple[str, str]) -> None:
        kind, ref = action
        (self.open_subject if kind == "subject" else self.navigate).emit(ref)

    def _on_continue(self) -> None:
        if self._continue_action is not None:
            self._go(self._continue_action)
