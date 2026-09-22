"""Engineering panel (Phase 6 UI): projects, circuits, calculations, results.

Structured views only — no schematic drag-and-drop, no simulation runs.
The service owns circuits/results; this panel reflects them.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from academic_core.ui.dialogs import prompt_form


class EngineeringPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app  # AcademicApp facade
        self.eng = app.engineering
        self.project: str | None = None
        self.circuit_name: str | None = None

        layout = QHBoxLayout(self)
        # -- projects ---------------------------------------------------------
        left = QVBoxLayout()
        left.addWidget(QLabel("Projects"))
        self.projects = QListWidget()
        left.addWidget(self.projects)
        row = QHBoxLayout()
        self.btn_new_proj = QPushButton("New project")
        self.btn_del_proj = QPushButton("Delete")
        row.addWidget(self.btn_new_proj)
        row.addWidget(self.btn_del_proj)
        left.addLayout(row)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(240)
        layout.addWidget(left_w)

        # -- circuits -------------------------------------------------------------
        mid = QVBoxLayout()
        mid.addWidget(QLabel("Circuits"))
        self.circuits = QListWidget()
        mid.addWidget(self.circuits)
        row2 = QHBoxLayout()
        self.btn_new_ckt = QPushButton("New circuit")
        self.btn_add_comp = QPushButton("Add component")
        row2.addWidget(self.btn_new_ckt)
        row2.addWidget(self.btn_add_comp)
        mid.addLayout(row2)
        mid_w = QWidget()
        mid_w.setLayout(mid)
        mid_w.setFixedWidth(260)
        layout.addWidget(mid_w)

        # -- detail ------------------------------------------------------------------
        right = QVBoxLayout()
        right.addWidget(QLabel("Topology / netlist / calculations"))
        self.detail = QTextEdit(readOnly=True)
        right.addWidget(self.detail)
        row3 = QHBoxLayout()
        self.btn_calc = QPushButton("Calculate…")
        self.btn_sim = QPushButton("Backend status")
        row3.addWidget(self.btn_calc)
        row3.addWidget(self.btn_sim)
        right.addLayout(row3)
        self.status = QLabel("No project")
        right.addWidget(self.status)
        right_w = QWidget()
        right_w.setLayout(right)
        layout.addWidget(right_w)

        self.btn_new_proj.clicked.connect(self._new_project)
        self.btn_del_proj.clicked.connect(self._del_project)
        self.projects.currentRowChanged.connect(lambda _i: self._select_project())
        self.btn_new_ckt.clicked.connect(self._new_circuit)
        self.btn_add_comp.clicked.connect(self._add_component)
        self.circuits.currentRowChanged.connect(lambda _i: self._select_circuit())
        self.btn_calc.clicked.connect(self._calculate)
        self.btn_sim.clicked.connect(self._backend_status)
        self.refresh_projects()

    # -- projects ---------------------------------------------------------------
    def refresh_projects(self) -> None:
        self.projects.clear()
        self._pnames = []
        for p in self.eng.repo.list_projects():
            self._pnames.append(p.name)
            self.projects.addItem(QListWidgetItem(p.name))

    def _new_project(self) -> None:
        v = prompt_form(self, "Project", [("name", "Name", "", "text")])
        if not v:
            return
        try:
            self.eng.create_project(v["name"])
        except Exception as e:
            QMessageBox.warning(self, "Project", f"{type(e).__name__}: {e}")
            return
        self.refresh_projects()

    def _del_project(self) -> None:
        i = self.projects.currentRow()
        if not (0 <= i < len(self._pnames)):
            return
        try:
            self.eng.repo.delete_project(self._pnames[i])
        except Exception as e:
            QMessageBox.warning(self, "Delete", f"{type(e).__name__}: {e}")
            return
        self.project = None
        self.refresh_projects()
        self._refresh_detail()

    def _select_project(self) -> None:
        i = self.projects.currentRow()
        self.project = self._pnames[i] if 0 <= i < len(self._pnames) else None
        self.circuits.clear()
        self._cnames = []
        if self.project:
            for name in self.eng.repo.circuits_of(self.project):
                self._cnames.append(name)
                self.circuits.addItem(QListWidgetItem(name))
        self._refresh_detail()

    # -- circuits ------------------------------------------------------------------
    def _new_circuit(self) -> None:
        if not self.project:
            QMessageBox.warning(self, "Circuit", "Select a project first")
            return
        v = prompt_form(self, "Circuit", [("name", "Name", "", "text")])
        if not v:
            return
        try:
            self.eng.save_circuit(self.project, self.eng.new_circuit(v["name"]))
        except Exception as e:
            QMessageBox.warning(self, "Circuit", f"{type(e).__name__}: {e}")
            return
        self._select_project()

    def _add_component(self) -> None:
        if not self.project or not self.circuit_name:
            QMessageBox.warning(self, "Component", "Select a project and circuit")
            return
        v = prompt_form(self, "Component",
                        [("type", "Type", [(t, t) for t in
                                           ("R", "C", "L", "V", "I", "D", "Q")], "combo"),
                         ("ref", "Ref (R1)", "", "text"),
                         ("value", "Value (10 kohm)", "", "text"),
                         ("pins", "Pins net1,net2", "", "text")])
        if not v:
            return
        from academic_core.errors import to_ui_error
        from academic_core.ui.errors import show_ui_error
        want = self.eng.component_pins(v["type"])
        nets = [n.strip() for n in v["pins"].split(",")]
        if len(nets) != len(want):
            show_ui_error(self, to_ui_error(
                ValueError(f"{v['type']} needs pins {list(want)}")))
            return
        try:
            self.eng.add_component(self.project, self.circuit_name, v["type"],
                                   v["ref"], v["value"], dict(zip(want, nets)))
        except Exception as e:
            QMessageBox.warning(self, "Component", f"{type(e).__name__}: {e}")
            return
        self._refresh_detail()

    def _select_circuit(self) -> None:
        names = getattr(self, "_cnames", [])
        i = self.circuits.currentRow()
        self.circuit_name = names[i] if 0 <= i < len(names) else None
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        if not self.project or not self.circuit_name:
            self.detail.setPlainText("Select a project and circuit")
            self.status.setText(self.project or "No project")
            return
        circuit = self.eng.repo.load_circuit(self.project, self.circuit_name)
        warnings = self.eng.circuit_warnings(circuit)
        structural_line = ""
        try:
            plan = self.eng.analyze_circuit(circuit)
            topos = [t.topology.value for t in plan.recognized_topologies]
            structural_line = f"structural: {plan.classification} [{', '.join(topos) or 'none'}] (primary: {plan.primary_analysis.value if plan.primary_analysis else 'none'})"
        except Exception as e:
            from academic_core.errors import to_ui_error
            from academic_core.ui.errors import show_ui_error  # noqa: F401
            structural_line = f"structural: unavailable ({to_ui_error(e).error_code})"
        calcs = self.eng.repo.calculations_of(self.project)
        lines = [f"circuit: {self.circuit_name}",
                 f"components: {len(circuit.components)}",
                 f"nets: {sorted(circuit.nets)}",
                 f"topology: {'; '.join(warnings) or 'clean'}"]
        if structural_line:
            lines.append(structural_line)
        lines.extend(["", "-- netlist --", circuit.to_netlist().rstrip(),
                      "", f"-- calculations ({len(calcs)}) --"])
        for c in calcs[-10:]:
            lines.append(f"• {c['name']}: {c['value']} {c['unit']} [{c['digest'][:8]}]")
        self.detail.setPlainText("\n".join(lines))
        self.status.setText(f"{self.project} / {self.circuit_name}")


    # -- calculations ------------------------------------------------------------------
    def _calculate(self) -> None:
        v = prompt_form(self, "Calculate",
                        [("equation", "Equation (I = V / R)", "I = V / R", "text"),
                         ("inputs", "Inputs (V=5 V; R=1 kohm)", "V=5 V; R=1 kohm", "text"),
                         ("name", "Name", "", "text")])
        if not v:
            return
        try:
            inputs = dict(p.split("=", 1) for p in v["inputs"].split(";") if "=" in p)
            inputs = {k.strip(): val.strip() for k, val in inputs.items()}
            result = self.eng.calculate(inputs, v["equation"],
                                        project=self.project or "",
                                        name=v["name"])
        except Exception as e:
            QMessageBox.warning(self, "Calculate", f"{type(e).__name__}: {e}")
            return
        QMessageBox.information(self, "Result",
                                f"{result.short()}\ndigest {result.digest[:12]}")
        self._refresh_detail()

    def _backend_status(self) -> None:
        QMessageBox.information(self, "Simulation backends",
                                "\n".join(self.eng.backend_status_lines()))
