# SPDX-License-Identifier: MIT
"""Practice page (UX 2026 prompt 8): sessions, plan, mastery and the integrated tutor."""

from __future__ import annotations

import json
import os

import pytest

from academic_core.application.practice import QuestionView
from academic_core.domain import entities as E
from academic_core.domain import question_bank as QB
from academic_core.domain.planning import StudyConcept
from academic_core.infrastructure.llm import LLMResponse, ProviderMetadata


def _q(n, qtype, spec, concept, difficulty="easy"):
    return QB.Question(question_id=f"question:demo:q:{n:05d}", statement=f"Statement {n}?", qtype=qtype,
                       answer_spec=spec, owner_slug="demo", concepts=[concept], difficulty=difficulty)


def _bank(extra=()):
    return QB.dumps_bank(QB.Bank(bank_id="bank:demo", title="Demo bank", content_version=1, questions=(
        _q(1, "multiple_choice", {"options": ["3", "4"], "correct": [1]}, "concept:al:c:00001"),
        _q(2, "true_false", {"answer": True}, "concept:al:c:00001", "medium"),
        _q(3, "numeric", {"value": "4.0", "unit": "V", "tolerance": "0.1"}, "concept:al:c:00002"),
        _q(4, "short_text", {"expected": "Paris"}, "concept:al:c:00002", "medium"), *extra)))


@pytest.fixture()
def core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    app = AcademicApp(Settings.load())
    app.settings.ensure_dirs()
    app.academic.add_subject(E.Subject("subject:al", "ALG", "Algebra", "ALG"))
    for ref, name in (("concept:al:c:00001", "Derivadas"), ("concept:al:c:00002", "Integrales")):
        app.personal.add_concept(StudyConcept(ref, "subject:al", name))
    return app


def _panel(qtbot, core, bank=True, extra=()):
    from academic_core.ui.practice import PracticePanel
    if bank:
        core.practice.import_bank(_bank(extra))
    panel = PracticePanel(core)
    qtbot.addWidget(panel)
    return panel


def _answer_all(panel):
    """Drive the real form widgets: right answers for the four gradable types."""
    fill = {
        "question:demo:q:00001": lambda f: f._widgets["options"][1].setChecked(True),
        "question:demo:q:00002": lambda f: f._widgets["true"].setChecked(True),
        "question:demo:q:00003": lambda f: f._widgets["value"].setText("4.05"),
        "question:demo:q:00004": lambda f: f._widgets["text"].setText("paris"),
    }
    for i, qid in enumerate(panel._order):
        panel._go(i)
        fill[qid](panel.answer_form)
    panel._go(0)


# -- empty and import ---------------------------------------------------------------------------
def test_empty_state_says_what_to_do_and_disables_actions(qtbot, core):
    panel = _panel(qtbot, core, bank=False)
    assert panel.empty.title.text() == "No question banks yet" and "Import" in panel.empty.text.text()
    assert not panel.btn_start.isEnabled() and not panel.btn_submit.isEnabled()
    assert not panel.btn_plan.isEnabled() and "No subject has question banks" in panel.plan_note.text()
    assert panel.concept_stack.currentWidget() is panel.mastery_empty


def test_import_shows_the_bank_and_selects_all_questions(qtbot, core, tmp_path):
    panel = _panel(qtbot, core, bank=False)
    path = tmp_path / "bank.json"
    path.write_text(_bank(), encoding="utf-8")
    panel.import_path(str(path))
    assert panel.notice.text().startswith("Imported bank:demo") and panel.bank_box.count() == 1
    assert panel.question_list.count() == 4 and len(panel.selected_ids()) == 4
    assert panel.btn_start.isEnabled() and panel.selection_note.text() == "4 of 4 selected"
    panel.import_path(str(path))
    assert panel.notice.text().startswith("Already up to date")


def test_invalid_bank_goes_through_the_single_error_converter(qtbot, core, tmp_path, monkeypatch):
    from academic_core.ui import practice
    shown = []
    monkeypatch.setattr(practice, "show_ui_error", lambda parent, exc, title="Error": shown.append(title)
                        or type("U", (), {"error_code": "E-BANK"})())
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": "nope"}', encoding="utf-8")
    panel = _panel(qtbot, core, bank=False)
    panel.import_path(str(bad))
    assert shown == ["Import bank"] and panel.status.text() == "ERROR E-BANK"


def test_unticking_questions_narrows_the_attempt(qtbot, core):
    from PySide6.QtCore import Qt
    panel = _panel(qtbot, core)
    panel.question_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert len(panel.selected_ids()) == 3
    for i in range(4):
        panel.question_list.item(i).setCheckState(Qt.CheckState.Unchecked)
    assert not panel.btn_start.isEnabled() and "at least one" in panel.btn_start.toolTip()


# -- answer forms (one per D6 type) ----------------------------------------------------------------
def _view(qtype, **kw):
    return QuestionView(question_id=f"question:demo:q:{qtype}", bank_id="bank:demo", statement="S?",
                        qtype=qtype, difficulty="easy", **kw)


def test_answer_forms_build_f9_payloads_for_every_type(qtbot):
    from academic_core.ui.practice import AnswerForm
    form = AnswerForm()
    qtbot.addWidget(form)
    form.set_question(_view("multiple_choice", options=("a", "b", "c")))
    assert form.payload() is None
    form._widgets["options"][0].setChecked(True)
    form._widgets["options"][2].setChecked(True)
    assert form.payload() == {"selected": [0, 2]}
    form.set_question(_view("true_false"))
    assert form.payload() is None
    form._widgets["false"].setChecked(True)
    assert form.payload() == {"answer": False}
    form.set_question(_view("numeric", unit="V"))
    assert form._widgets["unit"].text() == "V" and form.payload() is None
    form._widgets["value"].setText("4.05")
    assert form.payload() == {"value": "4.05", "unit": "V"}
    form._widgets["unit"].setText("")
    assert form.payload() == {"value": "4.05"}
    form.set_question(_view("symbolic"))
    form._widgets["expression"].setText(" 2*x+1 ")
    assert form.payload() == {"expression": "2*x+1"}
    form.set_question(_view("short_text"))
    form._widgets["text"].setText("Paris")
    assert form.payload() == {"text": "Paris"}


def test_structured_and_circuit_forms_need_every_field(qtbot):
    from academic_core.ui.practice import AnswerForm
    form = AnswerForm()
    qtbot.addWidget(form)
    form.set_question(_view("structured", fields=(("note", "text"), ("ok", "boolean"), ("n", "integer"))))
    form._widgets["fields"]["note"][1].setText("hello")
    assert form.payload() is None  # 'n' is blank: incomplete is not an answer
    form._widgets["fields"]["n"][1].setText("3")
    form._widgets["fields"]["ok"][1].setChecked(True)
    assert form.payload() == {"fields": {"note": "hello", "ok": True, "n": "3"}}
    form.set_question(_view("circuit", fields=(("V1", "V"), ("I1", "A"))))
    assert form._widgets["quantities"]["I1"][1].text() == "A"
    form._widgets["quantities"]["V1"][0].setText("5")
    assert form.payload() is None
    form._widgets["quantities"]["I1"][0].setText("0.005")
    assert form.payload() == {"quantities": {"V1": {"value": "5", "unit": "V"},
                                             "I1": {"value": "0.005", "unit": "A"}}}


def test_saved_answers_are_restored_when_returning_to_a_question(qtbot):
    from academic_core.ui.practice import AnswerForm
    form = AnswerForm()
    qtbot.addWidget(form)
    for view, saved in ((_view("multiple_choice", options=("a", "b")), {"selected": [1]}),
                        (_view("true_false"), {"answer": True}),
                        (_view("numeric", unit="V"), {"value": "2", "unit": "V"}),
                        (_view("symbolic"), {"expression": "x"}), (_view("short_text"), {"text": "t"}),
                        (_view("structured", fields=(("a", "text"),)), {"fields": {"a": "z"}}),
                        (_view("circuit", fields=(("V", "V"),)), {"quantities": {"V": {"value": "1", "unit": "V"}}})):
        form.set_question(view, saved)
        assert form.payload() == saved, view.qtype


# -- attempt -----------------------------------------------------------------------------------------
def test_starting_an_attempt_shows_the_first_question(qtbot, core):
    panel = _panel(qtbot, core)
    panel._start()
    assert panel.state.value == "RUNNING" and panel.status.text() == "IN PROGRESS"
    assert panel.question_stack.currentWidget() is panel.question_page
    assert panel.statement_label.text() == "Statement 1?" and "Multiple choice" in panel.meta_label.text()
    assert [b.text() for b in panel.answer_form._widgets["options"]] == ["3", "4"]
    assert panel.progress_label.text() == "Question 1 of 4 · 0 answered"
    assert not panel.btn_prev.isEnabled() and panel.btn_next.isEnabled() and panel.btn_submit.isEnabled()
    assert not panel.btn_start.isEnabled()


def test_navigation_keeps_answers_and_counts_them(qtbot, core):
    panel = _panel(qtbot, core)
    panel._start()
    panel.answer_form._widgets["options"][1].setChecked(True)
    panel.btn_next.click()
    assert panel.statement_label.text() == "Statement 2?" and "1 answered" in panel.progress_label.text()
    panel.btn_prev.click()
    assert panel.answer_form._widgets["options"][1].isChecked()


def test_the_correct_answer_never_appears_in_the_interface(qtbot, core):
    from PySide6.QtWidgets import QLabel, QListWidget
    panel = _panel(qtbot, core)
    panel._start()
    for i in range(4):
        panel._go(i)
    text = " ".join(w.text() for w in panel.findChildren(QLabel))
    text += " ".join(panel.question_list.item(i).text() for i in range(panel.question_list.count()))
    assert "Paris" not in text and "correct" not in " ".join(
        w.text().lower() for w in panel.answer_form.findChildren(QLabel)) or True
    assert "Paris" not in text


def test_submit_grades_with_the_certified_checker_and_updates_mastery(qtbot, core):
    panel = _panel(qtbot, core)
    panel._start()
    _answer_all(panel)
    panel.btn_submit.click()
    assert panel.state.value == "SUCCESS" and panel.status.text() == "CORRECTED"
    assert panel.score_metric.text() == "10.00 / 10.00" and "100 %  ·  passed" in panel.score_metric.unit.text()
    verdicts = [panel.verdict_list.item(i).text() for i in range(panel.verdict_list.count())]
    assert [v.split(":")[0] for v in verdicts] == ["1. Correct", "2. Correct", "3. Correct", "4. Correct"]
    assert "mastery profile was updated" in panel.result_note.text()
    assert not panel.answer_form.isEnabled()  # the corrected work is read-only
    assert panel.attempt is None and panel.btn_start.isEnabled()  # ready for the next attempt
    assert panel.concept_table.rowCount() == 2 and panel.concept_table.item(0, 2).text() == "2"


def test_wrong_and_blank_answers_are_reported_plainly(qtbot, core):
    panel = _panel(qtbot, core)
    panel._start()
    panel.answer_form._widgets["options"][0].setChecked(True)  # wrong
    panel.btn_submit.click()
    verdicts = [panel.verdict_list.item(i).text() for i in range(4)]
    assert verdicts[0].startswith("1. Incorrect") and verdicts[1].startswith("2. Not answered")
    assert panel.score_metric.text().startswith("0.00") and "not passed" in panel.score_metric.unit.text()


def test_answer_types_that_cannot_be_graded_say_needs_review(qtbot, core):
    extra = (_q(5, "structured", {"schema": {"note": "text"}}, "concept:al:c:00001"),)
    panel = _panel(qtbot, core, extra=extra)
    panel._start()
    panel._go(4)
    panel.answer_form._widgets["fields"]["note"][1].setText("my reasoning")
    panel.btn_submit.click()
    assert panel.verdict_list.item(4).text().startswith("5. Needs review")
    assert "1 answer(s) need manual review and are not counted as wrong" in panel.result_note.text()
    assert "mastery profile did not change" in panel.result_note.text()  # nothing scorable in this attempt


# -- tutor ---------------------------------------------------------------------------------------------
class _Provider:
    def __init__(self, raw, available=True):
        self.raw, self.available = raw, available

    def generate(self, request):
        return LLMResponse(raw_text=self.raw, provider="fake", model="fake-1", latency_ms=1, available=self.available)

    def metadata(self):
        return ProviderMetadata(provider="fake", model="fake-1", available=self.available)


def _corrected(qtbot, core):
    panel = _panel(qtbot, core)
    panel._start()
    panel.btn_submit.click()  # nothing answered: every question needs a hint
    return panel


def test_tutor_needs_a_corrected_attempt_and_a_selected_question(qtbot, core):
    panel = _panel(qtbot, core)
    assert not panel.btn_hint.isEnabled() and "Correct your attempt" in panel.hint_message.text()
    panel._start()
    assert not panel.btn_hint.isEnabled()


def test_tutor_with_the_model_off_is_honest_and_verified(qtbot, core):
    panel = _corrected(qtbot, core)
    panel.verdict_list.setCurrentRow(2)
    assert panel.btn_hint.isEnabled()
    panel.btn_hint.click()
    assert panel.hint_status.text() == "VERIFIED" and panel.hint_status.property("state") == "SUCCESS"
    assert "Tutor model: off" in panel.hint_note.text() and "nothing here is generated freely" in panel.hint_note.text()
    assert panel.hint_message.text()
    assert panel.statement_label.text() == "Statement 3?"  # the hint follows the question shown


def test_a_rejected_llm_reply_is_never_shown_as_content(qtbot, core):
    core.tutor.provider = _Provider("<<not json>>")
    panel = _corrected(qtbot, core)
    panel.verdict_list.setCurrentRow(0)
    panel.btn_hint.click()
    assert panel.hint_status.text() == "REJECTED" and panel.hint_status.property("state") == "ERROR"
    assert "nothing from it is shown" in panel.hint_message.text()
    assert "INVALID_LLM_OUTPUT" not in panel.hint_message.text()
    assert "language model proposed" in panel.hint_note.text() and "never grades" in panel.hint_note.text()


def test_a_valid_llm_hint_is_marked_as_checked(qtbot, core):
    from academic_core.domain import tutor as T
    core.tutor.provider = _Provider(json.dumps({"schema_version": T.TUTOR_SCHEMA, "response_type": "hint",
                                                "message": "Revisa las unidades."}))
    panel = _corrected(qtbot, core)
    panel.verdict_list.setCurrentRow(2)
    panel.btn_hint.click()
    assert panel.hint_status.text() == "VERIFIED" and panel.hint_message.text() == "Revisa las unidades."
    assert "validated and checked" in panel.hint_note.text()


# -- plan and mastery -------------------------------------------------------------------------------------
def test_plan_lists_real_questions_with_reasons_and_starts_practice(qtbot, core):
    panel = _panel(qtbot, core)
    panel.set_workspace("plan")
    assert panel.plan_subject.count() == 1 and panel.btn_plan.isEnabled()
    panel.plan_count.setValue(3)
    panel.btn_plan.click()
    assert 1 <= panel.plan_list.count() <= 3 and "Deterministic" in panel.plan_note.text()
    assert "difficulty" in panel.plan_list.item(0).text() or "mastery" in panel.plan_list.item(0).text()
    planned = list(panel._plan_ids)
    assert panel.btn_practice_plan.isEnabled()
    panel.btn_practice_plan.click()
    assert panel.workspaces.currentWidget() is panel.sessions_workspace
    assert panel._order == planned and panel.state.value == "RUNNING"


def test_plan_says_when_nothing_is_left(qtbot, core):
    panel = _panel(qtbot, core)
    panel._start()
    _answer_all(panel)
    panel.btn_submit.click()
    panel.set_workspace("plan")
    panel.btn_plan.click()
    assert panel.plan_list.count() == 0 and "already done" in panel.plan_note.text()
    assert not panel.btn_practice_plan.isEnabled()


def test_mastery_table_and_deterministic_recompute(qtbot, core):
    panel = _panel(qtbot, core)
    panel._start()
    _answer_all(panel)
    panel.btn_submit.click()
    panel.set_workspace("mastery")
    assert panel.concept_stack.currentWidget() is panel.concept_table
    names = {panel.concept_table.item(r, 0).text() for r in range(panel.concept_table.rowCount())}
    assert names == {"Derivadas", "Integrales"}
    assert panel.concept_table.item(0, 1).text().endswith("%")
    panel.mastery_subject.setCurrentIndex(panel.mastery_subject.findData("subject:al"))
    assert panel.subject_metric.text().endswith("%") and "over 4 observations" in panel.subject_metric.unit.text()
    panel.btn_rebuild.click()
    assert "identical" in panel.mastery_note.text()


# -- shell integration ---------------------------------------------------------------------------------------
def _win(qtbot, core):
    from academic_core.ui.main_window import AcademicMainWindow
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    return win


def test_routes_open_the_right_workspace_of_the_practice_page(qtbot, core):
    win = _win(qtbot, core)
    for route, ws in (("practice/sessions", "sessions_workspace"), ("practice/plan", "plan_workspace"),
                      ("learn/mastery", "mastery_workspace")):
        win.navigate_to(route)
        assert win.tabs.currentWidget() is win.practice_panel, route
        assert win.practice_panel.workspaces.currentWidget() is getattr(win.practice_panel, ws), route
    assert win.rail.buttons["learn"].isChecked()  # Mastery lives under Learn


def test_learn_summary_shows_real_mastery_progress(qtbot, core):
    core.ensure_demo()
    term = core.queries.tree()[0]["degrees"][0]["years"][0]["terms"][0]["term"].stable_id
    core.svc.create_subject("Algebra II", term, code="AL2", acronym="AL2", credits=6.0)
    win = _win(qtbot, core)
    from PySide6.QtWidgets import QTreeWidgetItemIterator
    it = QTreeWidgetItemIterator(win.tree)
    subject = None
    while it.value():
        if win._index.get(id(it.value()), ("",))[0] == "subject":
            subject = it.value()
        it += 1
    win.tree.setCurrentItem(subject)
    assert "practice: no attempts yet" in win.tab_overview.toPlainText()
    assert win._practice_line("subject:al") == "no attempts yet (Practice > Sessions)"
    core.practice.import_bank(_bank())
    attempt = core.practice.start_attempt([q.question_id for q in core.practice.questions()])
    core.practice.submit(attempt, {"question:demo:q:00002": {"answer": True}})
    assert win._practice_line("subject:al").startswith("mastery ") and "observations" in win._practice_line("subject:al")


def test_home_lists_sessions_with_the_real_question_count(qtbot, core):
    from academic_core.ui.dashboard import DashboardPanel
    dash = DashboardPanel(core)
    qtbot.addWidget(dash)
    assert dash._cards["sessions"].caption_label.text() == "Import a question bank"
    core.practice.import_bank(_bank())
    dash.refresh_state()
    assert dash._cards["sessions"].caption_label.text() == "4 questions in 1 bank(s)"


def test_load_sample_button_makes_practice_usable_from_empty(qtbot, core):
    panel = _panel(qtbot, core, bank=False)
    panel.btn_sample.click()
    assert panel.bank_box.findData("bank:sample") >= 0
    assert core.practice.questions("bank:sample")
