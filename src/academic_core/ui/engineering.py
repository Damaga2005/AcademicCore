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
    QAbstractItemView, QButtonGroup, QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from academic_core.application import schematic as S
from academic_core.ui.dialogs import prompt_form
from academic_core.ui.schematic import SchematicPage
from academic_core.ui.errors import show_ui_error
from academic_core.ui.state import UiState
from academic_core.ui.theme import apply_status_style
from academic_core.ui.workspace import EmptyState, HintList, KeyValueList, Metric, Panel

COMPONENT_COLUMNS = ("Ref", "Tipo", "Valor", "Pines")
CALC_COLUMNS = ("Nombre", "Valor", "Unidad", "Digest")


def _table(columns: tuple[str, ...], name: str) -> QTableWidget:
    t = QTableWidget(0, len(columns))
    t.setHorizontalHeaderLabels(columns)
    t.setAccessibleName(name)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.verticalHeader().hide()
    t.verticalHeader().setDefaultSectionSize(32)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
        self.btn_new_proj = QPushButton("Nuevo proyecto")
        self.btn_new_ckt = QPushButton("Nuevo circuito")
        self.btn_add_comp = QPushButton("Añadir componente")
        self.btn_equiv = QPushButton("Thévenin/Norton…")
        self.btn_equiv.setToolTip("Equivalente visto desde dos nodos del circuito (motor F8-C, exacto)")
        self.btn_calc = QPushButton("Calcular…")
        self.btn_calc.setProperty("class", "primary")
        self.btn_sim = QPushButton("Estado de los motores")
        for b in (self.btn_new_proj, self.btn_new_ckt, self.btn_add_comp, self.btn_equiv):
            tools.addWidget(b)
        tools.addSpacing(8)
        tools.addWidget(self.btn_calc)
        tools.addWidget(self.btn_sim)
        tools.addStretch(1)
        self.status = QLabel("Sin proyecto")
        self.status.setProperty("role", "crumb-current")
        self.pill = QLabel("EN ESPERA")
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
        proj = Panel("Proyectos")
        self.btn_del_proj = QPushButton("Eliminar")
        self.btn_del_proj.setProperty("class", "subtle")
        proj.actions.addWidget(self.btn_del_proj)
        self.projects = HintList("Aún no hay proyectos. Usa Nuevo proyecto.")
        self.projects.setAccessibleName("Proyectos")
        proj.add(self.projects, 1)
        explorer.addWidget(proj, 1)
        ckt = Panel("Circuitos")
        self.circuits = HintList("Elige un proyecto para ver sus circuitos.")
        self.circuits.setAccessibleName("Circuitos")
        ckt.add(self.circuits, 1)
        explorer.addWidget(ckt, 1)
        explorer_w = QWidget()
        explorer_w.setLayout(explorer)
        explorer_w.setFixedWidth(260)
        body.addWidget(explorer_w)

        # Visualization: components / netlist --------------------------------------------
        view = Panel("Circuito")
        self.view_group = QButtonGroup(self)
        self.btn_view_schematic = QPushButton("Esquema")
        self.btn_view_components = QPushButton("Componentes")
        self.btn_view_netlist = QPushButton("Netlist")
        for i, b in enumerate((self.btn_view_schematic, self.btn_view_components, self.btn_view_netlist)):
            b.setProperty("role", "section")
            b.setCheckable(True)
            self.view_group.addButton(b, i)
            view.actions.addWidget(b)
        self.btn_view_schematic.setChecked(True)  # the drawing is the main way to work on a circuit
        self.view_stack = QStackedWidget()
        self.schematic = SchematicPage({t: n for t, n in self.eng.component_types()})
        self._wire_schematic(self.schematic.canvas)
        self.empty = EmptyState("Ningún circuito elegido")
        self.components_table = _table(COMPONENT_COLUMNS, "Componentes")
        self.detail = QTextEdit(readOnly=True)
        self.detail.setObjectName("Output")
        self.detail.setProperty("role", "mono")
        self.detail.setAccessibleName("Netlist")
        for w in (self.empty, self.schematic, self.components_table, self.detail):
            self.view_stack.addWidget(w)
        view.add(self.view_stack, 1)
        body.addWidget(view, 5)

        # Results: topology, calculations, backends ----------------------------------------
        results = Panel("Resultados")
        self.facts = KeyValueList()
        results.add(self.facts)
        self.equiv = KeyValueList()  # Thevenin / Norton of the last port asked for
        self.equiv.hide()
        results.add(self.equiv)
        self.last_calc = Metric("Último cálculo")
        self.last_calc.hide()
        results.add(self.last_calc)
        self.calc_table = _table(CALC_COLUMNS, "Cálculos")
        self.calc_table.setMinimumHeight(120)
        results.add(self.calc_table, 1)
        self.backend_label = QLabel("Motores: sin comprobar")
        self.backend_label.setObjectName("CardStatus")
        self.backend_label.setWordWrap(True)
        results.add(self.backend_label)
        body.addWidget(results, 2)

        self.btn_new_proj.clicked.connect(self._new_project)
        self.btn_del_proj.clicked.connect(self._del_project)
        self.projects.currentRowChanged.connect(lambda _i: self._select_project())
        self.btn_new_ckt.clicked.connect(self._new_circuit)
        self.btn_add_comp.clicked.connect(self._add_component)
        self.btn_equiv.clicked.connect(self._equivalent)
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
        self.btn_equiv.setEnabled(bool(self.project and self.circuit_name))
        for b, tip in ((self.btn_new_ckt, "Elige o crea primero un proyecto"),
                       (self.btn_add_comp, "Elige primero un circuito"),
                       (self.btn_equiv, "Elige un circuito primero")):
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
        v = prompt_form(self, "Project", [("name", "Nombre", "", "text")])
        if not v:
            return
        try:
            self.eng.create_project(v["name"])
        except Exception as e:
            show_ui_error(self, e, "Proyecto")
            return
        self.refresh_projects()

    def _del_project(self) -> None:
        i = self.projects.currentRow()
        if not (0 <= i < len(self._pnames)):
            return
        try:
            self.eng.repo.delete_project(self._pnames[i])
        except Exception as e:
            show_ui_error(self, e, "Eliminar proyecto")
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
            show_ui_error(self, ValueError("elige primero un proyecto"), "Circuito")
            return
        v = prompt_form(self, "Circuit", [("name", "Nombre", "", "text")])
        if not v:
            return
        try:
            self.eng.save_circuit(self.project, self.eng.new_circuit(v["name"]))
        except Exception as e:
            show_ui_error(self, e, "Circuito")
            return
        self._select_project()
        if v["name"] in self._cnames:
            self.circuits.setCurrentRow(self._cnames.index(v["name"]))

    def _add_component(self) -> None:
        if not self.project or not self.circuit_name:
            show_ui_error(self, ValueError("elige un proyecto y un circuito"), "Componente")
            return
        # Step 1: which component. Step 2: only the fields that component needs.
        picked = prompt_form(self, "Component",
                             [("type", "Tipo", [(f"{t} · {name}", t) for t, name in self.eng.component_types()],
                               "combo")], context="Elige el tipo de componente.", primary="Siguiente")
        if not picked:
            return
        spec = self.eng.component_spec(picked["type"])
        circuit = self.eng.repo.load_circuit(self.project, self.circuit_name)
        fields = [("ref", "Referencia", self.eng.next_ref(circuit, spec.type), "text")]
        fields += [(f"pin:{pin}", f"{label} ({pin})", "", "text") for pin, label in spec.pins]
        if spec.value_label:
            fields.append(("value", spec.value_label, spec.value_default, "text"))
        for p in spec.params:
            if p.choices:
                fields.append((f"param:{p.key}", p.label, [(c, c) for c in p.choices], "combo"))
            else:
                fields.append((f"param:{p.key}", p.label, p.default, "text"))
        v = prompt_form(self, "Component", fields, context=spec.name, primary="Añadir")
        if not v:
            return
        pins = {pin: str(v[f"pin:{pin}"]).strip() for pin, _ in spec.pins}
        raw = {p.key: v[f"param:{p.key}"] for p in spec.params}
        try:
            if not all(pins.values()):
                raise ValueError("escribe el nodo de cada terminal (0 es tierra)")
            params = self.eng.make_parameters(spec.type, raw)
            self.eng.add_component(self.project, self.circuit_name, spec.type, v["ref"],
                                   v.get("value", ""), pins, params)
        except Exception as e:
            show_ui_error(self, e, "Componente")
            return
        self._refresh_detail()

    # -- schematic editing -------------------------------------------------------------------
    def _wire_schematic(self, canvas) -> None:
        canvas.place_requested.connect(self._sch_place)
        canvas.moved.connect(lambda ref, x, y: self._edit(S.move, ref, x, y))
        canvas.connect_requested.connect(lambda a, b: self._edit(S.connect, a, b))
        canvas.ground_requested.connect(lambda ref, pin: self._edit(S.ground, ref, pin))
        canvas.detach_requested.connect(lambda ref, pin: self._edit(S.detach, ref, pin))
        canvas.rotate_requested.connect(lambda ref: self._edit(S.rotate, ref))
        canvas.delete_requested.connect(lambda ref: self._edit(S.delete, ref))
        canvas.edit_requested.connect(self._sch_edit)
        canvas.rename_net_requested.connect(self._sch_rename)

    def _edit(self, fn, *args) -> bool:
        """Apply one pure schematic operation to the stored circuit and save the result."""
        if not (self.project and self.circuit_name):
            return False
        try:
            circuit = S.freeze_layout(self.eng.repo.load_circuit(self.project, self.circuit_name))
            new = fn(circuit, *args)
            self.eng.repo.save_circuit(self.project, new)
        except Exception as e:
            show_ui_error(self, e, "Componente")
            self._refresh_detail(keep_view=True)
            return False
        self._refresh_detail(keep_view=True)
        return True

    def _sch_place(self, ctype: str, gx: int, gy: int) -> None:
        spec = self.eng.component_spec(ctype)
        raw = {p.key: p.default for p in spec.params}
        missing = [p for p in spec.params if not raw[p.key]]
        if missing:  # controlled sources: which nodes / which source do they watch?
            v = prompt_form(self, "Component", [(f"param:{p.key}", p.label, "", "text") for p in missing],
                            context=spec.name, primary="Colocar")
            if not v:
                return
            raw.update({p.key: v[f"param:{p.key}"] for p in missing})
        try:
            params = self.eng.make_parameters(ctype, raw)
        except Exception as e:
            show_ui_error(self, e, "Componente")
            return
        self._edit(lambda c: S.place(c, spec, gx, gy, params))

    def _sch_edit(self, ref: str) -> None:
        """Double click: change the value, or the model parameters of a semiconductor."""
        circuit = self.eng.repo.load_circuit(self.project, self.circuit_name)
        comp = next((c for c in circuit.components if c.ref.upper() == ref), None)
        if comp is None:
            return
        spec = self.eng.component_spec(comp.type)
        fields = []
        if spec.value_label:
            fields.append(("value", spec.value_label, comp.value.compact() if comp.value else "", "text"))
        for p in spec.params:
            current = (comp.parameters or {}).get(p.key)
            text = current if isinstance(current, str) else (
                current.value.normalize().__format__("f") if current is not None else p.default)
            fields.append((f"param:{p.key}", p.label,
                           [(c, c) for c in p.choices] if p.choices else text, "combo" if p.choices else "text"))
        if not fields:
            return
        v = prompt_form(self, "Component", fields, context=f"{ref} · {spec.name}", primary="Guardar")
        if not v:
            return
        if spec.value_label:
            self._edit(S.set_value, ref, v["value"])
        if spec.params:
            try:
                params = self.eng.make_parameters(comp.type, {p.key: v[f"param:{p.key}"] for p in spec.params})
            except Exception as e:
                show_ui_error(self, e, "Componente")
                return
            self._edit(S.set_parameters, ref, params)

    def _sch_rename(self, net: str) -> None:
        if net == S.GROUND:
            return
        v = prompt_form(self, "Component", [("name", "Nombre del nodo", "" if S.is_auto_net(net) else net, "text")],
                        context="Un nombre como in u out aparece luego al elegir el nodo de salida.",
                        primary="Nombrar")
        if v and v["name"].strip():
            self._edit(S.rename_net, net, v["name"])

    def _equivalent(self) -> None:
        """Thevenin and Norton equivalents seen from two nets, straight from the exact engine."""
        if not self.project or not self.circuit_name:
            show_ui_error(self, ValueError("elige un proyecto y un circuito"), "Componente")
            return
        circuit = self.eng.repo.load_circuit(self.project, self.circuit_name)
        nets = sorted(circuit.nets)
        if len(nets) < 2:
            show_ui_error(self, ValueError("el circuito necesita al menos dos nodos"), "Componente")
            return
        choices = [(n, n) for n in nets]
        v = prompt_form(self, "Puerto", [("pos", "Terminal + ", choices, "combo"),
                                         ("neg", "Terminal − ", choices, "combo")],
                        context="Nodos entre los que se ve el equivalente.", primary="Calcular")
        if not v:
            return
        r = self.eng.one_port(circuit, v["pos"], v["neg"])
        head = f"Puerto {v['pos']} → {v['neg']}"
        if not r.ok:
            reason = r.diagnostics[0] if r.diagnostics else r.status
            self.equiv.set_rows([(head, "sin equivalente"), ("Estado", r.status), ("Motivo", reason)])
        else:
            rows = [(head, "Thévenin / Norton"), ("Vth", r.v_th), ("Rth", r.r_th),
                    ("In", r.i_n or "no definida"), ("Rn", r.r_n or "no definida"),
                    ("Vth = In·Rth", ("sí (exacto)" if r.equivalent else "no") if r.i_n else "—"),
                    ("Comprobación con cargas", f"{r.loads_passed}/{r.loads_total}")]
            self.equiv.set_rows(rows)
        self.equiv.show()

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
        elif self.btn_view_components.isChecked():
            self.view_stack.setCurrentWidget(self.components_table)
        else:
            self.view_stack.setCurrentWidget(self.schematic)

    def _empty_state(self) -> None:
        self.empty.set_action()
        if not self._pnames:
            self.empty.set("Aún no hay proyectos", "Crea un proyecto para empezar a construir circuitos.")
            self.empty.set_action("Nuevo proyecto", self._new_project)
        elif not self.project:
            self.empty.set("Elige un proyecto", "Elige un proyecto a la izquierda para ver sus circuitos.")
        elif not self._cnames:
            self.empty.set("Este proyecto no tiene circuitos", "Crea un circuito y añade componentes.")
            self.empty.set_action("Nuevo circuito", self._new_circuit)
        else:
            self.empty.set("Elige un circuito", "Elige un circuito para ver sus componentes y su netlist.")

    def _refresh_detail(self, keep_view: bool = False) -> None:
        self.calc_table.setRowCount(0)
        self.last_calc.hide()
        self.equiv.hide()
        self._keep_view = keep_view
        if not self.project or not self.circuit_name:
            self._empty_state()
            self.schematic.canvas.set_circuit(None)
            self.components_table.setRowCount(0)
            self.detail.clear()
            self.facts.set_rows([("Proyecto", self.project or "—")])
            self.status.setText(self.project or "Sin proyecto")
            self._show_view()
            if self.project:
                self._fill_calculations()
            return
        circuit = self.eng.repo.load_circuit(self.project, self.circuit_name)
        warnings = self.eng.circuit_warnings(circuit)
        rows = [("Circuito", self.circuit_name), ("Componentes", str(len(circuit.components))),
                ("Nodos", ", ".join(sorted(circuit.nets)) or "—"),
                ("Topología", "; ".join(warnings) or "correcta")]
        try:
            plan = self.eng.analyze_circuit(circuit)
            topos = [t.topology.value for t in plan.recognized_topologies]
            rows += [("Estructura", plan.classification),
                     ("Reconocido", ", ".join(topos) or "none"),
                     ("Análisis principal", plan.primary_analysis.value if plan.primary_analysis else "none")]
        except Exception as e:
            from academic_core.errors import to_ui_error
            rows.append(("Estructura", f"no disponible ({to_ui_error(e).error_code})"))
        self.facts.set_rows(rows)
        self._fill_components(circuit)
        self.schematic.canvas.set_circuit(circuit, fit=not keep_view)
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
                                        c.value.compact() if c.value else
                                        (str(c.parameters.get("polarity", "modelo")) if c.parameters else "—"),
                                        pins)):
                self.components_table.setItem(r, col, QTableWidgetItem(text))

    def _fill_calculations(self) -> None:
        calcs = self.eng.repo.calculations_of(self.project)[-10:]
        self.calc_table.setRowCount(len(calcs))
        for r, c in enumerate(calcs):
            for col, text in enumerate((c["name"], str(c["value"]), c["unit"], c["digest"][:8])):
                self.calc_table.setItem(r, col, QTableWidgetItem(text))

    # -- calculations ------------------------------------------------------------------------------
    def _calculate(self) -> None:
        v = prompt_form(self, "Calculate",
                        [("equation", "Ecuación (I = V / R)", "I = V / R", "text"),
                         ("inputs", "Datos (V=5 V; R=1 kohm)", "V=5 V; R=1 kohm", "text"),
                         ("name", "Nombre", "", "text")])
        if not v:
            return
        self._set_state(UiState.RUNNING, "EJECUTANDO…")
        try:
            inputs = dict(p.split("=", 1) for p in v["inputs"].split(";") if "=" in p)
            inputs = {k.strip(): val.strip() for k, val in inputs.items()}
            result = self.eng.calculate(inputs, v["equation"],
                                        project=self.project or "",
                                        name=v["name"])
        except Exception as e:
            ui = show_ui_error(self, e, "Calcular")
            self._set_state(UiState.ERROR, f"ERROR {ui.error_code}")
            return
        self._refresh_detail()
        self.last_calc.set_value(result.short())
        self.last_calc.setToolTip(f"digest {result.digest}")
        self.last_calc.show()
        self._set_state(UiState.SUCCESS, "ÉXITO")

    def _backend_status(self) -> None:
        self.backend_label.setText("Motores: " + " · ".join(self.eng.backend_status_lines()))
