"""Doble determinista de `TTSPort`, exclusivo de tests."""

from __future__ import annotations

from app.ports.tts import TTSPort


class FakeTTS(TTSPort):
    async def synthesize(self, text: str, *, voice: str = "es-default") -> bytes:
        return f"[fake-tts:{voice}]{text}".encode()
