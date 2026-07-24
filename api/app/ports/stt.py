"""`STTPort` — interfaz de reconocimiento de voz (voz en tiempo real, C3)."""

from __future__ import annotations

from typing import Protocol


class STTPort(Protocol):
    async def transcribe(self, audio_bytes: bytes, *, language: str = "es") -> str: ...
