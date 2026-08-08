"""Repositorio de chunks + índice FTS5 (RAG-001/005/008/009).

`insert` escribe la fila en `document_chunks` y su espejo en
`document_chunks_fts` **en la misma llamada** — es el punto único de
sincronización mencionado en el comentario de `schema.sql` sobre la tabla
FTS5. `delete_for_document` hace lo mismo en reversa y devuelve las filas
purgadas (el llamador las necesita para desalojar el caché de embeddings
por texto — RAG-009)."""

from __future__ import annotations

import sqlite3
from typing import Any

from app.services.embedding_codec import pack_embedding, unpack_embedding


class DocumentChunkRepository:
    def insert(
        self,
        conn: sqlite3.Connection,
        *,
        chunk_id: str,
        document_id: str,
        chunk_index: int,
        section: str | None,
        page: int | None,
        text: str,
        char_start: int | None,
        char_end: int | None,
        content_hash: str,
        embedding: list[float],
        created_at: str,
    ) -> None:
        embedding_blob = pack_embedding(embedding)
        conn.execute(
            """
            INSERT INTO document_chunks
                (id, document_id, section, page, text, created_at, chunk_index,
                 char_start, char_end, content_hash, embedding, embedding_dim)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                document_id,
                section,
                page,
                text,
                created_at,
                chunk_index,
                char_start,
                char_end,
                content_hash,
                embedding_blob,
                len(embedding),
            ),
        )
        conn.execute(
            "INSERT INTO document_chunks_fts (chunk_id, document_id, text) VALUES (?, ?, ?)",
            (chunk_id, document_id, text),
        )

    def list_for_document(self, conn: sqlite3.Connection, document_id: str) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM document_chunks WHERE document_id = ? ORDER BY chunk_index ASC",
            (document_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, conn: sqlite3.Connection, chunk_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM document_chunks WHERE id = ?", (chunk_id,)).fetchone()
        return dict(row) if row is not None else None

    def delete_for_document(self, conn: sqlite3.Connection, document_id: str) -> list[dict]:
        """Purga chunks + espejo FTS de `document_id`. Devuelve las filas
        (incluyendo texto) que existían antes del borrado, para que el
        llamador pueda desalojar el caché de embeddings y para dejar
        evidencia del borrado en la respuesta de la API si hace falta."""
        purged = self.list_for_document(conn, document_id)
        conn.execute("DELETE FROM document_chunks_fts WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
        return purged

    @staticmethod
    def embedding_of(row: dict) -> list[float]:
        return unpack_embedding(row["embedding"]).tolist()
