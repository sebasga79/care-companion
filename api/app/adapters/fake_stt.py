"""`FakeSTT` — adapter determinista de `STTPort` para tests/desarrollo."""

from __future__ import annotations

from app.ports.stt import STTPort


class FakeSTT(STTPort):
    async def transcribe(self, audio_bytes: bytes, *, language: str = "es") -> str:
        return f"[fake-stt:{language}] transcripción simulada ({len(audio_bytes)} bytes)"
