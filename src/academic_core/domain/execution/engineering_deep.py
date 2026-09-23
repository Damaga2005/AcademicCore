# SPDX-License-Identifier: MIT
"""E0.4 explainable engineering deep observability and resolver retrofit.

Every trace is ONE real execution of a certified engine, with its optional
observer attached when the engine has one (``observer=None`` is inert). The
trace shows only what the engine executed and handed over, or what its own
result carries; nothing is re-solved. E0 to E0.3 traces are unchanged:
these are new operations.

- **``engineering.transient-newton``** (F8-L): the inner Newton of every
  transient attempt. Per iteration it shows x_k, F(x_k), J(x_k) and Δx
  exactly as the integrator used them, α, each real backtracking trial,
  the residual norms and the stop tests. Every attempt carries its LTE and
  its accept/reject decision, and an inner Newton that stopped carries its
  reason and the failing iteration's data. CHECKs: J·Δx + F = 0 on the
  observed data (NUMERIC); observed iterations = ``stats.newton_total``
  (SYMBOLIC); x_(k+1) = x_k + α·Δx is consistent with the next iterate
  (NUMERIC).
- **``engineering.ac-sweep-mna``** (F8-D5 → F8-D3): per frequency, the
  real complex system of that point's ``solve_ac`` (A(jω), b(jω), x(jω),
  FULL up to ``MAX_MATRIX_FULL`` unknowns, else OMITTED + digest) and the
  point's H, |H| and ∠H from ``frequency_response``. CHECKs: A·x = b per
  frequency, |H|² = Re² + Im², the frequency sequence.
- **F8-M**:
  - ``engineering.param-sweep``, ``engineering.worst-case``: every point
    or corner through the sweep driver's observer (initial guess, Newton
    iterations, final state), plus the engine's corner extrema.
  - ``engineering.dc-sensitivity``: the converged point, the certified J,
    dF/dp and dx/dp per parameter (CHECK J·dx/dp + dF/dp = 0, NUMERIC) and
    the engine's observable derivatives.
  - ``engineering.monte-carlo``: the seed, and every sample's sub-seeds,
    sampled parameters, status and observables, with the engine's
    statistics. They come from ``MCResult``, which records them per
    sample; none is re-drawn.
- **F8-P**:
  - ``control.routh``: the exact Routh table rows, first column, sign
    changes, ε / auxiliary-row flags and verdict (``routh_of_tf``), with
    the engine's Durand–Kerner pole inventory as the cross-check.
  - ``dsp.fft``: the samples, the bit-reversed order, each radix-2 stage
    (twiddles used, vector produced) and X[k], with the direct DFT of the
    engine as reference (NUMERIC).
  - ``dsp.sampling``: f_N, the Nyquist rate, the verdict, and the alias.
  - ``rf.reflection``: Γ, |Γ|, VSWR, return loss and mismatch loss, with
    the Smith-chart map z → Γ as an independent engine path (NUMERIC).
  - ``comms.bpsk``: the channel setup and every simulated bit (uniform,
    bit, symbol, noise, received sample, decision) with errors, BER and
    the 5σ criterion.
  - ``satcom.link-budget``: the ``forward_budget`` chain
    EIRP → FSPL → Pr → G/T → C/N0 → C/N → Eb/N0 (every intermediate the
    engine keeps).
- **``lab.run-analysis``** (Virtual Lab, service level): PARAM_SWEEP,
  CORNERS, SENS_DC and MONTE_CARLO runs re-observed on the run's own
  working circuit, with CHECK = the recorded result.

Boundedness: matrices FULL up to 8×8 (OMITTED + SHA-256 above); DC points
and frequencies ≤ 500; Monte Carlo samples listed ≤ ``MAX_SAMPLES``; bits
listed ≤ ``MAX_BITS``; FFT stages listed up to N = ``MAX_FFT_SHOWN``.
Optional detail events share the E0.3 deterministic budget, which ends in
an explicit ``TRACE_TRUNCATED``.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction

from academic_core.domain.execution import analog as ana
from academic_core.domain.execution import analog_detail as det
from academic_core.domain.execution import newton as nwt
from academic_core.domain.execution.model import EventKind, ExecutionTrace, TraceRecorder, TraceValue, _invalid
from academic_core.domain.execution.verification import NONE, NUMERIC, SYMBOLIC, labelled
from academic_core.errors import UnsupportedError, ValidationError

TRANSIENT_NEWTON = "engineering.transient-newton"
AC_SWEEP_MNA = "engineering.ac-sweep-mna"
PARAM_SWEEP = "engineering.param-sweep"
WORST_CASE = "engineering.worst-case"
DC_SENSITIVITY = "engineering.dc-sensitivity"
MONTE_CARLO = "engineering.monte-carlo"
ROUTH = "control.routh"
FFT = "dsp.fft"
SAMPLING = "dsp.sampling"
REFLECTION = "rf.reflection"
BPSK = "comms.bpsk"
LINK_BUDGET = "satcom.link-budget"
LAB_ANALYSIS = "lab.run-analysis"
OPERATIONS = (TRANSIENT_NEWTON, AC_SWEEP_MNA, PARAM_SWEEP, WORST_CASE, DC_SENSITIVITY, MONTE_CARLO, ROUTH, FFT,
              SAMPLING, REFLECTION, BPSK, LINK_BUDGET)

MAX_VECTOR_SHOWN = 4  # x_k, F, Δx and J value by value up to 4 unknowns (as E0.1-R+ F8-H)
MAX_SAMPLES = 200  # Monte Carlo samples listed one by one
MAX_BITS = 64  # BPSK bits listed one by one
MAX_FFT_SHOWN = 16  # FFT stages listed entry by entry up to N = 16
MAX_PARAMS = 8  # sensitivity / worst-case parameters
LINEAR_TOL = Decimal("1e-40")
FFT_TOL = Decimal("1e-40")
STEP_TOL = Decimal("1e-40")


def _cxv(z) -> TraceValue:
    return TraceValue.of_text(det._cx(z))


def _fail(rec: TraceRecorder, exc: BaseException) -> None:
    rec.fail(exc, "La ejecución se detuvo", refs=tuple(r for r in (rec.last,) if r))


def _six(v: Decimal) -> Decimal:
    return det._six(v)


def _vectors(labels: tuple, x, f, jac, dx) -> tuple:
    """x_k, F(x_k), J(x_k) and Δx value by value (bounded display; above it, a digest of J)."""
    n = len(x)
    names = tuple(det._lab(lab) for lab in labels)
    if n > MAX_VECTOR_SHOWN:
        return (("jacobian", TraceValue.of_text(
            f"detalle omitido: sistema {n}×{n} mayor que {MAX_VECTOR_SHOWN}×{MAX_VECTOR_SHOWN}")),
            ("jacobian_digest", TraceValue.of_text(_real_digest(jac))))
    out = [(f"x_k.{names[i]}", ana._dec(x[i])) for i in range(n)]
    out += [(f"F_k.{names[i]}", ana._dec(f[i])) for i in range(n)]
    if dx is not None:
        out += [(f"dx.{names[i]}", ana._dec(dx[i])) for i in range(n)]
    out += [(f"J.{names[i]}.{names[j]}", ana._dec(jac[i][j])) for i in range(n) for j in range(n)]
    return tuple(out)


def _real_digest(rows) -> str:
    import hashlib
    return hashlib.sha256(";".join(",".join(str(v) for v in row) for row in rows).encode()).hexdigest()


def _newton_residual(rows) -> Decimal:
    """max over observed iterations of |J·Δx + F| / scale (80 digits): the linear step as the solver took it."""
    worst = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 80
        for jac, dx, f in rows:
            for i, row in enumerate(jac):
                lhs = sum((row[j] * dx[j] for j in range(len(dx))), Decimal(0)) + f[i]
                scale = max([Decimal(1)] + [abs(v) for v in row] + [abs(v) for v in dx])
                worst = max(worst, abs(lhs) / scale)
    return worst


def _bounded(worst: Decimal) -> tuple:
    bound = worst != 0 and worst.adjusted() < -150
    return (Decimal("1E-150") if bound else _six(worst)), bound


# ---------------------------------------------------------------- F8-L transient: the inner Newton

def _newton_rows(rec, prev, step_title, labels, newton, budget, failure=None):
    rows = []
    for (k, alpha, peak, kcl, aux, res_ok, step_ok, x, f, jac, dx, trials) in newton:
        rows.append((jac, dx, f))
        if len(trials) > 1:
            for n, (a, norm, accepted) in enumerate(trials, start=1):
                title = f"{step_title} · Newton {k} · backtracking {n}: α = {a}"
                values = (("alpha", ana._dec(a)), ("trial_residual", ana._dec(norm) if norm is not None else
                                                   TraceValue.of_text("no finito")),
                          ("decision", TraceValue.of_text("aceptado" if accepted else "rechazado")),
                          ("reason", TraceValue.of_text("‖F‖ disminuye" if accepted else "‖F‖ no disminuye")))
                if budget.take(title, values):
                    prev = rec.event(EventKind.STEP, title[:512], refs=(prev,), values=values,
                                     formula="x_prueba = x_k + α·Δx;  aceptar si ‖F(x_prueba)‖ < ‖F(x_k)‖")
        values = (("alpha", ana._dec(alpha)), ("step_peak", ana._dec(peak)), ("kcl_residual", ana._dec(kcl)),
                  ("aux_residual", ana._dec(aux)), ("res_ok", TraceValue.of_text("sí" if res_ok else "no")),
                  ("step_ok", TraceValue.of_text("sí" if step_ok else "no"))) + _vectors(labels, x, f, jac, dx)
        title = f"{step_title} · Newton {k}"
        formula = "J(x_k)·Δx = −F(x_k);  x_(k+1) = x_k + α·Δx;  parar si res_ok y step_ok"
        if budget.take(title, values[:64], formula):
            prev = rec.event(EventKind.STEP, title[:512], refs=(prev,), formula=formula, values=values[:64],
                             why="Iteración del Newton interno del integrador con el jacobiano que realmente usó.")
    if failure is not None and failure[0] is not None:
        reason, data = failure
        values = [("reason", TraceValue.of_text(reason[:512]))]
        if data is not None:
            k, x, f, jac, dx, trials = data
            values += [("iteration", TraceValue.of_number(k)), ("trials", TraceValue.of_number(len(trials)))]
            values += list(_vectors(labels, x, f, jac, dx))
            if dx is not None:
                rows.append((jac, dx, f))
        title = f"{step_title} · Newton sin convergencia"
        if budget.take(title, tuple(values[:64])):
            prev = rec.event(EventKind.WARNING, title[:512], refs=(prev,), values=tuple(values[:64]),
                             why=f"El Newton interno se detuvo: {reason}."[:512])
    return prev, rows


def explain_transient_newton(spec: str, method: str, tstop: str, h_init: str, h_min: str, h_max: str,
                             reltol: str = "1e-3", abstol: str = "1e-6", adaptive: bool = True,
                             **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.mna.transient import TransientConfig, solve_transient

    rec = TraceRecorder(TRANSIENT_NEWTON)
    ids = ana._circuit(rec, spec, limits)
    fields = (("method", method), ("tstop", tstop), ("h_init", h_init), ("h_min", h_min), ("h_max", h_max),
              ("reltol", reltol), ("abstol", abstol))
    det._text_inputs(rec, fields, "Transitorio")
    if not isinstance(adaptive, bool):
        raise _invalid("INVALID_INPUT", "adaptive must be a bool")
    rec.input("adaptive", TraceValue.of_text("true" if adaptive else "false"), "Transitorio: paso adaptativo")
    try:
        circuit, read = ana._read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        config = TransientConfig(method, *(ana._decimal(v, n) for n, v in fields[1:]), adaptive=adaptive)
        obs = det._TransientObserver()
        result = solve_transient(circuit, config, observer=obs)
        if obs.start is None:
            rec.event(EventKind.WARNING, "integration method details unavailable", refs=(read,),
                      why="El motor se detuvo antes de iniciar la integración.")
            raise ana._status_error(result.status.value, result.diagnostics)
        s = obs.start
        labels = s["unknowns"]
        prev = rec.event(EventKind.STEP, f"Método de integración: {det.METHODS.get(s['method'], s['method'])}",
                         refs=(read,), formula=f"orden {s['order']}; Newton amortiguado en cada t_(n+1)",
                         values=(("method", TraceValue.of_text(s["method"])),
                                 ("adaptive", TraceValue.of_text("sí" if s["adaptive"] else "no")),
                                 ("unknowns", TraceValue.of_text(", ".join(labels)[:512]))))
        budget = det._Budget()
        rows_all, total_it = [], 0
        for kind, a in obs.attempts:
            total_it += a["iterations"]
            if kind == "accept":
                title = f"Paso {a['index']}: t = {a['t_n']} → {a['t_next']} s"
                values = (("t_n", ana._dec(a["t_n"])), ("dt", ana._dec(a["h"])), ("E_max", det._num(a["e_max"])),
                          ("newton_iterations", TraceValue.of_number(a["iterations"])),
                          ("decision", TraceValue.of_text("aceptado")))
                values += det._vector("pred", labels, a["predictor"], MAX_VECTOR_SHOWN)
                values += det._vector("x_next", labels, a["x_next"], MAX_VECTOR_SHOWN)
                failure, short = None, f"Paso {a['index']}"
            else:
                failure, short = a["newton_failure"], f"Intento en t = {a['t_n']} s"
                stop = a["retry_h"] is None
                title = (f"Intento fallido en t = {a['t_n']} s (Δt = {a['h']})" if stop else
                         f"Intento rechazado en t = {a['t_n']} s (Δt = {a['h']})")
                values = (("cause", TraceValue.of_text(a["cause"])), ("dt_tried", ana._dec(a["h"])),
                          ("retry_dt", det._num(a["retry_h"])), ("E_max", det._num(a["e_max"])),
                          ("newton_iterations", TraceValue.of_number(a["iterations"])),
                          ("decision", TraceValue.of_text("la integración se detiene" if stop else "rechazado")))
            if budget.take(title, values):
                prev = rec.event(EventKind.STEP if kind == "accept" else EventKind.DECISION, title[:512],
                                 refs=(prev,), values=values[:64],
                                 formula="predictor → Newton (F, J, Δx, α) → LTE → aceptar / rechazar")
            prev, rows = _newton_rows(rec, prev, short, labels, a["newton"], budget, failure)
            rows_all += rows
        prev = budget.close(rec, prev)
        if result.status.value != "completed":
            raise ana._status_error(result.status.value, result.diagnostics)
        res = rec.event(EventKind.RESULT, "Transitorio completado", refs=(prev,),
                        values=(("samples", TraceValue.of_number(len(result.times))),
                                ("newton_total", TraceValue.of_number(total_it))),
                        result=TraceValue.of_text(f"COMPLETED: {len(result.times)} instantes"))
        stats = result.stats or {}
        rec.check("iteraciones de Newton observadas = stats.newton_total", TraceValue.of_number(total_it),
                  TraceValue.of_number(stats.get("newton_total", 0)), total_it == stats.get("newton_total"),
                  refs=(res,), detail=labelled("igualdad exacta de enteros", SYMBOLIC),
                  title="Comprobación: iteraciones de Newton")
        worst, bound = _bounded(_newton_residual(rows_all))
        rec.check("J·Δx + F = 0 con los datos observados" + (" (cota superior)" if bound else ""),
                  TraceValue.of_number(worst), TraceValue.of_number(Decimal(0)),
                  worst <= LINEAR_TOL if rows_all else None, refs=(res,), tolerance=TraceValue.of_number(LINEAR_TOL),
                  detail=labelled("máximo relativo sobre todas las iteraciones observadas",
                                  NUMERIC if rows_all else NONE),
                  title="Comprobación: el sistema lineal de Newton")
        chain = _step_chain(obs)
        rec.check("x_(k+1) = x_k + α·Δx coincide con el iterado siguiente", TraceValue.of_number(chain),
                  TraceValue.of_number(Decimal(0)), chain <= STEP_TOL if rows_all else None, refs=(res,),
                  tolerance=TraceValue.of_number(STEP_TOL),
                  detail=labelled("con x_k, α y Δx observados (80 dígitos)", NUMERIC if rows_all else NONE),
                  title="Comprobación: continuidad de Newton")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


def _step_chain(obs) -> Decimal:
    """max |x_k + α·Δx − x_(k+1)| over consecutive observed iterates (and the committed x_(n+1) for the last one)."""
    worst = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 80
        for kind, a in obs.attempts:
            newton = a["newton"]
            targets = [row[7] for row in newton[1:]] + ([a["x_next"]] if kind == "accept" else [])
            for row, target in zip(newton, targets):
                alpha, x, dx = row[1], row[7], row[10]
                for xi, di, ti in zip(x, dx, target):
                    worst = max(worst, abs(xi + alpha * di - ti) / max(Decimal(1), abs(ti)))
    return _six(worst)


# ---------------------------------------------------------------- F8-D5 AC sweep with the matrix of every frequency

class _SweepACObserver:
    def __init__(self):
        self.points: list = []

    def sweep_frequency(self, index, frequency_hz):
        self.points.append(dict(index=index, f=frequency_hz, system=None, outcome=None))

    def ac_system(self, unknowns, matrix, rhs, kind, frequency_hz, omega):
        self.points[-1]["system"] = (tuple(unknowns), tuple(matrix), tuple(rhs), kind, frequency_hz, omega)

    def ac_outcome(self, status, mode, rank, solution, residual_norm, backward_error):
        self.points[-1]["outcome"] = (status, mode, rank, solution, residual_norm, backward_error)


def explain_ac_sweep_mna(spec: str, source: str, output_p: str, output_n: str, frequencies: str,
                         **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.ac.response import ResponseDefinition, frequency_response, voltage_between

    rec = TraceRecorder(AC_SWEEP_MNA)
    ids = ana._circuit(rec, spec, limits)
    det._text_inputs(rec, (("source", source), ("output_p", output_p), ("output_n", output_n),
                           ("frequencies", frequencies)), "Barrido AC")
    try:
        freqs = det._parse_frequencies(frequencies)
        circuit, read = ana._read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        src = {c.ref.upper(): c for c in circuit.components}.get(source.upper())
        if src is None or src.type.upper() not in ("V", "I"):
            raise _invalid("INVALID_INPUT", f"input source {source[:16]!r} must be a V/I source of the circuit")
        plus, minus = src.pins.get("+", src.pins.get("1", "")), src.pins.get("-", src.pins.get("2", ""))
        definition = ResponseDefinition("transfer", (voltage_between(plus, minus),
                                                     voltage_between(output_p, output_n), src.ref))
        obs = _SweepACObserver()
        sweep = frequency_response(circuit, definition, freqs, observer=obs)
        prev = rec.event(EventKind.STEP, "Barrido en frecuencia (sistema MNA por punto)", refs=(read,),
                         formula=f"por cada f: A(jω)·x = b → H(jω) = V({output_p},{output_n}) / V({plus},{minus})",
                         values=(("points", TraceValue.of_number(len(freqs))),))
        budget, worst_axb, rows, exact_all = det._Budget(), Decimal(0), [], True
        axb_ok = True
        for point, sp in zip(obs.points, sweep.points):
            k, sysm = point["index"], point["system"]
            if sysm is None:
                prev = rec.event(EventKind.WARNING, f"f{k}: matrix_detail = UNAVAILABLE", refs=(prev,),
                                 why=f"El motor no ensambló el sistema en este punto: {sp.diagnostic}"[:512])
                continue
            labels, matrix, rhs, kind, f_hz, omega = sysm
            n = len(labels)
            full = n <= det.MAX_MATRIX_FULL
            title = f"f{k} = {f_hz} Hz: A(jω)" + ("" if full else " (detalle omitido)")
            values = (tuple((f"A.{i}.{j}", _cxv(matrix[i][j])) for i in range(n) for j in range(n)) if full else
                      (("matrix_detail", TraceValue.of_text("OMITTED")), ("size", TraceValue.of_number(n)),
                       ("digest", TraceValue.of_text(det._digest(matrix)))))
            if budget.take(title, values):
                prev = rec.event(EventKind.STEP, title, refs=(prev,), values=values,
                                 formula="matriz compleja que solve_ac pasó al resolvedor en esta frecuencia")
            status, mode, _rank, x, _res, _be = point["outcome"]
            vb = (("omega", ana._dec(omega)),) + tuple((f"b.{i}", _cxv(v)) for i, v in enumerate(rhs[:20]))
            vx = tuple((f"x.{det._lab(labels[i])}", _cxv(x[i])) for i in range(min(n, 20))) if x else ()
            title = f"f{k}: b(jω) y x(jω)"
            if budget.take(title, vb + vx):
                prev = rec.event(EventKind.STEP, title, refs=(prev,), values=(vb + vx)[:64],
                                 why=f"Excitación y solución del resolvedor ({status}, modo {mode}).")
            if x:
                worst, ok = det._axb(matrix, rhs, x, mode == "exact")
                exact_all = exact_all and mode == "exact"
                axb_ok = axb_ok and ok
                if isinstance(worst, Fraction):
                    worst = Decimal(worst.numerator) / Decimal(worst.denominator)
                worst_axb = max(worst_axb, worst)
            if sp.value is not None and sp.value.value is not None:
                h = sp.value.value
                mag, arg = sp.value.magnitude(), sp.value.phase()
                rows.append((mag, h.re, h.im))
                prev = rec.event(EventKind.STEP, f"f{k}: H(jω)", refs=(prev,),
                                 values=(("re_H", det._num(h.re)), ("im_H", det._num(h.im)), ("abs_H", ana._dec(mag)),
                                         ("arg_H", ana._dec(arg)), ("status", TraceValue.of_text(sp.status.value))))
        prev = budget.close(rec, prev)
        res = rec.event(EventKind.RESULT, "Respuesta en frecuencia", refs=(prev,),
                        values=(("points", TraceValue.of_number(len(sweep.points))),
                                ("digest", TraceValue.of_text(sweep.digest))),
                        result=TraceValue.of_text(f"{sweep.status}: {len(sweep.points)} frecuencias"))
        rec.check("A·x = b en cada frecuencia", TraceValue.of_number(_six(worst_axb)), TraceValue.of_number(Decimal(0)),
                  axb_ok, refs=(res,), tolerance=None if exact_all else TraceValue.of_number(det.AXB_TOL),
                  detail=labelled("aritmética racional exacta" if exact_all else "residuo relativo por fila, 80 dígitos",
                                  SYMBOLIC if exact_all else NUMERIC), title="Comprobación: A·x = b por frecuencia")
        det._ac_sweep_checks(rec, sweep, freqs, rows, res)
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- F8-M: parameter sweep, corners, sensitivity, MC

def _addresses(text: str) -> tuple:
    from academic_core.domain.engineering.mna.analysis import ParamAddress
    items = [t.strip() for t in text.split(",") if t.strip()]
    if not items or len(items) > MAX_PARAMS:
        raise _invalid("INVALID_LIMIT", f"give 1..{MAX_PARAMS} parameters (REF or REF.field) separated by commas")
    out = []
    for t in items:
        ref, _sep, fld = t.partition(".")
        out.append(ParamAddress(ref, fld or "value"))
    return tuple(out)


def _observables(text: str) -> tuple:
    from academic_core.domain.engineering.mna.analysis import ObservableSpec
    return tuple(ObservableSpec("node_voltage", n.strip()) for n in text.split(",") if n.strip())


def _points_trace(rec, read, header: str, why: str, run, n_points: int):
    """Header + every observed point (the E0.3 renderer) for a sweep-driver engine run."""
    if n_points > det.MAX_DETAIL_POINTS:
        raise _invalid("INVALID_LIMIT", f"at most {det.MAX_DETAIL_POINTS} points are traced (got {n_points})")
    head = rec.event(EventKind.STEP, header, refs=(read,), why=why, values=(("points", TraceValue.of_number(n_points)),))
    obs = det._SweepObserver()
    result = run(obs)
    return result, obs, head


def explain_param_sweep(spec: str, target: str, start: str, stop: str, step: str, observe: str = "",
                        warm_start: bool = True, **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.mna.analysis import GridSpec, ParamSweepConfig, expand_grid, solve_param_sweep

    rec = TraceRecorder(PARAM_SWEEP)
    ids = ana._circuit(rec, spec, limits)
    det._text_inputs(rec, (("target", target), ("start", start), ("stop", stop), ("step", step),
                           ("observe", observe)), "Barrido de parámetro")
    if not isinstance(warm_start, bool):
        raise _invalid("INVALID_INPUT", "warm_start must be a bool")
    rec.input("warm_start", TraceValue.of_text("true" if warm_start else "false"), "Arranque en caliente")
    try:
        circuit, read = ana._read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        (addr,) = _addresses(target)[:1]
        grid = GridSpec.linear(ana._decimal(start, "start"), ana._decimal(stop, "stop"), ana._decimal(step, "step"))
        config = ParamSweepConfig("grid", target=addr, grid=grid, observables=_observables(observe),
                                  warm_start=warm_start)
        try:
            count = len(expand_grid(grid))
        except ValueError:
            count = 0
        result, obs, head = _points_trace(
            rec, read, f"Barrido de {addr.key}",
            "M2 (F8-M): el motor sustituye el parámetro en cada punto y resuelve el punto de operación (F8-H).",
            lambda o: solve_param_sweep(circuit, config, observer=o), count)
        points, last, facts = det._render_points(rec, result.points, obs, head, det._Budget())
        if result.status.value != "completed":
            raise ana._status_error(result.status.value, result.diagnostics or ("sweep did not complete",))
        res = rec.event(EventKind.RESULT, "Barrido de parámetro completado", refs=(last,),
                        values=(("points", TraceValue.of_number(len(result.points))),
                                ("digest", TraceValue.of_text(result.digest or "-"))),
                        result=TraceValue.of_text(f"{result.status.value}: {len(result.points)} puntos"))
        det._sweep_checks(rec, result.points, facts, res)
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


def _corner_entries(text: str) -> tuple:
    """``R1=900:1100, R2.value=1.8k:2.2k`` → ((ParamAddress, low, high), …) (engine coerces the values)."""
    from academic_core.domain.engineering.mna.analysis import ParamAddress
    items = [t.strip() for t in text.split(",") if t.strip()]
    if not items or len(items) > MAX_PARAMS:
        raise _invalid("INVALID_LIMIT", f"give 1..{MAX_PARAMS} entries REF=low:high")
    out = []
    for t in items:
        name, sep, rng = t.partition("=")
        lo, sep2, hi = rng.partition(":")
        if not sep or not sep2:
            raise _invalid("INVALID_INPUT", f"bad corner entry {t[:32]!r} (REF=low:high)")
        ref, _s, fld = name.strip().partition(".")
        out.append((ParamAddress(ref, fld or "value"), ana._decimal(lo.strip(), "low"), ana._decimal(hi.strip(), "high")))
    return tuple(out)


def explain_worst_case(spec: str, corners: str, observe: str, warm_start: bool = True, **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.mna.analysis import WorstCaseConfig, solve_worst_case

    rec = TraceRecorder(WORST_CASE)
    ids = ana._circuit(rec, spec, limits)
    det._text_inputs(rec, (("corners", corners), ("observe", observe)), "Peor caso")
    if not isinstance(warm_start, bool):
        raise _invalid("INVALID_INPUT", "warm_start must be a bool")
    rec.input("warm_start", TraceValue.of_text("true" if warm_start else "false"), "Arranque en caliente")
    try:
        circuit, read = ana._read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        entries = _corner_entries(corners)
        config = WorstCaseConfig(entries, _observables(observe), warm_start)
        result, obs, head = _points_trace(
            rec, read, f"Esquinas: 2^{len(entries)} combinaciones",
            "M3 (F8-M): el motor enumera todas las esquinas low/high (orden por clave) y resuelve cada una.",
            lambda o: solve_worst_case(circuit, config, observer=o), 2 ** len(entries))
        points, last, facts = det._render_points(rec, result.corners, obs, head, det._Budget())
        if result.status.value not in ("completed",):
            raise ana._status_error(result.status.value, result.diagnostics or ("worst case did not complete",))
        for key, ext in sorted(result.extrema.items()):
            values = []
            for side in ("min", "max"):
                e = ext.get(side)
                if e:
                    values += [(f"{side}.value", ana._dec(e["value"])),
                               (f"{side}.corner", TraceValue.of_text(str(e["arg_corner"])[:512])),
                               (f"{side}.index", TraceValue.of_number(e["arg_corner_index"]))]
            last = rec.event(EventKind.STEP, f"Extremos de {key} sobre las esquinas", refs=(last,),
                             why="Reducción del motor: mínimo y máximo sobre las esquinas evaluadas (no global).",
                             values=tuple(values))
        res = rec.event(EventKind.RESULT, "Peor caso por esquinas", refs=(last,),
                        values=(("corners", TraceValue.of_number(len(result.corners))),
                                ("digest", TraceValue.of_text(result.digest or "-"))),
                        result=TraceValue.of_text(f"{result.status.value}: {len(result.corners)} esquinas"))
        det._sweep_checks(rec, result.corners, facts, res)
        same = all(result.extrema[k][side]["value"] == ([p for p in result.corners if p.index ==
                                                          result.extrema[k][side]["arg_corner_index"]][0]
                                                         .observables[k])
                   for k in result.extrema for side in ("min", "max") if result.extrema[k][side])
        rec.check("cada extremo es el valor de su esquina", TraceValue.of_text("sí" if same else "no"),
                  TraceValue.of_text("sí"), same, refs=(res,),
                  detail=labelled("igualdad exacta con el observable de la esquina", SYMBOLIC),
                  title="Comprobación: extremos")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


class _SensitivityObserver:
    def __init__(self):
        self.system = None
        self.params: list = []

    def sensitivity_system(self, unknowns, x, jac):
        self.system = (tuple(unknowns), tuple(x), tuple(jac))

    def sensitivity_parameter(self, key, df, dx):
        self.params.append((key, tuple(df), tuple(dx)))


def _sensitivity_events(rec, circuit, config, read):
    from academic_core.domain.engineering.mna.sensitivity import solve_dc_sensitivity

    obs = _SensitivityObserver()
    result = solve_dc_sensitivity(circuit, config, observer=obs)
    if obs.system is None:
        rec.event(EventKind.WARNING, "Jacobian details unavailable", refs=(read,),
                  why="El motor terminó antes de usar el jacobiano del punto convergido.")
        raise ana._status_error(result.status.value, result.diagnostics)
    labels, x, jac = obs.system
    n = len(labels)
    names = tuple(det._lab(lab) for lab in labels)
    values = tuple((f"x.{names[i]}", ana._dec(x[i])) for i in range(min(n, 24)))
    values += (tuple((f"J.{names[i]}.{names[j]}", ana._dec(jac[i][j])) for i in range(n) for j in range(n))
               if n <= 6 else (("jacobian", TraceValue.of_text(f"detalle omitido ({n}×{n})")),
                               ("jacobian_digest", TraceValue.of_text(_real_digest(jac)))))
    prev = rec.event(EventKind.STEP, "Punto convergido y jacobiano certificado", refs=(read,),
                     formula="J(x*)·dx/dp = −dF/dp (una resolución por parámetro)",
                     why="El motor M4 reutiliza el jacobiano del Newton en x* (sin diferencias finitas).",
                     values=values[:64])
    rows = []
    for key, df, dx in obs.params:
        rows.append((jac, dx, df))
        vals = tuple((f"dF_dp.{names[i]}", ana._dec(df[i])) for i in range(min(n, 24)))
        vals += tuple((f"dx_dp.{names[i]}", ana._dec(dx[i])) for i in range(min(n, 24)))
        prev = rec.event(EventKind.STEP, f"Parámetro {key}", refs=(prev,), values=vals[:64],
                         formula="dF/dp analítico (estampas y dispositivos) → dx/dp = −J⁻¹·dF/dp",
                         why="Vectores que el motor construyó y resolvió para este parámetro.")
    return result, prev, rows


def explain_dc_sensitivity(spec: str, parameters: str, observe: str = "", **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.mna.sensitivity import SensitivityConfig

    rec = TraceRecorder(DC_SENSITIVITY)
    ids = ana._circuit(rec, spec, limits)
    det._text_inputs(rec, (("parameters", parameters), ("observe", observe)), "Sensibilidad")
    try:
        circuit, read = ana._read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        config = SensitivityConfig(_addresses(parameters), _observables(observe))
        result, prev, rows = _sensitivity_events(rec, circuit, config, read)
        prev = _sensitivity_result(rec, result, prev)
        if result.status.value != "completed":
            raise ana._status_error(result.status.value, result.diagnostics)
        res = rec.event(EventKind.RESULT, "Sensibilidades DC", refs=(prev,),
                        values=(("digest", TraceValue.of_text(result.digest or "-")),),
                        result=TraceValue.of_text(f"{result.status.value}: {len(rows)} parámetros"))
        _sensitivity_check(rec, rows, res)
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


def _sensitivity_result(rec, result, prev):
    for okey, rec_ in sorted((result.observables or {}).items()):
        vals = [("value", ana._dec(rec_["value"]))]
        vals += [(f"d.{det._lab(p)}", ana._dec(item["derivative"])) for p, item in sorted(rec_["sensitivities"].items())]
        prev = rec.event(EventKind.STEP, f"Observable {okey}", refs=(prev,), values=tuple(vals[:64]),
                         formula="d(obs)/dp = ∇obs · dx/dp + ∂obs/∂p (motor)")
    return prev


def _sensitivity_check(rec, rows, res):
    worst, bound = _bounded(_newton_residual(rows))
    rec.check("J·dx/dp + dF/dp = 0 con los vectores observados", TraceValue.of_number(worst),
              TraceValue.of_number(Decimal(0)), worst <= LINEAR_TOL if rows else None, refs=(res,),
              tolerance=TraceValue.of_number(LINEAR_TOL),
              detail=labelled("residuo relativo máximo (80 dígitos)", NUMERIC if rows else NONE),
              title="Comprobación: sistema de sensibilidad")


def _distributions(text: str) -> tuple:
    """``R1=uniform:900:1100, R2=normal:2000:50:1800:2200`` → ((ParamAddress, dist), …)."""
    from academic_core.domain.engineering.mna.analysis import NormalDist, ParamAddress, UniformDist
    items = [t.strip() for t in text.split(",") if t.strip()]
    if not items or len(items) > MAX_PARAMS:
        raise _invalid("INVALID_LIMIT", f"give 1..{MAX_PARAMS} distributions")
    out = []
    for t in items:
        name, sep, rest = t.partition("=")
        parts = rest.split(":")
        ref, _s, fld = name.strip().partition(".")
        addr = ParamAddress(ref, fld or "value")
        if not sep or parts[0] not in ("uniform", "normal"):
            raise _invalid("INVALID_INPUT", f"bad distribution {t[:40]!r}")
        nums = [ana._decimal(p.strip(), "distribution") for p in parts[1:]]
        if parts[0] == "uniform" and len(nums) == 2:
            out.append((addr, UniformDist(*nums)))
        elif parts[0] == "normal" and len(nums) == 4:
            out.append((addr, NormalDist(*nums)))
        else:
            raise _invalid("INVALID_INPUT", f"bad distribution {t[:40]!r}")
    return tuple(out)


def _mc_events(rec, result, prev, seed):
    prev = rec.event(EventKind.STEP, "Semilla y plan de muestreo", refs=(prev,),
                     formula="Random(seed) maestro → una sub-semilla por (muestra, parámetro) → Random(sub) → muestra",
                     why=("Semántica determinista del motor M5: la misma semilla produce exactamente las mismas "
                          "muestras; no hay semilla implícita."),
                     values=(("seed", TraceValue.of_number(seed)),
                             ("plan_digest", TraceValue.of_text(result.plan_digest or "-")),
                             ("samples", TraceValue.of_number(len(result.iterations)))))
    for it in result.iterations[:MAX_SAMPLES]:
        values = [("status", TraceValue.of_text(it.status)), ("init_mode", TraceValue.of_text(it.init_mode)),
                  ("iterations", TraceValue.of_number(it.iterations) if it.iterations is not None
                   else TraceValue.of_text("-"))]
        values += [(f"sub_seed.{k}", TraceValue.of_text(str(s))) for k, s in enumerate(it.sub_seeds[:8])]
        values += [(f"param.{det._lab(k)}", ana._dec(v)) for k, v in it.parameters[:8]]
        values += [(f"obs.{det._lab(k)}", ana._dec(v)) for k, v in sorted(it.observables.items())[:16]]
        prev = rec.event(EventKind.STEP if it.status == "ok" else EventKind.WARNING, f"Muestra {it.index}",
                         refs=(prev,), values=tuple(values[:64]),
                         why=("Muestra producida y resuelta en frío por el motor." if it.status == "ok" else
                              f"Muestra no válida o no convergida: {it.diagnostic}"[:512]))
    if len(result.iterations) > MAX_SAMPLES:
        prev = rec.event(EventKind.WARNING, det.TRUNCATED, refs=(prev,),
                         why=f"Se listan {MAX_SAMPLES} de {len(result.iterations)} muestras; las estadísticas cubren todas.",
                         values=(("omitted_events", TraceValue.of_number(len(result.iterations) - MAX_SAMPLES)),))
    for key, st in sorted(result.statistics.items()):
        values = [("n", TraceValue.of_number(st["n"]))]
        for name in ("mean", "std", "min", "max"):
            if st.get(name) is not None:
                values.append((name, ana._dec(st[name])))
        values += [(p, ana._dec(v)) for p, v in sorted((st.get("percentiles") or {}).items())]
        prev = rec.event(EventKind.STEP, f"Estadística de {key}", refs=(prev,), values=tuple(values),
                         why="native_statistics del motor sobre las muestras válidas (Decimal).")
    return prev


def _mc_checks(rec, result, n, res):
    ok = sum(1 for it in result.iterations if it.status == "ok")
    rec.check("muestras producidas = iteraciones pedidas", TraceValue.of_number(len(result.iterations)),
              TraceValue.of_number(n), len(result.iterations) == n, refs=(res,),
              detail=labelled("conteo exacto", SYMBOLIC), title="Comprobación: muestras")
    stat_ok = all(st["n"] == ok for st in result.statistics.values())
    rec.check("n de cada estadística = muestras válidas", TraceValue.of_number(ok), TraceValue.of_number(ok),
              stat_ok if result.statistics else None, refs=(res,),
              detail=labelled("conteo exacto", SYMBOLIC if result.statistics else NONE),
              title="Comprobación: estadísticas")


def explain_monte_carlo(spec: str, distributions: str, iterations: str, seed: str, observe: str,
                        **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.mna.analysis import MCConfig, run_monte_carlo_native

    rec = TraceRecorder(MONTE_CARLO)
    ids = ana._circuit(rec, spec, limits)
    det._text_inputs(rec, (("distributions", distributions), ("iterations", iterations), ("seed", seed),
                           ("observe", observe)), "Monte Carlo")
    try:
        circuit, read = ana._read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        n, s = _int(iterations, "iterations"), _int(seed, "seed")
        result = run_monte_carlo_native(circuit, MCConfig(n, _distributions(distributions), s, _observables(observe)))
        if result.status.value not in ("completed",):
            raise ana._status_error(result.status.value, result.diagnostics or ("monte carlo failed",))
        last = _mc_events(rec, result, read, s)
        res = rec.event(EventKind.RESULT, "Monte Carlo completado", refs=(last,),
                        values=(("digest", TraceValue.of_text(result.digest or "-")),
                                ("failures", TraceValue.of_number(result.failure_count))),
                        result=TraceValue.of_text(f"{result.status.value}: {len(result.iterations)} muestras"))
        _mc_checks(rec, result, n, res)
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


def _int(text: str, what: str) -> int:
    v = ana._decimal(text, what)
    if v != v.to_integral_value() or v < 0:
        raise _invalid("INVALID_INPUT", f"{what} must be a non-negative integer")
    return int(v)


# ---------------------------------------------------------------- F8-P1 control: Routh–Hurwitz

def explain_routh(numerator: str, denominator: str) -> ExecutionTrace:
    from academic_core.domain.engineering.control.stability import pole_inventory, routh_of_tf
    from academic_core.domain.engineering.control.tf import make_tf
    from academic_core.domain.execution.control import _coeffs, _poly_text

    rec = TraceRecorder(ROUTH)
    det._text_inputs(rec, (("numerator", numerator), ("denominator", denominator)), "H(s)")
    try:
        num, den = _coeffs(numerator, "numerator"), _coeffs(denominator, "denominator")
        h = make_tf(num, den)
        prev = rec.event(EventKind.STEP, "Polinomio característico", refs=(rec.last,),
                         formula=f"D(s) = {_poly_text(den)}", why="Denominador del TransferFunctionTF del motor.")
        r = routh_of_tf(h)
        for i, row in enumerate(r.table):
            prev = rec.event(EventKind.STEP, f"Fila {i} de la tabla de Routh", refs=(prev,),
                             formula="r_i,j = (r_(i−1),0·r_(i−2),(j+1) − r_(i−2),0·r_(i−1),(j+1)) / r_(i−1),0",
                             why="Fila exacta (Fraction) que construyó el motor.",
                             values=tuple((f"c.{j}", TraceValue.of_text(v)) for j, v in enumerate(row[:64])))
        if r.used_epsilon or r.used_auxiliary:
            prev = rec.event(EventKind.WARNING, "Caso especial de la tabla", refs=(prev,), why=r.detail,
                             values=(("epsilon", TraceValue.of_text("sí" if r.used_epsilon else "no")),
                                     ("auxiliary", TraceValue.of_text("sí" if r.used_auxiliary else "no"))))
        res = rec.event(EventKind.RESULT, "Criterio de Routh–Hurwitz", refs=(prev,),
                        values=(("first_column", TraceValue.of_text(", ".join(r.first_column)[:512])),
                                ("sign_changes", TraceValue.of_number(r.sign_changes)),
                                ("rhp_poles", TraceValue.of_number(r.rhp_count)),
                                ("verdict", TraceValue.of_text(r.verdict))),
                        result=TraceValue.of_text(f"{r.verdict}: {r.rhp_count} polos en el semiplano derecho"))
        inv = pole_inventory(h)
        rec.check("polos en el semiplano derecho: Routh = Durand–Kerner", TraceValue.of_number(inv.rhp_dk),
                  TraceValue.of_number(r.rhp_count), inv.agreement if inv.rhp_dk >= 0 else None, refs=(res,),
                  detail=labelled("dos métodos del motor: tabla exacta y raíces numéricas", NUMERIC
                                  if inv.rhp_dk >= 0 else NONE), title="Comprobación: inventario de polos")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- F8-P2 DSP: FFT stages and sampling

class _FFTObserver:
    def __init__(self):
        self.input = None
        self.stages: list = []

    def fft_input(self, samples, bit_reversed):
        self.input = (tuple(samples), tuple(bit_reversed))

    def fft_stage(self, length, twiddles, data):
        self.stages.append((length, tuple(twiddles), tuple(data)))


def explain_fft(samples: str) -> ExecutionTrace:
    from academic_core.domain.engineering.dsp.dft import dft, fft

    rec = TraceRecorder(FFT)
    det._text_inputs(rec, (("samples", samples),), "Secuencia")
    try:
        values = [ana._decimal(t.strip(), "sample") for t in samples.split(",") if t.strip()]
        obs = _FFTObserver()
        out = fft(values, observer=obs)
        size = len(out)
        show = size <= MAX_FFT_SHOWN
        x, rev = obs.input
        prev = rec.event(EventKind.STEP, "Reordenación por inversión de bits", refs=(rec.last,),
                         formula="DIT radix-2: x[bitrev(n)]",
                         why="Orden en que el motor coloca las muestras antes de las etapas.",
                         values=tuple((f"x.{n}", _cxv(v)) for n, v in enumerate(rev[:64])) if show else
                         (("n", TraceValue.of_number(size)),))
        for length, tw, data in obs.stages:
            vals = tuple((f"W.{j}", _cxv(w)) for j, w in enumerate(tw[:16]))
            vals += tuple((f"y.{n}", _cxv(v)) for n, v in enumerate(data[:48])) if show else ()
            prev = rec.event(EventKind.STEP, f"Etapa de longitud {length}", refs=(prev,), values=vals[:64],
                             formula="mariposa: a' = a + W·b,  b' = a − W·b",
                             why="Factores de giro usados y vector resultante de la etapa, tal como los produjo el motor.")
        res = rec.event(EventKind.RESULT, "Espectro X[k]", refs=(prev,),
                        values=tuple((f"X.{k}", _cxv(v)) for k, v in enumerate(out[:64])),
                        result=TraceValue.of_text(f"FFT de {size} puntos, {len(obs.stages)} etapas"))
        ref = dft(values)
        with localcontext() as ctx:
            ctx.prec = 80
            worst = max((abs(a.re - b.re) + abs(a.im - b.im)) / max(Decimal(1), abs(b.re) + abs(b.im))
                        for a, b in zip(out, ref))
        worst = _six(worst)
        rec.check("FFT = DFT directa del motor", TraceValue.of_number(worst), TraceValue.of_number(Decimal(0)),
                  worst <= FFT_TOL, refs=(res,), tolerance=TraceValue.of_number(FFT_TOL),
                  detail=labelled("dos algoritmos del motor (radix-2 y suma directa)", NUMERIC),
                  title="Comprobación: DFT de referencia")
        stages_ok = len(obs.stages) == size.bit_length() - 1 and (not obs.stages or obs.stages[-1][2] == out)
        rec.check("etapas = log2(N) y la última etapa es X[k]", TraceValue.of_number(len(obs.stages)),
                  TraceValue.of_number(size.bit_length() - 1), stages_ok, refs=(res,),
                  detail=labelled("conteo e igualdad exactos", SYMBOLIC), title="Comprobación: etapas")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


def explain_sampling(signal_hz: str, rate_hz: str) -> ExecutionTrace:
    from academic_core.domain.engineering.dsp.sampling import alias_of, nyquist_frequency, nyquist_rate, nyquist_verdict

    rec = TraceRecorder(SAMPLING)
    det._text_inputs(rec, (("signal_hz", signal_hz), ("rate_hz", rate_hz)), "Muestreo")
    try:
        f, fs = ana._decimal(signal_hz, "signal_hz"), ana._decimal(rate_hz, "rate_hz")
        fn, rate = nyquist_frequency(fs), nyquist_rate(f)
        prev = rec.event(EventKind.STEP, "Frecuencia y tasa de Nyquist", refs=(rec.last,),
                         formula="f_N = fs/2;  tasa de Nyquist = 2·f_max",
                         values=(("f_N", ana._dec(fn)), ("nyquist_rate", ana._dec(rate))))
        verdict = nyquist_verdict(f, fs)
        prev = rec.event(EventKind.DECISION, f"Veredicto: {verdict}", refs=(prev,),
                         formula="CLEAN si f < fs/2; MARGINAL si f = fs/2; ALIASED si f > fs/2",
                         values=(("verdict", TraceValue.of_text(verdict)),))
        alias = alias_of(f, fs)
        res = rec.event(EventKind.RESULT, "Frecuencia aparente", refs=(prev,),
                        formula="f_a = |f − round(f/fs)·fs|", values=(("alias", ana._dec(alias)),),
                        result=TraceValue.of_text(f"{verdict}: f_a = {alias} Hz"))
        rec.check("0 ≤ f_a ≤ fs/2", ana._dec(alias), ana._dec(fn), Decimal(0) <= alias <= fn, refs=(res,),
                  detail=labelled("comparación exacta de los valores del motor", SYMBOLIC),
                  title="Comprobación: banda base")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- F8-P3 RF: reflection chain

def _complex(text: str, what: str):
    from academic_core.domain.engineering.math import DecimalComplex
    t = text.replace(" ", "")
    if "j" not in t:
        return DecimalComplex(ana._decimal(t, what), Decimal(0))
    body = t.replace("j", "")
    for k in range(len(body) - 1, 0, -1):
        if body[k] in "+-" and body[k - 1] not in "eE":
            return DecimalComplex(ana._decimal(body[:k], what), ana._decimal(body[k:] or "0", what))
    return DecimalComplex(Decimal(0), ana._decimal(body or "1", what))


def explain_reflection(z_load: str, z0: str) -> ExecutionTrace:
    from academic_core.domain.engineering.rf.lines import load_impedance, reflection_coefficient
    from academic_core.domain.engineering.rf.margins import mismatch_loss_db, return_loss_db, vswr
    from academic_core.domain.engineering.rf.smith import normalize, z_to_gamma

    rec = TraceRecorder(REFLECTION)
    det._text_inputs(rec, (("z_load", z_load), ("z0", z0)), "Línea")
    try:
        zl, zo = _complex(z_load, "z_load"), _complex(z0, "z0")
        gamma = reflection_coefficient(load_impedance(zl), zo)
        if gamma.status != "FINITE" or gamma.value is None:
            raise UnsupportedError(f"SINGULAR: reflection coefficient {gamma.status}")
        g = gamma.value
        mag = g.modulus()
        prev = rec.event(EventKind.STEP, "Coeficiente de reflexión", refs=(rec.last,),
                         formula="Γ = (ZL − Z0)/(ZL + Z0)", values=(("gamma", _cxv(g)), ("abs_gamma", ana._dec(mag))))
        for name, fn, formula in (("VSWR", vswr, "(1+|Γ|)/(1−|Γ|)"), ("RL_dB", return_loss_db, "−20·log10|Γ|"),
                                  ("ML_dB", mismatch_loss_db, "−10·log10(1−|Γ|²)")):
            m = fn(g)
            prev = rec.event(EventKind.STEP if m.status == "FINITE" else EventKind.WARNING, name, refs=(prev,),
                             formula=formula,
                             values=((name, ana._dec(m.value)),) if m.value is not None else
                             (("status", TraceValue.of_text(m.status)), ("reason", TraceValue.of_text(m.reason[:512]))))
        res = rec.event(EventKind.RESULT, "Adaptación de la carga", refs=(prev,), values=(("gamma", _cxv(g)),),
                        result=TraceValue.of_text(f"|Γ| = {mag}"))
        smith = z_to_gamma(normalize(zl, zo))
        with localcontext() as ctx:
            ctx.prec = 80
            diff = _six(abs(smith.re - g.re) + abs(smith.im - g.im))
        rec.check("Γ de la línea = Γ de la carta de Smith (z = ZL/Z0)", TraceValue.of_number(diff),
                  TraceValue.of_number(Decimal(0)), diff <= Decimal("1e-40"), refs=(res,),
                  tolerance=TraceValue.of_number(Decimal("1e-40")),
                  detail=labelled("dos rutas del motor (rf.lines y rf.smith)", NUMERIC), title="Comprobación: Smith")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- F8-P4 comms: BPSK over AWGN

class _BPSKObserver:
    def __init__(self):
        self.setup = None
        self.bits: list = []

    def bpsk_setup(self, eb_n0_lin, n0, sigma, seed):
        self.setup = (eb_n0_lin, n0, sigma, seed)

    def bpsk_bit(self, index, uniform, bit, symbol, noise, sample, decided):
        self.bits.append((index, uniform, bit, symbol, noise, sample, decided))


def explain_bpsk(eb_n0_db: str, bits: str, seed: str) -> ExecutionTrace:
    from academic_core.domain.engineering.comms.simulation import simulate_bpsk

    rec = TraceRecorder(BPSK)
    det._text_inputs(rec, (("eb_n0_db", eb_n0_db), ("bits", bits), ("seed", seed)), "BPSK")
    try:
        obs = _BPSKObserver()
        report = simulate_bpsk(ana._decimal(eb_n0_db, "eb_n0_db"), _int(bits, "bits"), _int(seed, "seed"),
                               observer=obs)
        lin, n0, sigma, tag = obs.setup
        prev = rec.event(EventKind.STEP, "Canal AWGN", refs=(rec.last,),
                         formula="Eb/N0 lineal = 10^(dB/10); N0 = 1/(Eb/N0); σ = √(N0/2); Es = Eb = 1",
                         values=(("eb_n0_linear", ana._dec(lin)), ("n0", ana._dec(n0)), ("sigma", ana._dec(sigma)),
                                 ("seed", TraceValue.of_number(tag))))
        for index, u, bit, symbol, noise, sample, decided in obs.bits[:MAX_BITS]:
            prev = rec.event(EventKind.STEP, f"Bit {index}", refs=(prev,),
                             formula="bit = [u ≥ 1/2]; s = ±1; r = s + σ·n; decisión = signo(r)",
                             values=(("uniform", ana._dec(u)), ("bit", TraceValue.of_number(bit)),
                                     ("symbol", _cxv(symbol)), ("noise", ana._dec(noise)), ("received", _cxv(sample)),
                                     ("decided", TraceValue.of_number(decided)),
                                     ("error", TraceValue.of_text("sí" if decided != bit else "no"))))
        if len(obs.bits) > MAX_BITS:
            prev = rec.event(EventKind.WARNING, det.TRUNCATED, refs=(prev,),
                             why=f"Se listan {MAX_BITS} de {len(obs.bits)} bits; el recuento de errores los cubre todos.",
                             values=(("omitted_events", TraceValue.of_number(len(obs.bits) - MAX_BITS)),))
        res = rec.event(EventKind.RESULT, "BER simulada", refs=(prev,),
                        values=(("errors", TraceValue.of_number(report.errors)), ("bits", TraceValue.of_number(report.bits)),
                                ("ber_sim", ana._dec(report.ber_sim)), ("ber_analytic", ana._dec(report.ber_analytic)),
                                ("bound_5sigma", ana._dec(report.bound_5sigma)),
                                ("within_bound", TraceValue.of_text("sí" if report.within_bound else "no"))),
                        result=TraceValue.of_text(f"BER = {report.ber_sim} ({report.errors}/{report.bits})"))
        errors = sum(1 for b in obs.bits if b[6] != b[2])
        rec.check("errores observados bit a bit = errores del informe", TraceValue.of_number(errors),
                  TraceValue.of_number(report.errors), errors == report.errors and len(obs.bits) == report.bits,
                  refs=(res,), detail=labelled("conteo exacto", SYMBOLIC), title="Comprobación: errores")
        rec.check("|BER simulada − BER analítica| ≤ 5σ", ana._dec(report.ber_sim), ana._dec(report.ber_analytic),
                  report.within_bound, refs=(res,), tolerance=ana._dec(report.bound_5sigma),
                  detail=labelled("criterio estadístico documentado del motor", NUMERIC),
                  title="Comprobación: criterio 5σ")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- F8-P5 satcom: forward link budget

_LEG_FIELDS = ("direction", "ptx_w", "gtx_dbi", "ltx_db", "freq_hz", "distance_m", "grx_dbi", "lrx_db", "tsys_k",
               "bandwidth_hz", "rb_bps")


def _leg(text: str):
    from academic_core.domain.engineering.satcom.antennas import Antenna
    from academic_core.domain.engineering.satcom.link import LinkLeg
    pairs = {}
    for item in text.split(";"):
        if not item.strip():
            continue
        k, sep, v = item.partition("=")
        k = k.strip()
        if not sep or k not in _LEG_FIELDS or k in pairs:
            raise _invalid("INVALID_INPUT", f"bad link field {item.strip()[:32]!r}")
        pairs[k] = v.strip()
    missing = [k for k in _LEG_FIELDS if k not in pairs]
    if missing:
        raise _invalid("INVALID_INPUT", f"missing link fields: {', '.join(missing)}")
    d = {k: ana._decimal(pairs[k], k) for k in _LEG_FIELDS if k != "direction"}
    return LinkLeg(pairs["direction"], d["ptx_w"], Antenna(gain_dbi=d["gtx_dbi"]), d["ltx_db"], d["freq_hz"],
                   d["distance_m"], rx_antenna=Antenna(gain_dbi=d["grx_dbi"]), lrx_db=d["lrx_db"], tsys_k=d["tsys_k"],
                   bandwidth_hz=d["bandwidth_hz"], rb_bps=d["rb_bps"])


def explain_link_budget(leg: str) -> ExecutionTrace:
    from academic_core.domain.engineering.comms.metrics import to_db10
    from academic_core.domain.engineering.satcom.synthesis import forward_budget

    rec = TraceRecorder(LINK_BUDGET)
    det._text_inputs(rec, (("leg", leg),), "Enlace")
    try:
        b = forward_budget(_leg(leg))
        prev = rec.last
        for title, formula, name, value in (
                ("EIRP", "EIRP = Ptx + Gtx − Ltx (dBW)", "eirp_dbw", b.eirp_dbw),
                ("Pérdida de espacio libre", "FSPL = 20·log10(4πd/λ) (dB)", "fspl_db", b.fspl_db),
                ("Pérdidas adicionales", "Σ pérdidas explícitas (dB)", "misc_db", b.misc_db),
                ("Ganancia de recepción", "Grx (dBi)", "grx_dbi", b.grx_dbi),
                ("Potencia recibida", "Pr = EIRP − FSPL − Lmisc − Lrx + Grx (dBW)", "received_dbw", b.received_dbw),
                ("Factor de mérito", "G/T = Grx − Lrx − 10·log10(Tsys) (dB/K)", "g_over_t_dbk", b.g_over_t_dbk),
                ("C/N0", "C/N0 = EIRP − FSPL − Lmisc + G/T − k (dBHz)", "cn0_dbhz", b.cn0_dbhz),
                ("C/N", "C/N = C/N0 − 10·log10(B) (dB)", "cn_db", b.cn_db)):
            prev = rec.event(EventKind.STEP, title, refs=(prev,), formula=formula, values=((name, ana._dec(value)),),
                             why="Valor intermedio que forward_budget del motor conserva (BudgetResult).")
        res = rec.event(EventKind.RESULT, "Eb/N0 disponible", refs=(prev,), formula="Eb/N0 = C/N0 − 10·log10(Rb) (dB)",
                        values=(("ebno_db", ana._dec(b.ebno_db)),), result=TraceValue.of_text(f"Eb/N0 = {b.ebno_db} dB"))
        with localcontext() as ctx:
            ctx.prec = 80
            pr = abs(b.eirp_dbw - b.fspl_db - b.misc_db - b.lrx_db + b.grx_dbi - b.received_dbw)
        pr = _six(pr)
        rec.check("Pr = EIRP − FSPL − Lmisc − Lrx + Grx", TraceValue.of_number(pr), TraceValue.of_number(Decimal(0)),
                  pr <= Decimal("1e-40"), refs=(res,), tolerance=TraceValue.of_number(Decimal("1e-40")),
                  detail=labelled("con los valores intermedios del motor", NUMERIC), title="Comprobación: potencia")
        with localcontext() as ctx:
            ctx.prec = 80
            parsed = _leg(leg)
            gap = _six(abs(b.cn0_dbhz - to_db10(parsed.rb_bps) - b.ebno_db))
        rec.check("Eb/N0 = C/N0 − 10·log10(Rb)", TraceValue.of_number(gap), TraceValue.of_number(Decimal(0)),
                  gap <= Decimal("1e-40"), refs=(res,), tolerance=TraceValue.of_number(Decimal("1e-40")),
                  detail=labelled("to_db10 del motor sobre Rb", NUMERIC), title="Comprobación: Eb/N0")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- Virtual Lab: F8-M analyses re-observed

def explain_lab_run_analysis(session, run_id: str) -> ExecutionTrace:
    """PARAM_SWEEP / CORNERS / SENS_DC / MONTE_CARLO runs re-observed on the run's working circuit."""
    import dataclasses

    from academic_core.domain.engineering.lab.run import working_circuit
    from academic_core.domain.engineering.mna.analysis import (
        run_monte_carlo_native,
        solve_param_sweep,
        solve_worst_case,
    )

    run, definition = det._find_run(session, run_id)
    rec = TraceRecorder(LAB_ANALYSIS)
    for name, v in (("run_id", run.run_id), ("analysis", run.analysis_kind),
                    ("result_digest", run.result_digest or "-")):
        rec.input(name, TraceValue.of_text(str(v)[:512]), f"Run: {name}")
    kind = run.analysis_kind
    try:
        head = rec.event(EventKind.STEP, f"Experimento {kind} (análisis)", refs=(rec.last,),
                         why="Se vuelve a ejecutar el mismo motor F8-M sobre el circuito de trabajo del run con el "
                             "observador activado; se comprueba que el resultado observado es el registrado.",
                         values=(("status", TraceValue.of_text(str(run.status))),))
        if kind not in ("PARAM_SWEEP", "CORNERS", "SENS_DC", "MONTE_CARLO"):
            rec.event(EventKind.WARNING, f"Explicación de análisis no disponible para {kind}", refs=(head,),
                      why="Use lab.run-detail para OP, DC_SWEEP, AC_POINT, AC_SWEEP y TRANSIENT; SENS_AC no expone "
                          "observaciones internas.")
            raise UnsupportedError(f"UNSUPPORTED: analysis explanation not available for {kind}")
        if run.result is None or definition is None:
            raise ValidationError(f"{str(run.status)}: the run has no engine result to explain")
        analysis = definition.analysis
        working = working_circuit(session.circuit, definition)
        if kind in ("PARAM_SWEEP", "CORNERS"):
            obs = det._SweepObserver()
            if kind == "PARAM_SWEEP":
                observed = solve_param_sweep(working, analysis.param_sweep, observer=obs)
                pts = observed.points
            else:
                observed = solve_worst_case(working, analysis.corners, observer=obs)
                pts = observed.corners
            _ids, last, facts = det._render_points(rec, pts, obs, head, det._Budget())
            res = rec.event(EventKind.RESULT, f"{kind} del run", refs=(last,),
                            values=(("points", TraceValue.of_number(len(pts))),),
                            result=TraceValue.of_text(f"{observed.status.value}: {len(pts)} puntos"))
            det._sweep_checks(rec, pts, facts, res)
        elif kind == "SENS_DC":
            observed, last, rows = _sensitivity_events(rec, working, analysis.sens, head)
            last = _sensitivity_result(rec, observed, last)
            res = rec.event(EventKind.RESULT, "Sensibilidades del run", refs=(last,),
                            result=TraceValue.of_text(f"{observed.status.value}: {len(rows)} parámetros"))
            _sensitivity_check(rec, rows, res)
        else:
            config = dataclasses.replace(analysis.mc, seed=definition.seed)
            observed = run_monte_carlo_native(working, config)
            last = _mc_events(rec, observed, head, definition.seed)
            res = rec.event(EventKind.RESULT, "Monte Carlo del run", refs=(last,),
                            result=TraceValue.of_text(f"{observed.status.value}: {len(observed.iterations)} muestras"))
            _mc_checks(rec, observed, config.iterations, res)
        same = observed.digest == run.result.digest
        rec.check("el resultado observado es el del run registrado", TraceValue.of_text("sí" if same else "no"),
                  TraceValue.of_text("sí"), same, refs=(res,),
                  detail=labelled("igualdad exacta del digest del motor", SYMBOLIC),
                  title="Comprobación: mismo resultado que el run")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- replay

def replay_deep(trace: ExecutionTrace) -> ExecutionTrace:
    if not isinstance(trace, ExecutionTrace) or trace.operation not in OPERATIONS:
        raise _invalid("INVALID_TRACE", "not an E0.4 trace")
    i = {n: v.text for n, v in trace.inputs}
    wide = dict(max_lines=nwt.CEILING_LINES, max_line_length=nwt.CEILING_LINE, max_total_chars=nwt.CEILING_TOTAL)
    op = trace.operation
    if op == ROUTH:
        return explain_routh(i["numerator"], i["denominator"])
    if op == FFT:
        return explain_fft(i["samples"])
    if op == SAMPLING:
        return explain_sampling(i["signal_hz"], i["rate_hz"])
    if op == REFLECTION:
        return explain_reflection(i["z_load"], i["z0"])
    if op == BPSK:
        return explain_bpsk(i["eb_n0_db"], i["bits"], i["seed"])
    if op == LINK_BUDGET:
        return explain_link_budget(i["leg"])
    spec = ana._spec_of(trace)
    if op == TRANSIENT_NEWTON:
        return explain_transient_newton(spec, i["method"], i["tstop"], i["h_init"], i["h_min"], i["h_max"],
                                        i["reltol"], i["abstol"], i["adaptive"] == "true", **wide)
    if op == AC_SWEEP_MNA:
        return explain_ac_sweep_mna(spec, i["source"], i["output_p"], i["output_n"], i["frequencies"], **wide)
    if op == PARAM_SWEEP:
        return explain_param_sweep(spec, i["target"], i["start"], i["stop"], i["step"], i["observe"],
                                   i["warm_start"] == "true", **wide)
    if op == WORST_CASE:
        return explain_worst_case(spec, i["corners"], i["observe"], i["warm_start"] == "true", **wide)
    if op == DC_SENSITIVITY:
        return explain_dc_sensitivity(spec, i["parameters"], i["observe"], **wide)
    return explain_monte_carlo(spec, i["distributions"], i["iterations"], i["seed"], i["observe"], **wide)
