"""Acceso a la versión global de conocimiento (DB-001).

El ciclo de vida completo (incrementar en carga/borrado, consulta canaria)
pertenece a RAG-008/RAG-009, fuera de esta fase. Aquí solo se expone la
lectura que necesita `POST /api/v1/sessions` para fijar `knowledge_version`
al crear una sesión (spec.md §11.2 BR-001)."""

from __future__ import annotations

from app.repositories.db import session_scope


def get_current_knowledge_version(database_path: str) -> int:
    with session_scope(database_path) as conn:
        row = conn.execute("SELECT version FROM knowledge_version WHERE id = 1").fetchone()
    return int(row["version"]) if row is not None else 1
