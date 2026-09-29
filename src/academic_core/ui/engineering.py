"""Engineering workspace: Circuits and Aerospace (UX 2026, prompt 6).

Context (project / circuit) -> Tools (toolbar) -> Visualization (components,
netlist) -> Results (topology, calculations, backends). Structured views
only: no schematic editor, no simulation runs. The service owns
circuits/results; this panel reflects them.

The panel is one page of the pinned 13 and hosts two workspaces:
``circuits`` and ``aerospace`` (the routes ``engineering/circuits`` and
``engineering/aerospace``), switched with :meth:`set_workspace`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from academic_core.ui.dialogs import prompt_form
from academic_core.ui.errors import show_ui_error
from academic_core.ui.state import UiState
from academic_core.ui.theme import apply_status_style
from academic_core.ui.workspace import EmptyState, KeyValueList, Metric, Panel

COMPONENT_COLUMNS = ("Ref", "Type", "Value", "Pins")
CALC_COLUMNS = ("Name", "Value", "Unit", "Digest")


def _table(columns: tuple[str, ...], name: str) -> QTableWidget:
    t = QTableWidget(0, len(columns))
    t.setHorizontalHeaderLabels(columns)
    t.setAccessibleName(name)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.verticalHeader().hide()
    t.verticalHeader().setDefaultSectionSize(32)
    t.horizontalHeader().setStretchLastSection(True)
    t.setShowGrid(False)
    return t


class EngineeringPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app  # AcademicApp facade
        self.eng = app.engineering
        self.project: str | None = None
        self.circuit_name: str | None = None
        self.state = UiState.IDLE
        self._pnames: list[str] = []
        self._cnames: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.workspaces = QStackedWidget()
        outer.addWidget(self.workspaces)
        self.circuits_workspace = QWidget()
        self._build_circuits(self.circuits_workspace)
        self.workspaces.addWidget(self.circuits_workspace)
        from academic_core.ui.aerospace import OrbitPanel
        self.orbit_panel = OrbitPanel(app)
        self.workspaces.addWidget(self.orbit_panel)
        self.refresh_projects()

    # -- layout --------------------------------------------------------------------------
    def _build_circuits(self, host: QWidget) -> None:
        root = QVBoxLayout(host)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # Tools ------------------------------------------------------------------------
        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.btn_new_proj = QPushButton("New project")
        self.btn_new_ckt = QPushButton("New circuit")
        self.btn_add_comp = QPushButton("Add component")
        self.btn_calc = QPushButton("Calculate…")
        self.btn_calc.setProperty("class", "primary")
        self.btn_sim = QPushButton("Backend status")
        for b in (self.btn_new_proj, self.btn_new_ckt, self.btn_add_comp):
            tools.addWidget(b)
        tools.addSpacing(8)
        tools.addWidget(self.btn_calc)
        tools.addWidget(self.btn_sim)
        tools.addStretch(1)
        self.status = QLabel("No project")
        self.status.setProperty("role", "crumb-current")
        self.pill = QLabel("IDLE")
        apply_status_style(self.pill, UiState.IDLE)
        tools.addWidget(self.status)
        tools.addWidget(self.pill)
        root.addLayout(tools)

        body = QHBoxLayout()
        body.setSpacing(16)
        root.addLayout(body, 1)

        # Context: projects and circuits ---------------------------------------------------
        explorer = QVBoxLayout()
        explorer.setSpacing(16)
        proj = Panel("Projects")
        self.btn_del_proj = QPushButton("Delete")
        self.btn_del_proj.setProperty("class", "subtle")
        proj.actions.addWidget(self.btn_del_proj)
        self.projects = QListWidget()
        self.projects.setAccessibleName("Projects")
        proj.add(self.projects, 1)
        explorer.addWidget(proj, 1)
        ckt = Panel("Circuits")
        self.circuits = QListWidget()
        self.circuits.setAccessibleName("Circuits")
        ckt.add(self.circuits, 1)
        explorer.addWidget(ckt, 1)
        explorer_w = QWidget()
        explorer_w.setLayout(explorer)
        explorer_w.setFixedWidth(260)
        body.addWidget(explorer_w)

        # Visualization: components / netlist --------------------------------------------
        view = Panel("Circuit")
        self.view_group = QButtonGroup(self)
        self.btn_view_components = QPushButton("Components")
        self.btn_view_netlist = QPushButton("Netlist")
        for i, b in enumerate((self.btn_view_components, self.btn_view_netlist), start=1):
            b.setProperty("role", "section")
            b.setCheckable(True)
            self.view_group.addButton(b, i)
            view.actions.addWidget(b)
        self.btn_view_components.setChecked(True)
        self.view_stack = QStackedWidget()
        self.empty = EmptyState("No circuit selected")
        self.components_table = _table(COMPONENT_COLUMNS, "Components")
        self.detail = QTextEdit(readOnly=True)
        self.detail.setObjectName("Output")
        self.detail.setProperty("role", "mono")
        self.detail.setAccessibleName("Netlist")
        for w in (self.empty, self.components_table, self.detail):
            self.view_stack.addWidget(w)
        view.add(self.view_stack, 1)
        body.addWidget(view, 3)

        # Results: topology, calculations, backends ----------------------------------------
        results = Panel("Results")
        self.facts = KeyValueList()
        results.add(self.facts)
        self.last_calc = Metric("Last calculation")
        self.last_calc.hide()
        results.add(self.last_calc)
        self.calc_table = _table(CALC_COLUMNS, "Calculations")
        self.calc_table.setMinimumHeight(120)
        results.add(self.calc_table, 1)
        self.backend_label = QLabel("Backends: not checked")
        self.backend_label.setObjectName("CardStatus")
        self.backend_label.setWordWrap(True)
        results.add(self.backend_label)
        body.addWidget(results, 2)

        self.btn_new_proj.clicked.connect(self._new_project)
        self.btn_del_proj.clicked.connect(self._del_project)
        self.projects.currentRowChanged.connect(lambda _i: self._select_project())
        self.btn_new_ckt.clicked.connect(self._new_circuit)
        self.btn_add_comp.clicked.connect(self._add_component)
        self.circuits.currentRowChanged.connect(lambda _i: self._select_circuit())
        self.btn_calc.clicked.connect(self._calculate)
        self.btn_sim.clicked.connect(self._backend_status)
        self.view_group.idClicked.connect(lambda _id: self._show_view())

    def set_workspace(self, name: str) -> None:
        """``circuits`` or ``aerospace`` (routes engineering/circuits|aerospace)."""
        self.workspaces.setCurrentWidget(self.orbit_panel if name == "aerospace"
                                         else self.circuits_workspace)

    # -- state -----------------------------------------------------------------------------
    def _set_state(self, state: UiState, text: str) -> None:
        self.state = state
        self.pill.setText(text)
        apply_status_style(self.pill, state)

    def _sync_actions(self) -> None:
        self.btn_del_proj.setEnabled(bool(self.project))
        self.btn_new_ckt.setEnabled(bool(self.project))
        self.btn_add_comp.setEnabled(bool(self.project and self.circuit_name))
        for b, tip in ((self.btn_new_ckt, "Select or create a project first"),
                       (self.btn_add_comp, "Select a circuit first")):
            b.setToolTip("" if b.isEnabled() else tip)

    # -- projects ---------------------------------------------------------------------------
    def refresh_projects(self) -> None:
        self.projects.clear()
        self._pnames = []
        for p in self.eng.repo.list_projects():
            self._pnames.append(p.name)
            self.projects.addItem(QListWidgetItem(p.name))
        self._sync_actions()
        self._refresh_detail()

    def _new_project(self) -> None:
        v = prompt_form(self, "Project", [("name", "Name", "", "text")])
        if not v:
            return
        try:
            self.eng.create_project(v["name"])
        except Exception as e:
            show_ui_error(self, e, "Project")
            return
        self.refresh_projects()

    def _del_project(self) -> None:
        i = self.projects.currentRow()
        if not (0 <= i < len(self._pnames)):
            return
        try:
            self.eng.repo.delete_project(self._pnames[i])
        except Exception as e:
            show_ui_error(self, e, "Delete project")
            return
        self.project = None
        self.circuit_name = None
        self.circuits.clear()
        self._cnames = []
        self.refresh_projects()

    def _select_project(self) -> None:
        i = self.projects.currentRow()
        self.project = self._pnames[i] if 0 <= i < len(self._pnames) else None
        self.circuit_name = None
        self.circuits.clear()
        self._cnames = []
        if self.project:
            for name in self.eng.repo.circuits_of(self.project):
                self._cnames.append(name)
                self.circuits.addItem(QListWidgetItem(name))
        self._sync_actions()
        self._refresh_detail()

    # -- circuits ------------------------------------------------------------------------------
    def _new_circuit(self) -> None:
        if not self.project:
            show_ui_error(self, ValueError("select a project first"), "Circuit")
            return
        v = prompt_form(self, "Circuit", [("name", "Name", "", "text")])
        if not v:
            return
        try:
            self.eng.save_circuit(self.project, self.eng.new_circuit(v["name"]))
        except Exception as e:
            show_ui_error(self, e, "Circuit")
            return
        self._select_project()
        if v["name"] in self._cnames:
            self.circuits.setCurrentRow(self._cnames.index(v["name"]))

    def _add_component(self) -> None:
        if not self.project or not self.circuit_name:
            show_ui_error(self, ValueError("select a project and a circuit"), "Component")
            return
        v = prompt_form(self, "Component",
                        [("type", "Type", [(t, t) for t in
                                           ("R", "C", "L", "V", "I", "D", "Q")], "combo"),
                         ("ref", "Ref (R1)", "", "text"),
                         ("value", "Value (10 kohm)", "", "text"),
                         ("pins", "Pins net1,net2", "", "text")])
        if not v:
            return
        want = self.eng.component_pins(v["type"])
        nets = [n.strip() for n in v["pins"].split(",")]
        if len(nets) != len(want):
            show_ui_error(self, ValueError(f"{v['type']} needs pins {list(want)}"), "Component")
            return
        try:
            self.eng.add_component(self.project, self.circuit_name, v["type"],
                                   v["ref"], v["value"], dict(zip(want, nets)))
        except Exception as e:
            show_ui_error(self, e, "Component")
            return
        self._refresh_detail()

    def _select_circuit(self) -> None:
        i = self.circuits.currentRow()
        self.circuit_name = self._cnames[i] if 0 <= i < len(self._cnames) else None
        self._sync_actions()
        self._refresh_detail()

    # -- views ------------------------------------------------------------------------------------
    def _show_view(self) -> None:
        if not (self.project and self.circuit_name):
            self.view_stack.setCurrentWidget(self.empty)
        elif self.btn_view_netlist.isChecked():
            self.view_stack.setCurrentWidget(self.detail)
        else:
            self.view_stack.setCurrentWidget(self.components_table)

    def _empty_state(self) -> None:
        if not self._pnames:
            self.empty.set("No projects yet", "Create a project to start building circuits.")
        elif not self.project:
            self.empty.set("Select a project", "Pick a project on the left to see its circuits.")
        elif not self._cnames:
            self.empty.set("This project has no circuits", "Create a circuit, then add components.")
        else:
            self.empty.set("Select a circuit", "Pick a circuit to see its components and netlist.")

    def _refresh_detail(self) -> None:
        self.calc_table.setRowCount(0)
        self.last_calc.hide()
        if not self.project or not self.circuit_name:
            self._empty_state()
            self.components_table.setRowCount(0)
            self.detail.clear()
            self.facts.set_rows([("Project", self.project or "—")])
            self.status.setText(self.project or "No project")
            self._show_view()
            if self.project:
                self._fill_calculations()
            return
        circuit = self.eng.repo.load_circuit(self.project, self.circuit_name)
        warnings = self.eng.circuit_warnings(circuit)
        rows = [("Circuit", self.circuit_name), ("Components", str(len(circuit.components))),
                ("Nets", ", ".join(sorted(circuit.nets)) or "—"),
                ("Topology", "; ".join(warnings) or "clean")]
        try:
            plan = self.eng.analyze_circuit(circuit)
            topos = [t.topology.value for t in plan.recognized_topologies]
            rows += [("Structure", plan.classification),
                     ("Recognized", ", ".join(topos) or "none"),
                     ("Primary analysis", plan.primary_analysis.value if plan.primary_analysis else "none")]
        except Exception as e:
            from academic_core.errors import to_ui_error
            rows.append(("Structure", f"unavailable ({to_ui_error(e).error_code})"))
        self.facts.set_rows(rows)
        self._fill_components(circuit)
        self.detail.setPlainText(circuit.to_netlist().rstrip())
        self._fill_calculations()
        self.status.setText(f"{self.project} / {self.circuit_name}")
        self._show_view()

    def _fill_components(self, circuit) -> None:
        comps = sorted(circuit.components, key=lambda c: c.ref.upper())
        self.components_table.setRowCount(len(comps))
        for r, c in enumerate(comps):
            pins = ", ".join(f"{p}={n}" for p, n in c.pins.items())
            for col, text in enumerate((c.ref.upper(), c.type.upper(),
                                        c.value.compact() if c.value else "—", pins)):
                self.components_table.setItem(r, col, QTableWidgetItem(text))
        self.components_table.resizeColumnsToContents()
        self.components_table.horizontalHeader().setStretchLastSection(True)

    def _fill_calculations(self) -> None:
        calcs = self.eng.repo.calculations_of(self.project)[-10:]
        self.calc_table.setRowCount(len(calcs))
        for r, c in enumerate(calcs):
            for col, text in enumerate((c["name"], str(c["value"]), c["unit"], c["digest"][:8])):
                self.calc_table.setItem(r, col, QTableWidgetItem(text))
        self.calc_table.resizeColumnsToContents()
        self.calc_table.horizontalHeader().setStretchLastSection(True)

    # -- calculations ------------------------------------------------------------------------------
    def _calculate(self) -> None:
        v = prompt_form(self, "Calculate",
                        [("equation", "Equation (I = V / R)", "I = V / R", "text"),
                         ("inputs", "Inputs (V=5 V; R=1 kohm)", "V=5 V; R=1 kohm", "text"),
                         ("name", "Name", "", "text")])
        if not v:
            return
        self._set_state(UiState.RUNNING, "RUNNING…")
        try:
            inputs = dict(p.split("=", 1) for p in v["inputs"].split(";") if "=" in p)
            inputs = {k.strip(): val.strip() for k, val in inputs.items()}
            result = self.eng.calculate(inputs, v["equation"],
                                        project=self.project or "",
                                        name=v["name"])
        except Exception as e:
            ui = show_ui_error(self, e, "Calculate")
            self._set_state(UiState.ERROR, f"ERROR {ui.error_code}")
            return
        self._refresh_detail()
        self.last_calc.set_value(result.short())
        self.last_calc.setToolTip(f"digest {result.digest}")
        self.last_calc.show()
        self._set_state(UiState.SUCCESS, "SUCCESS")

    def _backend_status(self) -> None:
        self.backend_label.setText("Backends: " + " · ".join(self.eng.backend_status_lines()))
