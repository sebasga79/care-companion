"""RAG-010 — `/api/v1/knowledge` end-to-end vía `TestClient` (API real,
sin mocks del pipeline de ingestión/retrieval)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.db import session_scope

_CONTENT = (
    b"# Guia de alta postoperatoria\n\n"
    b"## Signos de alarma\n\n"
    b"Si siente calor en la herida quirurgica o fiebre mayor a 38 grados, "
    b"contacte al equipo medico de inmediato.\n"
)


@pytest.fixture
def client(clean_env: None) -> TestClient:
    app = create_app()
    return TestClient(app)


def _upload(client: TestClient, *, filename: str = "guia.md", content: bytes = _CONTENT, **kwargs):
    files = {"file": (filename, content, "text/markdown")}
    return client.post("/api/v1/knowledge/documents", files=files, **kwargs)


def test_list_documents_starts_empty(client: TestClient) -> None:
    response = client.get("/api/v1/knowledge/documents")
    assert response.status_code == 200
    body = response.json()
    assert body["documents"] == []
    assert body["knowledge_version"] == 1


def test_upload_valid_document_returns_201_and_ready_status(client: TestClient) -> None:
    response = _upload(client, data={"applicability": json.dumps({"procedure": "appendectomy"})})
    assert response.status_code == 201
    body = response.json()
    assert body["document"]["status"] == "ready"
    assert body["document"]["filename"] == "guia.md"
    assert body["chunk_count"] >= 1
    assert body["knowledge_version"] == 2  # 1 (seed) -> 2 tras el learn
    assert body["document"]["protected"] is False
    assert body["document"]["applicability"]["source"] == "evaluator_upload"


def test_official_corpus_document_is_protected_server_side(client: TestClient) -> None:
    upload = _upload(client)
    document_id = upload.json()["document"]["id"]
    database_path = client.app.state.settings.database_path
    with session_scope(database_path) as conn:
        conn.execute(
            "UPDATE documents SET applicability = ? WHERE id = ?",
            (json.dumps({"procedure": "appendicitis", "source": "official_corpus"}), document_id),
        )

    detail = client.get(f"/api/v1/knowledge/documents/{document_id}")
    assert detail.json()["document"]["protected"] is True

    response = client.delete(f"/api/v1/knowledge/documents/{document_id}")
    assert response.status_code == 403
    assert "corpus oficial" in response.json()["detail"].lower()


def test_uploaded_document_appears_in_list(client: TestClient) -> None:
    upload = _upload(client)
    document_id = upload.json()["document"]["id"]

    listed = client.get("/api/v1/knowledge/documents").json()
    ids = {d["id"] for d in listed["documents"]}
    assert document_id in ids


def test_upload_rejects_disallowed_extension(client: TestClient) -> None:
    files = {"file": ("malware.exe", b"MZ" + b"\x00" * 10, "application/octet-stream")}
    response = client.post("/api/v1/knowledge/documents", files=files)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "extension_not_allowed"


def test_upload_rejects_unreadable_pdf(client: TestClient) -> None:
    files = {"file": ("informe.pdf", b"%PDF-1.4 x", "application/pdf")}
    response = client.post("/api/v1/knowledge/documents", files=files)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "pdf_unreadable"


def test_upload_valid_pdf_extracts_text_and_returns_ready(client: TestClient) -> None:
    """RAG-002 ampliado: el corpus real del reto es PDF (`dataset/textos/`)
    — un PDF con texto real se acepta y sigue el mismo pipeline que
    txt/md, vía `/api/v1/knowledge` (RAG-010)."""
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, StreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    resources = DictionaryObject()
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = writer._add_object(font)  # noqa: SLF001
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources
    stream_obj = StreamObject()
    stream_obj.set_data(b"BT /F1 24 Tf 10 100 Td (Guia clinica en PDF) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream_obj)  # noqa: SLF001
    buf = io.BytesIO()
    writer.write(buf)

    files = {"file": ("guia.pdf", buf.getvalue(), "application/pdf")}
    response = client.post("/api/v1/knowledge/documents", files=files)
    assert response.status_code == 201
    body = response.json()
    assert body["document"]["status"] == "ready"
    assert body["document"]["mime"] == "application/pdf"
    assert body["chunk_count"] == 1


def test_upload_rejects_duplicate_checksum(client: TestClient) -> None:
    first = _upload(client, filename="a.md")
    assert first.status_code == 201
    second = _upload(client, filename="b.md")
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "duplicate_checksum"


def test_upload_rejects_invalid_applicability_json(client: TestClient) -> None:
    response = _upload(client, data={"applicability": "{not valid json"})
    assert response.status_code == 400


def test_get_document_detail_reports_positive_canary(client: TestClient) -> None:
    upload = _upload(client)
    document_id = upload.json()["document"]["id"]

    detail = client.get(f"/api/v1/knowledge/documents/{document_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["document"]["status"] == "ready"
    assert body["canary"] is not None
    assert body["canary"]["found"] is True


def test_get_document_missing_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/knowledge/documents/does-not-exist")
    assert response.status_code == 404


def test_delete_document_marks_deleted_and_increments_version(client: TestClient) -> None:
    upload = _upload(client)
    document_id = upload.json()["document"]["id"]
    version_after_upload = upload.json()["knowledge_version"]

    response = client.delete(f"/api/v1/knowledge/documents/{document_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["document"]["status"] == "deleted"
    assert body["knowledge_version"] == version_after_upload + 1
    assert body["purged_chunk_count"] >= 1


def test_delete_missing_document_returns_404(client: TestClient) -> None:
    response = client.delete("/api/v1/knowledge/documents/does-not-exist")
    assert response.status_code == 404


def test_delete_twice_returns_409(client: TestClient) -> None:
    upload = _upload(client)
    document_id = upload.json()["document"]["id"]
    first = client.delete(f"/api/v1/knowledge/documents/{document_id}")
    assert first.status_code == 200
    second = client.delete(f"/api/v1/knowledge/documents/{document_id}")
    assert second.status_code == 409


def test_search_debug_finds_uploaded_content(client: TestClient) -> None:
    _upload(client)
    response = client.get(
        "/api/v1/knowledge/search", params={"q": "calor en la herida fiebre alarma"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) >= 1
    top = body["results"][0]
    assert "lexical_score" in top
    assert "semantic_score" in top
    assert "rrf_score" in top


def test_search_after_delete_finds_nothing_for_deleted_content(client: TestClient) -> None:
    upload = _upload(client)
    document_id = upload.json()["document"]["id"]
    client.delete(f"/api/v1/knowledge/documents/{document_id}")

    response = client.get(
        "/api/v1/knowledge/search", params={"q": "calor en la herida fiebre alarma"}
    )
    assert response.status_code == 200
    document_ids = {r["document_id"] for r in response.json()["results"]}
    assert document_id not in document_ids


def test_search_applicability_filter_query_params(client: TestClient) -> None:
    _upload(client, data={"applicability": json.dumps({"procedure": "appendectomy"})})
    response = client.get(
        "/api/v1/knowledge/search",
        params={"q": "calor herida fiebre", "procedure": "knee_surgery"},
    )
    assert response.status_code == 200
    # el único documento cargado es de otro procedimiento -> no debe aparecer
    assert response.json()["results"] == []


def test_openapi_schema_includes_knowledge_paths(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/knowledge/documents" in paths
    assert "/api/v1/knowledge/documents/{document_id}" in paths
    assert "/api/v1/knowledge/search" in paths


def test_upload_rejects_oversize_file(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_MAX_UPLOAD_BYTES", "10")
    app = create_app()
    small_limit_client = TestClient(app)
    response = _upload(small_limit_client, content=_CONTENT)
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"
