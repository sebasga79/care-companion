"""`TTSPort` — interfaz de síntesis de voz (voz en tiempo real, C3)."""

from __future__ import annotations

from typing import Protocol


class TTSPort(Protocol):
    async def synthesize(self, text: str, *, voice: str = "es-default") -> bytes: ...
