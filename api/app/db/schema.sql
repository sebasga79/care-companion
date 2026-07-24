-- Care Companion — schema operacional SQLite (DB-001)
--
-- Idempotente: seguro de aplicar en cada arranque (CREATE TABLE IF NOT
-- EXISTS / INSERT OR IGNORE). Sin ORM (docs/policies/dependencies.md —
-- dependencias mínimas). WAL y foreign_keys se activan por conexión en
-- app/repositories/db.py, no aquí.

-- Versión global de conocimiento. Fila única (id=1). Cada carga/borrado de
-- documento la incrementa (RAG-008/RAG-009, fuera de esta fase); cada
-- sesión fija el valor vigente al crearse (spec.md §11.2 BR-001).
CREATE TABLE IF NOT EXISTS knowledge_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT OR IGNORE INTO knowledge_version (id, version) VALUES (1, 1);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    state TEXT NOT NULL,
    knowledge_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_case ON sessions(case_id);

CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    speaker TEXT NOT NULL CHECK (speaker IN ('patient', 'agent', 'system')),
    text TEXT NOT NULL,
    is_final INTEGER NOT NULL DEFAULT 1,
    sequence INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);

-- Eventos de traza (correlation_id, timings, agente/etapa). Telemetría no
-- clínica: escritura fail-open (architecture.md §13.1) — un fallo aquí no
-- debe bloquear la llamada. session_id es nullable porque hay eventos
-- (p. ej. HTTP genérico) que no pertenecen a una sesión concreta.
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    correlation_id TEXT NOT NULL,
    component TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT,
    latency_ms REAL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id);

-- `knowledge_version` (columna) se reutiliza como "knowledge_version_added"
-- (RAG-001): versión global vigente en el momento en que el documento quedó
-- `ready`. `knowledge_version_deleted` (agregada por `_ensure_columns` en
-- app/repositories/db.py, ver comentario ahí) registra la versión en la que
-- se borró. `status` ∈ processing|ready|deleted|failed (spec.md §9.2 reduce
-- el enum completo al subconjunto relevante en runtime: `uploaded`/
-- `validating`/`rejected` se resuelven antes de escribir la fila).
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    checksum TEXT NOT NULL,
    status TEXT NOT NULL,
    knowledge_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Solo un documento activo (processing|ready) por checksum: defensa en
-- profundidad además de la verificación a nivel de aplicación (RAG-002),
-- cierra la ventana de carrera entre dos cargas concurrentes del mismo
-- contenido. Un checksum puede reaparecer si el documento anterior fue
-- borrado (deleted) o falló (failed) — volver a "aprender" contenido
-- borrado es una operación legítima, no un duplicado.
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_checksum_active
    ON documents(checksum)
    WHERE status IN ('processing', 'ready');

-- chunk_id (id) es determinista: sha256(document_id|chunk_index|text)
-- (RAG-003), no un uuid aleatorio — permite recomputar/verificar identidad
-- sin ir a la base. `embedding` es un BLOB float32 (NumPy `tobytes()`);
-- `embedding_dim` guarda la dimensión para reconstruir con `frombuffer`.
CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section TEXT,
    page INTEGER,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON document_chunks(document_id);

-- Índice FTS5 (BM25 léxico, RAG-005). Tabla independiente (no "external
-- content"): `document_chunks.id` es TEXT, no hay alias de rowid entero
-- limpio para triggers de contenido externo. Se sincroniza explícitamente
-- desde `app/repositories/knowledge_documents.py` dentro de la misma
-- transacción que escribe `document_chunks` (insertar/borrar en ambas
-- tablas juntas) — "sincronizada" por código de aplicación, no por
-- triggers SQL, documentado aquí para quien audite el schema.
CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    text
);

-- knowledge_version (columna) es la versión global vigente en el momento en
-- que se registró la cita (no la versión del documento) — permite auditar
-- "qué vio la sesión" incluso si el documento se borra después.
CREATE TABLE IF NOT EXISTS citations (
    id TEXT PRIMARY KEY,
    turn_id TEXT REFERENCES turns(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(id),
    chunk_id TEXT NOT NULL REFERENCES document_chunks(id),
    document_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_citations_turn ON citations(turn_id);

CREATE TABLE IF NOT EXISTS metrics (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    component TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metrics_session ON metrics(session_id);
