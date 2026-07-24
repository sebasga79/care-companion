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

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    checksum TEXT NOT NULL,
    status TEXT NOT NULL,
    knowledge_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section TEXT,
    page INTEGER,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON document_chunks(document_id);

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
