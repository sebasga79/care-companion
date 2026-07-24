"""Serialización de vectores de embedding a/desde BLOB SQLite (RAG-001/005).

float32 (no float64): la mitad de espacio en disco, precisión de sobra
para similitud coseno sobre vectores de baja dimensión (`Settings.
rag_embedding_dimensions`, default 128). Única función de NumPy usada aquí
— el cómputo de coseno vectorizado (la razón real de la dependencia) vive
en `app/services/retrieval.py`."""

from __future__ import annotations

import numpy as np


def pack_embedding(vector: list[float]) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def unpack_embedding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)
