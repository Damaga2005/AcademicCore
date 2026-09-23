-- Gestion-Academica@187a614 schema (alembic head e5a7c9b1d3f4).
-- Dumped from a DB created by Gestion's own migrations; DDL only, no data.
CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL, 
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
CREATE TABLE anio (
	id INTEGER NOT NULL, 
	numero INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (numero)
);
CREATE TABLE anotacion_pdf (
	id INTEGER NOT NULL, 
	documento_id INTEGER NOT NULL, 
	numero_pagina INTEGER NOT NULL, 
	tipo VARCHAR(20) DEFAULT 'resaltado' NOT NULL, 
	color VARCHAR(20) DEFAULT '#ffd400' NOT NULL, 
	texto TEXT, 
	comentario TEXT, 
	rects TEXT NOT NULL, 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(documento_id) REFERENCES documento (id)
);
CREATE TABLE apartado (
	id INTEGER NOT NULL, 
	asignatura_id INTEGER NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	orden INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(asignatura_id) REFERENCES asignatura (id)
);
CREATE TABLE "asignatura" (
	id INTEGER NOT NULL, 
	cuatrimestre_id INTEGER NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	creditos_ects FLOAT NOT NULL, 
	tipo VARCHAR(20) NOT NULL, 
	estado VARCHAR(20) NOT NULL, 
	nota_final FLOAT, 
	origen_catalogo BOOLEAN NOT NULL, 
	notas TEXT, 
	notas_actualizado_en DATETIME, 
	despacho_profesor VARCHAR(200), 
	correo_profesor VARCHAR(200), 
	link_aula_virtual VARCHAR(500), 
	nombre_profesor VARCHAR(200), 
	regla_esquemas VARCHAR(20) DEFAULT 'maximo' NOT NULL, 
	siglas VARCHAR(20), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_asignatura_siglas UNIQUE (siglas), 
	FOREIGN KEY(cuatrimestre_id) REFERENCES cuatrimestre (id)
);
CREATE TABLE asignatura_prerrequisito (
	asignatura_id INTEGER NOT NULL, 
	prerrequisito_id INTEGER NOT NULL, 
	PRIMARY KEY (asignatura_id, prerrequisito_id), 
	FOREIGN KEY(asignatura_id) REFERENCES asignatura (id), 
	FOREIGN KEY(prerrequisito_id) REFERENCES asignatura (id)
);
CREATE TABLE aviso_descartado (
	tipo VARCHAR(30) NOT NULL, 
	entidad_id INTEGER NOT NULL, 
	fecha DATE NOT NULL, 
	PRIMARY KEY (tipo, entidad_id, fecha)
);
CREATE TABLE bloque_evaluacion (
	id INTEGER NOT NULL, 
	esquema_id INTEGER NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	porcentaje FLOAT NOT NULL, 
	orden INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(esquema_id) REFERENCES esquema_evaluacion (id)
);
CREATE TABLE busqueda_favorito (
	id INTEGER NOT NULL, 
	tipo_entidad VARCHAR(20) NOT NULL, 
	entidad_id INTEGER NOT NULL, 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_favorito_entidad UNIQUE (tipo_entidad, entidad_id)
);
CREATE TABLE busqueda_reciente (
	id INTEGER NOT NULL, 
	tipo_entidad VARCHAR(20) NOT NULL, 
	entidad_id INTEGER NOT NULL, 
	etiqueta_mostrada VARCHAR(300) NOT NULL, 
	url VARCHAR(500) NOT NULL, 
	fecha_acceso DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE "componente_evaluacion" (
	id INTEGER NOT NULL, 
	asignatura_id INTEGER NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	tipo VARCHAR(20) NOT NULL, 
	porcentaje FLOAT NOT NULL, 
	nota FLOAT, 
	esquema_id INTEGER, 
	bloque_id INTEGER, orden INTEGER DEFAULT '0' NOT NULL, nota_minima FLOAT, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_componente_evaluacion_esquema_id FOREIGN KEY(esquema_id) REFERENCES esquema_evaluacion (id), 
	CONSTRAINT fk_componente_evaluacion_bloque_id FOREIGN KEY(bloque_id) REFERENCES bloque_evaluacion (id), 
	FOREIGN KEY(asignatura_id) REFERENCES asignatura (id)
);
CREATE TABLE concepto (
	id INTEGER NOT NULL, 
	asignatura_id INTEGER NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	estado VARCHAR(20) NOT NULL, 
	ultima_revision DATE, 
	proxima_revision DATE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(asignatura_id) REFERENCES asignatura (id)
);
CREATE TABLE configuracion_app (
	id INTEGER NOT NULL, 
	tema VARCHAR(10) NOT NULL, 
	dias_aviso_examen INTEGER NOT NULL, 
	dias_asignatura_abandonada INTEGER NOT NULL, 
	widgets_orden VARCHAR(200) NOT NULL, 
	widgets_ocultos VARCHAR(200), objetivo_media FLOAT, 
	PRIMARY KEY (id)
);
CREATE TABLE cuatrimestre (
	id INTEGER NOT NULL, 
	anio_id INTEGER NOT NULL, 
	numero INTEGER NOT NULL, 
	estado VARCHAR(20) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(anio_id) REFERENCES anio (id), 
	UNIQUE (numero)
);
CREATE TABLE dia_actividad (
	fecha DATE NOT NULL, 
	PRIMARY KEY (fecha)
);
CREATE TABLE "documento" (
	id INTEGER NOT NULL, 
	asignatura_id INTEGER NOT NULL, 
	apartado_id INTEGER, 
	nombre_archivo VARCHAR(255) NOT NULL, 
	ruta_local VARCHAR(500) NOT NULL, 
	fecha_subida DATETIME NOT NULL, 
	ultima_pagina_vista INTEGER, 
	etiquetas VARCHAR(500), 
	categoria VARCHAR(20), 
	grupo_documento_id INTEGER, 
	tamano_bytes INTEGER, nombre_original VARCHAR(255), porcentaje_leido FLOAT, zoom_nivel VARCHAR(20), modo_visualizacion VARCHAR(20), scroll_vertical FLOAT, fecha_primera_apertura DATETIME, fecha_ultima_apertura DATETIME, tiempo_total_lectura_segundos INTEGER DEFAULT '0' NOT NULL, numero_sesiones INTEGER DEFAULT '0' NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_documento_grupo_documento_id FOREIGN KEY(grupo_documento_id) REFERENCES grupo_documento (id), 
	FOREIGN KEY(apartado_id) REFERENCES apartado (id), 
	FOREIGN KEY(asignatura_id) REFERENCES asignatura (id)
);
CREATE TABLE espacio_estudio (
	id INTEGER NOT NULL, 
	tarea_evento_id INTEGER NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tarea_evento_id) REFERENCES tarea_evento (id), 
	UNIQUE (tarea_evento_id)
);
CREATE TABLE espacio_estudio_documento (
	id INTEGER NOT NULL, 
	espacio_estudio_id INTEGER NOT NULL, 
	documento_id INTEGER NOT NULL, 
	seccion VARCHAR(30) NOT NULL, 
	leido BOOLEAN NOT NULL, 
	destacado BOOLEAN NOT NULL, 
	orden INTEGER NOT NULL, 
	fecha_referencia DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(documento_id) REFERENCES documento (id), 
	FOREIGN KEY(espacio_estudio_id) REFERENCES espacio_estudio (id), 
	CONSTRAINT uq_espacio_documento UNIQUE (espacio_estudio_id, documento_id)
);
CREATE TABLE esquema_evaluacion (
	id INTEGER NOT NULL, 
	asignatura_id INTEGER NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	orden INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(asignatura_id) REFERENCES asignatura (id)
);
CREATE TABLE grupo_documento (
	id INTEGER NOT NULL, 
	asignatura_id INTEGER NOT NULL, 
	categoria VARCHAR(20) NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	orden INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(asignatura_id) REFERENCES asignatura (id), 
	CONSTRAINT uq_grupo_documento_asig_cat_nombre UNIQUE (asignatura_id, categoria, nombre)
);
CREATE TABLE hito (
	id INTEGER NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	estado VARCHAR(20) NOT NULL, 
	fecha DATE, 
	orden INTEGER NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE horario_clase (
	id INTEGER NOT NULL, 
	asignatura_id INTEGER NOT NULL, 
	tipo VARCHAR(20) NOT NULL, 
	dia_semana INTEGER NOT NULL, 
	hora_inicio TIME NOT NULL, 
	hora_fin TIME NOT NULL, 
	aula VARCHAR(100), 
	fecha_inicio DATE NOT NULL, 
	fecha_fin DATE NOT NULL, 
	intervalo_semanas INTEGER NOT NULL, 
	notas TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(asignatura_id) REFERENCES asignatura (id)
);
CREATE TABLE marcador (
	id INTEGER NOT NULL, 
	documento_id INTEGER NOT NULL, 
	numero_pagina INTEGER NOT NULL, 
	titulo VARCHAR(200), 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(documento_id) REFERENCES documento (id)
);
CREATE TABLE nota_rapida (
	id INTEGER NOT NULL, 
	texto VARCHAR(1000) NOT NULL, 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE objetivo_espacio (
	id INTEGER NOT NULL, 
	espacio_estudio_id INTEGER NOT NULL, 
	texto VARCHAR(300) NOT NULL, 
	completada BOOLEAN NOT NULL, 
	orden INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(espacio_estudio_id) REFERENCES espacio_estudio (id)
);
CREATE TABLE pagina_texto (
	id INTEGER NOT NULL, 
	documento_id INTEGER NOT NULL, 
	numero_pagina INTEGER NOT NULL, 
	contenido TEXT NOT NULL, contenido_normalizado TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(documento_id) REFERENCES documento (id)
);
CREATE TABLE profesor (
	id INTEGER NOT NULL, 
	asignatura_id INTEGER NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	rol VARCHAR(100), 
	correo VARCHAR(200), 
	despacho VARCHAR(200), 
	aula_virtual VARCHAR(500), 
	orden INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(asignatura_id) REFERENCES asignatura (id)
);
CREATE TABLE recurso_externo (
	id INTEGER NOT NULL, 
	asignatura_id INTEGER NOT NULL, 
	nombre VARCHAR(100) NOT NULL, 
	url VARCHAR(500) NOT NULL, 
	tipo VARCHAR(50), 
	orden INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(asignatura_id) REFERENCES asignatura (id)
);
CREATE TABLE sesion_estudio (
	id INTEGER NOT NULL, 
	asignatura_id INTEGER, 
	fecha DATE NOT NULL, 
	minutos INTEGER NOT NULL, nota VARCHAR(200), 
	PRIMARY KEY (id), 
	CONSTRAINT fk_sesion_estudio_asignatura_id FOREIGN KEY(asignatura_id) REFERENCES asignatura (id)
);
CREATE TABLE "tarea_evento" (
	id INTEGER NOT NULL, 
	asignatura_id INTEGER, 
	titulo VARCHAR(200) NOT NULL, 
	fecha DATE NOT NULL, 
	tipo VARCHAR(20) NOT NULL, 
	completada BOOLEAN NOT NULL, 
	prioridad VARCHAR(10) NOT NULL, 
	hora_inicio TIME, 
	hora_fin TIME, 
	aula VARCHAR(100), 
	ubicacion VARCHAR(200), 
	descripcion TEXT, 
	recordatorio INTEGER, 
	link_relacionado VARCHAR(500), 
	documento_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_tarea_evento_documento_id FOREIGN KEY(documento_id) REFERENCES documento (id), 
	FOREIGN KEY(asignatura_id) REFERENCES asignatura (id)
);
CREATE INDEX ix_anotacion_pdf_documento_id ON anotacion_pdf (documento_id);
CREATE INDEX ix_concepto_asignatura_id ON concepto (asignatura_id);
CREATE INDEX ix_concepto_proxima_revision ON concepto (proxima_revision);
CREATE INDEX ix_documento_apartado_id ON documento (apartado_id);
CREATE INDEX ix_documento_asignatura_id ON documento (asignatura_id);
CREATE INDEX ix_documento_fecha_ultima_apertura ON documento (fecha_ultima_apertura);
CREATE INDEX ix_documento_grupo_documento_id ON documento (grupo_documento_id);
CREATE INDEX ix_horario_clase_asignatura_id ON horario_clase (asignatura_id);
CREATE INDEX ix_pagina_texto_documento_id ON pagina_texto (documento_id);
CREATE INDEX ix_profesor_asignatura_id ON profesor (asignatura_id);
CREATE INDEX ix_tarea_evento_asignatura_id ON tarea_evento (asignatura_id);
CREATE INDEX ix_tarea_evento_fecha ON tarea_evento (fecha);
