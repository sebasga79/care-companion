"""DB-002 — repositorios sessions/turns/events + smoke test de concurrencia."""

from __future__ import annotations

import threading

from app.repositories.db import apply_schema, get_connection
from app.repositories.events import EventRepository
from app.repositories.sessions import SessionRepository
from app.repositories.turns import TurnRepository


def _init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
    finally:
        conn.close()


def test_session_repository_create_get_update(db_path: str) -> None:
    _init_db(db_path)
    repo = SessionRepository(db_path)

    created = repo.create(case_id="demo-case-001", state="created", knowledge_version=1)
    assert created["case_id"] == "demo-case-001"
    assert created["state"] == "created"
    assert created["closed_at"] is None

    fetched = repo.get(created["id"])
    assert fetched == created

    updated = repo.update_state(created["id"], state="closed", closed_at="2026-01-01T00:00:00Z")
    assert updated is not None
    assert updated["state"] == "closed"
    assert updated["closed_at"] == "2026-01-01T00:00:00Z"


def test_session_repository_get_missing_returns_none(db_path: str) -> None:
    _init_db(db_path)
    repo = SessionRepository(db_path)
    assert repo.get("does-not-exist") is None


def test_turn_repository_add_and_list_ordered(db_path: str) -> None:
    _init_db(db_path)
    session_repo = SessionRepository(db_path)
    turn_repo = TurnRepository(db_path)

    session = session_repo.create(
        case_id="demo-case-001", state="interviewing", knowledge_version=1
    )

    turn_repo.add(session_id=session["id"], speaker="agent", text="Hola", sequence=1)
    turn_repo.add(session_id=session["id"], speaker="patient", text="Hola, bien", sequence=2)

    turns = turn_repo.list_for_session(session["id"])
    assert [t["sequence"] for t in turns] == [1, 2]
    assert turns[0]["speaker"] == "agent"
    assert turns[1]["speaker"] == "patient"


def test_event_repository_add_and_list(db_path: str) -> None:
    _init_db(db_path)
    session_repo = SessionRepository(db_path)
    event_repo = EventRepository(db_path)

    session = session_repo.create(case_id="demo-case-001", state="created", knowledge_version=1)
    event_repo.add_event(
        session_id=session["id"],
        correlation_id="corr-1",
        component="orchestrator",
        event_type="session.created",
        payload={"foo": "bar"},
        latency_ms=12.3,
    )

    events = event_repo.list_for_session(session["id"])
    assert len(events) == 1
    assert events[0]["event_type"] == "session.created"
    assert events[0]["correlation_id"] == "corr-1"

    by_correlation = event_repo.list_by_correlation("corr-1")
    assert len(by_correlation) == 1


def test_concurrent_turn_inserts_all_persisted(db_path: str) -> None:
    """Smoke test de concurrencia básico (DB-002): varios hilos, cada uno
    con su propia conexión de corta duración (vía TurnRepository.add),
    insertan turnos concurrentemente sobre la misma sesión bajo WAL. Todas
    las escrituras deben persistir sin corrupción ni pérdida silenciosa."""
    _init_db(db_path)
    session_repo = SessionRepository(db_path)
    turn_repo = TurnRepository(db_path)

    session = session_repo.create(
        case_id="demo-case-001", state="interviewing", knowledge_version=1
    )

    thread_count = 8
    errors: list[BaseException] = []

    def _write(index: int) -> None:
        try:
            turn_repo.add(
                session_id=session["id"],
                speaker="agent" if index % 2 == 0 else "patient",
                text=f"turno {index}",
                sequence=index,
            )
        except BaseException as exc:  # pragma: no cover - solo si algo falla
            errors.append(exc)

    threads = [threading.Thread(target=_write, args=(i,)) for i in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, f"escrituras concurrentes fallaron: {errors}"

    turns = turn_repo.list_for_session(session["id"])
    assert len(turns) == thread_count
    assert sorted(t["sequence"] for t in turns) == list(range(thread_count))
