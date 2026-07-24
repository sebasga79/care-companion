"""Puertos obligatorios — verifica que los fakes cumplen el contrato y son
deterministas (ADR-001: dominio detrás de puertos, adapters reemplazables)."""

from __future__ import annotations

from app.adapters.fake_embeddings import FakeEmbeddings
from app.adapters.fake_llm import FakeLLM
from app.adapters.fake_stt import FakeSTT
from app.adapters.fake_tts import FakeTTS
from app.adapters.fixture_cases import FixtureCaseAdapter
from app.ports.challenge_case import CaseFilters
from app.ports.llm import LLMMessage


async def test_fake_llm_is_deterministic() -> None:
    llm = FakeLLM()
    messages = [LLMMessage(role="user", content="hola, ¿cómo está el paciente?")]
    first = await llm.generate(messages=messages)
    second = await llm.generate(messages=messages)
    assert first.text == second.text
    assert first.provider == "fake"
    assert first.model == "fake-model-v1"


async def test_fake_stt_returns_text() -> None:
    stt = FakeSTT()
    text = await stt.transcribe(b"\x00\x01\x02", language="es")
    assert "es" in text
    assert isinstance(text, str)


async def test_fake_tts_returns_bytes() -> None:
    tts = FakeTTS()
    audio = await tts.synthesize("hola")
    assert isinstance(audio, bytes)
    assert b"hola" in audio


async def test_fake_embeddings_is_deterministic_and_dimension_stable() -> None:
    embeddings = FakeEmbeddings()
    vectors = await embeddings.embed(["hola", "hola", "adios"])
    assert vectors[0] == vectors[1]  # mismo texto -> mismo vector
    assert vectors[0] != vectors[2]
    assert len(vectors[0]) == len(vectors[2])


async def test_fixture_case_adapter_lists_synthetic_cases() -> None:
    adapter = FixtureCaseAdapter()
    cases = await adapter.list_cases(CaseFilters())
    assert len(cases) >= 2
    case_ids = {case.case_id for case in cases}
    assert "demo-case-001" in case_ids


async def test_fixture_case_adapter_get_case_returns_none_for_unknown() -> None:
    adapter = FixtureCaseAdapter()
    assert await adapter.get_case("unknown") is None


async def test_fixture_case_adapter_get_case_returns_full_record() -> None:
    adapter = FixtureCaseAdapter()
    case = await adapter.get_case("demo-case-001")
    assert case is not None
    assert case.case_id == "demo-case-001"
    assert case.procedure
    assert case.caregiver_role
