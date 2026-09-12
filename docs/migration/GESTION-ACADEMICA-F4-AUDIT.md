# GESTION-ACADEMICA — F4 audit (read-only, HEAD `83a1ad4`)

Reference only: Flask + Flask-SQLAlchemy + Jinja SSR + pywebview desktop.
AcademicCore ports concepts, never code (no Flask/SQLAlchemy/routes/templates).

## Arquitectura original
Monolito web: `app.py` factory + 30 blueprints (`routes/`, 152 endpoints) +
`models.py` (1.541 lín, 28 tablas) + 18 migraciones Alembic + `templates/`
(SSR) + pdf.js/lucide vendorizados. Auth custom sin Flask-Login, SECRET_KEY
efímera por defecto. SQLite monousuario, `DOCUMENTOS_DIR` configurable,
backup con límites anti-zip-slip/bomb.

## Entidades y reglas relevantes para F4
- **Anio/Cuatrimestre**: jerarquía Año→Cuatrimestre→Asignatura; estados
  `superado/actual/pendiente` (cuatrimestre), sin fechas en el modelo.
- **Asignatura**: `siglas` UNIQUE-nullable (varios NULL ok), `creditos_ects`
  Float obligatorio, `tipo` obligatoria/optativa, estados
  `superada/cursando/pendiente/no_superada/no_elegida` + flag
  `origen_catalogo` (optativas: quitar revierte a `no_elegida`, manual se
  borra), `regla_esquemas` (`maximo`), `nota_final` override Float,
  prerrequisitos M2M (`asignatura_prerrequisito`), notas libres + timestamp
  inactividad, contacto profesor embebido (compat) + entidad Profesor 1:N.
- **Profesor 1:N por asignatura** (no M2M global): nombre/rol libre/email
  validado (PATRON_EMAIL)/despacho/aula-virtual validada (PATRON_URL)/orden.
- **Componentes/Esquemas/Bloques**: ya portados en F1 (Decimal + gates).
- **TareaEvento**: `asignatura_id` NULLABLE (tareas huérfanas), `completada`
  bool, tipos 8 (4 de examen autocrean EspacioEstudio), prioridad tríada,
  hora/aula/ubicación/descripción/recordatorio-días/link validado
  (PATRON_URL, nunca fetched), fecha indexada.
- **Horarios/conflictos**: portados en F1.
- **EspacioEstudio**: referencias (nunca copias), secciones fijas, progreso
  leídos/total, modo examen; objetivos/hitos (`pendiente/en_progreso/hecho`).
- **Conceptos**: `no_visto/flojo/dominado` + intervalos 0/3/18 (dominio F1;
  motor adaptativo = fase posterior).
- **Documentos/Marcadores/Anotaciones/Búsqueda/Backup/Notificaciones**: fases
  F2/F3 o posteriores; F4 no los toca salvo referencias.

## Divergencias con el modelo canónico (decisiones F4)
1. **Task requiere Subject** en AcademicCore (Gestion permite huérfanas):
   la planificación F4 (upcoming/overdue por subject/term) exige el enlace;
   documentado, no parche.
2. **Assignment states F1** (`draft/active/submitted/graded/archived`) se
   conservan frente a la sugerencia PLANNED/…: `graded≠completed` es distinción
   real (nota registrada vs actividad cerrada).
3. **Profesor global con slug estable** en vez de 1:N ciego por asignatura:
   misma expresividad (SubjectStaff con rol/grupos) + identidad persistente.
4. **Notas**: Gestion = Float 0–10 implícito. F4 = modelo genérico
   (escalas 0–10/0–20/0–100/letras/pass-fail, Decimal, pesos, opcionales).
   Tablas F1 de grading coexisten sin cambios (sin borrados silenciosos).
5. **Terms/Years con fechas + estado** (`pendiente/actual/superado`):
   Gestion no fecha periodos; F4 sí (planificación y reapertura segura).
6. **Borrado seguro con guards en repositorio** (SQLite sin FK DDL en
   tablas heredadas): padres con hijos no se borran (error controlado).

## Problemas detectados (no heredar)
SECRET_KEY efímera; auth sin Flask-Login; `MAX_CONTENT_LENGTH` 200 MB;
scrapers frágiles; pdf.js vendorizado pesado; DB local en migración vieja;
`Apartado` legacy duplicado; Float para notas y `round()` banker's (F1 ya
divergió a Decimal documentado).
