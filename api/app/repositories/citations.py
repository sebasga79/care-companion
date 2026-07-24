"""Repositorio de citas (RAG-007).

Persiste `CitationRef` (contrato ya definido en `app/domain/models.py` —
spec.md §8.2: documento, versión, ubicación y `chunk_id` por afirmación)
asociadas a un turno. Deliberadamente no hace `ON DELETE CASCADE` desde
`documents`/`document_chunks`: una cita ya registrada es un hecho histórico
de auditoría ("qué vio y citó esta sesión en su momento"), no debe
desaparecer si el documento se borra después (RAG-009 solo purga el
contenido/índice, nunca las citas ya emitidas)."""

from __future__ import annotations

import sqlite3
from typing import Any

from app.domain.models import CitationRef


class CitationRepository:
    def record(
        self,
        conn: sqlite3.Connection,
        *,
        turn_id: str | None,
        citation: CitationRef,
        created_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO citations
                (id, turn_id, document_id, chunk_id, document_version, title, section, page,
                 knowledge_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                citation.citation_id,
                turn_id,
                citation.document_id,
                citation.chunk_id,
                citation.document_version,
                citation.title,
                citation.section,
                citation.page,
                citation.knowledge_version,
                created_at,
            ),
        )

    def list_for_turn(self, conn: sqlite3.Connection, turn_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM citations WHERE turn_id = ? ORDER BY created_at ASC", (turn_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def to_citation_ref(self, row: dict[str, Any]) -> CitationRef:
        return CitationRef(
            citation_id=row["id"],
            document_id=row["document_id"],
            document_version=row["document_version"],
            chunk_id=row["chunk_id"],
            title=row["title"],
            section=row["section"],
            page=row["page"],
            knowledge_version=row["knowledge_version"],
        )
