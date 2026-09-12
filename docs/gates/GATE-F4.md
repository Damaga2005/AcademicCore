# GATE F4 — Academic Management: ✅ PASS (2026-09-12)

Suite: **145 passed, 2 skipped** (123 F0–F3 + 22 F4; skips = reportlab).
Gestion-Academica intact (HEAD `83a1ad4`, only syncthing untracked files).

- [x] auditoría Gestion-Academica completada (+ reuse map con veredictos)
- [x] modelo académico verificado (jerarquía, invariantes, estados)
- [x] university/degree/year/term/subject funcional (CRUD + guards)
- [x] topics / assignments / exams / projects / labs / tasks funcional
- [x] deadlines funcional (upcoming/overdue/done, por actividad e implícitos)
- [x] grades funcional (escalas 0–10/0–20/0–100/letras/pass-fail, pesos,
  opcionales, parciales honestos) + cálculo determinista Decimal
- [x] persistencia verificada (create/reopen/update/delete, mig 008 aditiva
  sobre bases F3, sin borrados silenciosos)
- [x] integridad referencial verificada (padres bloqueados, cascadas de
  deadlines, prerrequisitos, duplicados, huérfanos)
- [x] consultas verificadas (7 queries encapsuladas, UI sin SQL)
- [x] UI verificada (árbol, workspace 5 tabs, CRUD, JSON io, offscreen)
- [x] tests dominio/aplicación/persistencia/UI/edge/property
  (0/1/N actividades, peso 0/100/inválido, mín/máx, deadlines iguales/
  vencidos/ausentes, subjects/terms/years vacíos, eliminación, reopen)
- [x] architecture tests (domain⊄Qt/SQLAlchemy, app⊄widgets, ui⊄infra/
  sqlite, no Flask, no servicios web)
- [x] seguridad revisada (IDs manipulados, strings/SQL, URLs, import,
  paths, serialización; todo parametrizado, todo validado)
- [x] performance medida (30 subjects/300 tasks + tree + reopen, bounds ok)
- [x] regresión F0/F1/F2/F3 PASS + F4 PASS en una sola run

Certificación: IMPLEMENTED (código nuevo) / VERIFIED (todo lo ejecutado en
suite) / TESTED (gates previos intactos). Nada SIMULATED en F4.
**F5 NO iniciada.**
