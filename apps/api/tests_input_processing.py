"""Unit tests for the FR1/FR2 input acceptance criteria; no database or AI service required."""
import asyncio
import io
import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused")

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from core.input_processing import (
    MAX_FILE_BYTES,
    attach_source_labels,
    parse_fr_nfr,
    parse_user_stories,
    pasted_page_count,
    read_and_extract_upload,
)


def test_pasted_text_page_count_rounds_up_at_3000_chars():
    assert pasted_page_count("") == 0
    assert pasted_page_count("x" * 3000) == 1
    assert pasted_page_count("x" * 3001) == 2
    assert pasted_page_count("x" * 300000) == 100


def test_user_stories_parse_role_goal_reason_and_keep_malformed_lines():
    text = "As a librarian, I want to register members, so that I can manage membership.\nThis malformed story is still a requirement."
    normalized, metadata, warning = parse_user_stories(text)
    stories = metadata["parsed_stories"]
    assert stories[0]["structured"] is True
    assert stories[0]["role"] == "librarian"
    assert stories[0]["goal"] == "to register members"
    assert stories[0]["reason"] == "I can manage membership"
    assert stories[1]["structured"] is False
    assert "malformed story" in normalized
    assert warning and "retained" in warning


def test_fr_nfr_input_records_original_ids_and_warns_for_unnumbered_list():
    _, metadata, warning = parse_fr_nfr("FR1: User can log in.\nNFR2: Respond within 2 seconds.")
    assert metadata["source_labels_by_line"] == {"1": "FR1", "2": "NFR2"}
    assert warning is None
    _, metadata, warning = parse_fr_nfr("User can log in\nRespond quickly")
    assert metadata["source_labels_by_line"] == {}
    assert "could not be preserved" in warning


def test_original_fr_nfr_id_is_attached_to_extracted_statement():
    result = [{"text": "The user can log in.", "source_location": {"line_start": 1}}]
    attach_source_labels(result, "FR12: The user can log in.")
    assert result[0]["source_label"] == "FR12"


def test_unsupported_file_type_is_rejected_before_reading():
    upload = UploadFile(filename="requirements.txt", file=io.BytesIO(b"some text"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(read_and_extract_upload(upload))
    assert error.value.status_code == 415
    assert "PDF" in error.value.detail and "DOCX" in error.value.detail


def test_fake_pdf_extension_is_rejected_by_content():
    upload = UploadFile(filename="not-really.pdf", file=io.BytesIO(b"not a PDF"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(read_and_extract_upload(upload))
    assert error.value.status_code == 400
    assert "not a valid PDF" in error.value.detail


def test_file_larger_than_10_mib_is_rejected_but_exact_limit_is_not_size_rejected():
    oversized = UploadFile(filename="large.pdf", file=io.BytesIO(b"%PDF-" + b"x" * MAX_FILE_BYTES))
    with pytest.raises(HTTPException) as error:
        asyncio.run(read_and_extract_upload(oversized))
    assert error.value.status_code == 413
    assert "10 MB" in error.value.detail

    # Exactly 10 MiB proceeds beyond the size gate and is rejected only by the PDF parser as malformed.
    exact = UploadFile(filename="exact.pdf", file=io.BytesIO(b"%PDF-" + b"x" * (MAX_FILE_BYTES - 5)))
    with pytest.raises(HTTPException) as exact_error:
        asyncio.run(read_and_extract_upload(exact))
    assert exact_error.value.status_code != 413


def _pdf_bytes_with_text_and_blank_page():
    from reportlab.pdfgen import canvas
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    pdf.drawString(50, 750, "FR1: The user shall be able to log in.")
    pdf.showPage()
    pdf.showPage()  # image-only/blank page: must be skipped and warned about
    pdf.save()
    return output.getvalue()


def test_pdf_with_mixed_text_and_image_only_pages_is_accepted_with_warning():
    data = _pdf_bytes_with_text_and_blank_page()
    upload = UploadFile(filename="requirements.pdf", file=io.BytesIO(data))
    result = asyncio.run(read_and_extract_upload(upload))
    assert result["page_count"] == 2
    assert "user shall be able to log in" in result["text"]
    assert result["skipped_pages"] == [2]
    assert "page(s): 2" in result["warning"]


def test_pdf_with_no_extractable_text_is_rejected():
    from pypdf import PdfWriter
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    upload = UploadFile(filename="scanned.pdf", file=io.BytesIO(output.getvalue()))
    with pytest.raises(HTTPException) as error:
        asyncio.run(read_and_extract_upload(upload))
    assert error.value.status_code == 422
    assert "no extractable text" in error.value.detail


def test_docx_is_extracted_and_page_count_is_recorded():
    from docx import Document
    output = io.BytesIO()
    doc = Document()
    doc.add_paragraph("FR1: The user shall be able to log in.")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "NFR1"
    table.cell(0, 1).text = "The system shall respond quickly."
    doc.save(output)
    upload = UploadFile(filename="requirements.docx", file=io.BytesIO(output.getvalue()))
    result = asyncio.run(read_and_extract_upload(upload))
    assert "FR1" in result["text"]
    assert "NFR1 | The system shall respond quickly." in result["text"]
    assert result["page_count"] >= 1


def test_exactly_10_mib_pdf_is_accepted():
    data = _pdf_bytes_with_text_and_blank_page()
    data += b" " * (MAX_FILE_BYTES - len(data))
    assert len(data) == MAX_FILE_BYTES
    upload = UploadFile(filename="exact-limit.pdf", file=io.BytesIO(data))
    result = asyncio.run(read_and_extract_upload(upload))
    assert result["size_bytes"] == MAX_FILE_BYTES
    assert result["page_count"] == 2


def test_password_protected_docx_gets_specific_error():
    encrypted_office_signature = bytes.fromhex("D0CF11E0A1B11AE1") + b"encrypted-content"
    upload = UploadFile(filename="protected.docx", file=io.BytesIO(encrypted_office_signature))
    with pytest.raises(HTTPException) as error:
        asyncio.run(read_and_extract_upload(upload))
    assert error.value.status_code == 400
    assert "password-protected" in error.value.detail


def test_corrupt_pdf_and_docx_have_specific_errors():
    pdf = UploadFile(filename="broken.pdf", file=io.BytesIO(b"%PDF-this is not a valid PDF"))
    with pytest.raises(HTTPException) as pdf_error:
        asyncio.run(read_and_extract_upload(pdf))
    assert pdf_error.value.status_code == 400
    assert "PDF file appears corrupted" in pdf_error.value.detail

    docx = UploadFile(filename="broken.docx", file=io.BytesIO(b"not a zip package"))
    with pytest.raises(HTTPException) as docx_error:
        asyncio.run(read_and_extract_upload(docx))
    assert docx_error.value.status_code == 400
    assert "DOCX file appears corrupted" in docx_error.value.detail


def test_user_story_metadata_attached_to_statement():
    from core.input_processing import enrich_extracted_statements

    story_text = "As a librarian, I want to catalog books, so that users can search them."
    result = [{"text": story_text, "source_location": {"line_start": 1}}]
    enriched = enrich_extracted_statements(result, story_text)
    assert enriched[0]["metadata"] == {
        "role": "librarian",
        "goal": "to catalog books",
        "reason": "users can search them",
        "structured": True,
    }


def test_password_protected_pdf_gets_specific_error():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret-pass")
    buf = io.BytesIO()
    writer.write(buf)

    upload = UploadFile(filename="encrypted.pdf", file=io.BytesIO(buf.getvalue()))
    with pytest.raises(HTTPException) as error:
        asyncio.run(read_and_extract_upload(upload))
    assert error.value.status_code == 400
    assert "password-protected" in error.value.detail


def test_password_protected_docx_with_encrypted_package_gets_specific_error():
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("EncryptedPackage", b"encrypted data stream")
    upload = UploadFile(filename="modern-encrypted.docx", file=io.BytesIO(buf.getvalue()))
    with pytest.raises(HTTPException) as error:
        asyncio.run(read_and_extract_upload(upload))
    assert error.value.status_code == 400
    assert "password-protected" in error.value.detail


def test_pdf_exceeding_100_pages_is_rejected():
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(101):
        writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)

    upload = UploadFile(filename="huge.pdf", file=io.BytesIO(buf.getvalue()))
    with pytest.raises(HTTPException) as error:
        asyncio.run(read_and_extract_upload(upload))
    assert error.value.status_code == 413
    assert "100 pages" in error.value.detail


def test_parse_input_requirements_and_malformed_story_metadata():
    from core.input_processing import parse_input_requirements, enrich_extracted_statements

    raw_input = (
        "As a member, I want to search books, so that I can find what to read.\n"
        "As a librarian, I want to register members.\n"  # malformed (no 'so that')
        "FR10: The system shall backup the database daily.\n"
        "Unnumbered general requirement.\n"
    )
    text_for_ai, metadata, warnings = parse_input_requirements(raw_input)
    assert len(metadata["parsed_stories"]) == 2
    assert metadata["parsed_stories"][0]["structured"] is True
    assert metadata["parsed_stories"][1]["structured"] is False
    assert metadata["source_labels_by_line"] == {"3": "FR10"}
    assert len(warnings) == 2  # one for malformed story, one for unnumbered requirement

    # When AI extracts statements, metadata and labels are attached
    extracted_reqs = [
        {"id": "R-1", "text": "A member searches books.", "source_location": {"line_start": 1}},
        {"id": "R-2", "text": "A librarian registers members.", "source_location": {"line_start": 2}},
        {"id": "R-3", "text": "Backup database daily.", "source_location": {"line_start": 3}},
        {"id": "R-4", "text": "Unnumbered general requirement.", "source_location": {"line_start": 4}},
    ]
    enriched = enrich_extracted_statements(extracted_reqs, raw_input, parsed_metadata=metadata)

    # R-1 has structured user story metadata
    assert enriched[0]["metadata"] == {
        "role": "member",
        "goal": "to search books",
        "reason": "I can find what to read",
        "structured": True,
    }

    # R-2 is preserved as unstructured requirement
    assert enriched[1]["metadata"] == {"structured": False}

    # R-3 has preserved original FR10 ID
    assert enriched[2].get("source_label") == "FR10"

    # R-4 has no invented ID
    assert enriched[3].get("source_label") is None


def test_docx_page_count_from_extended_app_xml():
    from docx import Document
    from core.input_processing import _docx_page_count

    doc = Document()
    doc.add_paragraph("Testing docx page counting")
    buf = io.BytesIO()
    doc.save(buf)

    pages, warning = _docx_page_count(buf.getvalue(), "Testing docx page counting")
    assert pages == 1
    assert warning is None  # Extracted from docProps/app.xml cleanly


def test_upload_document_requires_storage_configuration(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from core.auth import get_current_user, User
    import routers.integrated as integrated

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    app.dependency_overrides[get_current_user] = lambda: User(id="user_123", email="user@example.com")
    monkeypatch.setattr(integrated, "require_project", lambda pid, u: {"id": pid, "name": "Test Project"})
    monkeypatch.setattr(integrated.db, "consent", lambda uid: {"policy_version": integrated.POLICY_VERSION})
    monkeypatch.setattr(integrated.db, "project_document_totals", lambda pid: {"document_count": 0, "total_pages": 0})

    client = TestClient(app)
    pdf_data = _pdf_bytes_with_text_and_blank_page()
    res = client.post(
        "/api/v1/projects/proj_1/documents",
        files={"file": ("test.pdf", pdf_data, "application/pdf")},
        headers={"Authorization": "Bearer valid-real-token"},
    )
    assert res.status_code == 503
    assert "Storage service is not configured" in res.json()["detail"]


def test_upload_document_rejects_mock_token_for_storage(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from core.auth import get_current_user, User
    import routers.integrated as integrated

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    app.dependency_overrides[get_current_user] = lambda: User(id="user_123", email="user@example.com")
    monkeypatch.setattr(integrated, "require_project", lambda pid, u: {"id": pid, "name": "Test Project"})
    monkeypatch.setattr(integrated.db, "consent", lambda uid: {"policy_version": integrated.POLICY_VERSION})
    monkeypatch.setattr(integrated.db, "project_document_totals", lambda pid: {"document_count": 0, "total_pages": 0})

    client = TestClient(app)
    pdf_data = _pdf_bytes_with_text_and_blank_page()
    res = client.post(
        "/api/v1/projects/proj_1/documents",
        files={"file": ("test.pdf", pdf_data, "application/pdf")},
        headers={"Authorization": "Bearer mock-token:user@example.com"},
    )
    assert res.status_code == 403
    assert "Mock or anonymous tokens cannot be used" in res.json()["detail"]


def test_upload_document_links_job_and_document(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from core.auth import get_current_user, User
    import routers.integrated as integrated
    import httpx

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", "project-documents")
    app.dependency_overrides[get_current_user] = lambda: User(id="user_123", email="user@example.com")
    monkeypatch.setattr(integrated, "require_project", lambda pid, u: {"id": pid, "name": "Test Project"})
    monkeypatch.setattr(integrated.db, "consent", lambda uid: {"policy_version": integrated.POLICY_VERSION})
    monkeypatch.setattr(integrated.db, "project_document_totals", lambda pid: {"document_count": 0, "total_pages": 0})

    doc_store = {}
    job_store = {}

    def fake_create_doc(pid, filename, storage_path, content_type, size_bytes, page_count, **kwargs):
        d = {
            "id": "doc_abc123",
            "project_id": pid,
            "filename": filename,
            "storage_path": storage_path,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "page_count": page_count,
            "status": "uploaded",
            "warning": kwargs.get("warning"),
            "skipped_pages": kwargs.get("skipped_pages", []),
            "job_id": None,
        }
        doc_store["doc"] = d
        return d

    def fake_create_job(pid, kind, total, label, diagram_types=(), document_id=None):
        j = {
            "id": "job_xyz789",
            "project_id": pid,
            "kind": kind,
            "status": "queued",
            "progress_step": 0,
            "progress_total": total,
            "progress_label": label,
            "document_id": document_id,
        }
        job_store["job"] = j
        return j

    def fake_update_doc(doc_id, **fields):
        doc_store["doc"].update(fields)
        return doc_store["doc"]

    monkeypatch.setattr(integrated.db, "create_document", fake_create_doc)
    monkeypatch.setattr(integrated.db, "create_job", fake_create_job)
    monkeypatch.setattr(integrated.db, "update_document", fake_update_doc)
    monkeypatch.setattr(integrated.db, "touch_project", lambda pid, clear_confirmation=True: None)
    async def noop_queued(*args, **kwargs):
        pass
    monkeypatch.setattr(integrated, "queued", noop_queued)

    # Mock storage HTTP call to return 200
    class MockStorageClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            assert "project-documents" in url
            return httpx.Response(200, json={"Key": "uploaded"})

    monkeypatch.setattr(integrated.httpx, "AsyncClient", MockStorageClient)

    client = TestClient(app)
    pdf_data = _pdf_bytes_with_text_and_blank_page()
    res = client.post(
        "/api/v1/projects/proj_1/documents",
        files={"file": ("srs.pdf", pdf_data, "application/pdf")},
        headers={"Authorization": "Bearer real-user-token"},
    )
    assert res.status_code == 202
    data = res.json()
    assert data["document"]["id"] == "doc_abc123"
    assert data["job"]["id"] == "job_xyz789"

    # Verify bidirectional link
    assert doc_store["doc"]["job_id"] == "job_xyz789"
    assert job_store["job"]["document_id"] == "doc_abc123"


def test_upload_document_cleans_up_storage_on_db_failure(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from core.auth import get_current_user, User
    import routers.integrated as integrated
    import httpx

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    app.dependency_overrides[get_current_user] = lambda: User(id="user_123", email="user@example.com")
    monkeypatch.setattr(integrated, "require_project", lambda pid, u: {"id": pid, "name": "Test Project"})
    monkeypatch.setattr(integrated.db, "consent", lambda uid: {"policy_version": integrated.POLICY_VERSION})
    monkeypatch.setattr(integrated.db, "project_document_totals", lambda pid: {"document_count": 0, "total_pages": 0})

    deleted_paths = []
    async def fake_delete_storage(path, token):
        deleted_paths.append(path)
        return True

    monkeypatch.setattr(integrated, "_delete_storage", fake_delete_storage)

    def failing_create_doc(*args, **kwargs):
        raise ValueError("A project can contain at most 100 pages in total.")

    monkeypatch.setattr(integrated.db, "create_document", failing_create_doc)

    class MockStorageClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            return httpx.Response(200, json={"Key": "uploaded"})

    monkeypatch.setattr(integrated.httpx, "AsyncClient", MockStorageClient)

    client = TestClient(app)
    pdf_data = _pdf_bytes_with_text_and_blank_page()
    res = client.post(
        "/api/v1/projects/proj_1/documents",
        files={"file": ("srs.pdf", pdf_data, "application/pdf")},
        headers={"Authorization": "Bearer real-user-token"},
    )
    assert res.status_code == 413
    assert len(deleted_paths) == 1
    assert "proj_1" in deleted_paths[0] and "srs.pdf" in deleted_paths[0]





def test_paste_empty_or_whitespace_rejected():
    from fastapi.testclient import TestClient
    from main import app
    from core.auth import get_current_user, User
    import routers.integrated as integrated

    app.dependency_overrides[get_current_user] = lambda: User(id="user_123", email="user@example.com")
    integrated.require_project = lambda pid, u: {"id": pid, "name": "Test Project"}

    client = TestClient(app)
    res_empty = client.post("/api/v1/projects/proj_1/inputs", json={"text": ""})
    assert res_empty.status_code == 422

    res_whitespace = client.post("/api/v1/projects/proj_1/inputs", json={"text": "   \n\t  \n  "})
    assert res_whitespace.status_code == 422
    assert "Enter some requirements text" in res_whitespace.json()["detail"]


def test_upload_document_enforces_15_document_limit(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from core.auth import get_current_user, User
    import routers.integrated as integrated

    app.dependency_overrides[get_current_user] = lambda: User(id="user_123", email="user@example.com")
    monkeypatch.setattr(integrated, "require_project", lambda pid, u: {"id": pid, "name": "Test Project"})
    monkeypatch.setattr(integrated.db, "consent", lambda uid: {"policy_version": integrated.POLICY_VERSION})
    monkeypatch.setattr(integrated.db, "project_document_totals", lambda pid: {"document_count": 15, "total_pages": 30})

    client = TestClient(app)
    pdf_data = _pdf_bytes_with_text_and_blank_page()
    res = client.post(
        "/api/v1/projects/proj_1/documents",
        files={"file": ("doc16.pdf", pdf_data, "application/pdf")},
        headers={"Authorization": "Bearer real-token"},
    )
    assert res.status_code == 400
    assert "at most 15 documents" in res.json()["detail"]


def test_upload_document_enforces_100_page_project_limit(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from core.auth import get_current_user, User
    import routers.integrated as integrated

    app.dependency_overrides[get_current_user] = lambda: User(id="user_123", email="user@example.com")
    monkeypatch.setattr(integrated, "require_project", lambda pid, u: {"id": pid, "name": "Test Project"})
    monkeypatch.setattr(integrated.db, "consent", lambda uid: {"policy_version": integrated.POLICY_VERSION})
    monkeypatch.setattr(integrated.db, "project_document_totals", lambda pid: {"document_count": 5, "total_pages": 99})

    client = TestClient(app)
    # _pdf_bytes_with_text_and_blank_page has 2 pages; 99 + 2 = 101 > 100 max
    pdf_data = _pdf_bytes_with_text_and_blank_page()
    res = client.post(
        "/api/v1/projects/proj_1/documents",
        files={"file": ("doc_over_page_limit.pdf", pdf_data, "application/pdf")},
        headers={"Authorization": "Bearer real-token"},
    )
    assert res.status_code == 413
    assert "exceeds the remaining project limit of 1 pages" in res.json()["detail"]


def test_delete_document_removes_storage_and_metadata(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from core.auth import get_current_user, User
    import routers.integrated as integrated

    app.dependency_overrides[get_current_user] = lambda: User(id="user_123", email="user@example.com")
    monkeypatch.setattr(integrated, "require_project", lambda pid, u: {"id": pid, "name": "Test Project"})
    monkeypatch.setattr(integrated.db, "get_document", lambda pid, did: {
        "id": did,
        "project_id": pid,
        "filename": "delete_me.pdf",
        "storage_path": f"{pid}/{did}/delete_me.pdf",
    })

    deleted_storage = []
    async def fake_delete_storage(path, token):
        deleted_storage.append(path)
        return True

    deleted_db = []
    def fake_delete_db(pid, did):
        deleted_db.append((pid, did))
        return {"id": did}

    monkeypatch.setattr(integrated, "_delete_storage", fake_delete_storage)
    monkeypatch.setattr(integrated.db, "delete_document", fake_delete_db)
    monkeypatch.setattr(integrated.db, "touch_project", lambda pid, clear_confirmation=True: None)

    client = TestClient(app)
    res = client.delete(
        "/api/v1/projects/proj_1/documents/doc_del123",
        headers={"Authorization": "Bearer real-token"},
    )
    assert res.status_code == 200
    assert res.json() == {"deleted": True, "id": "doc_del123"}
    assert len(deleted_storage) == 1
    assert "doc_del123/delete_me.pdf" in deleted_storage[0]
    assert deleted_db == [("proj_1", "doc_del123")]


def test_extraction_worker_end_to_end_with_metadata(monkeypatch):
    import routers.integrated as integrated
    import httpx

    job_updates = []
    def fake_update_job(job_id, **fields):
        job_updates.append((job_id, fields))

    doc_updates = []
    def fake_update_doc(doc_id, **fields):
        doc_updates.append((doc_id, fields))

    inserted_statements = []
    def fake_insert_statements(pid, statements, source_document="pasted requirements"):
        inserted_statements.extend(statements)
        return [f"st_{i}" for i in range(len(statements))]

    added_items = []
    def fake_add_items(pid, items):
        added_items.extend(items)

    monkeypatch.setattr(integrated.db, "update_job", fake_update_job)
    monkeypatch.setattr(integrated.db, "update_document", fake_update_doc)
    monkeypatch.setattr(integrated.db, "insert_statements", fake_insert_statements)
    monkeypatch.setattr(integrated.db, "add_system_items", fake_add_items)
    monkeypatch.setattr(integrated.db, "touch_project", lambda pid, clear_confirmation=True: None)
    monkeypatch.setattr(integrated, "detect", lambda pid: True)

    class FakeExtractionAI:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, json=None, **kwargs):
            req = httpx.Request("POST", url)
            return httpx.Response(200, request=req, json={
                "requirements": [
                    {
                        "id": "R-001",
                        "text": "The librarian shall register a member.",
                        "labels": ["functional"],
                        "source_location": {"line_start": 1, "excerpt": "FR1: The librarian shall register a member."},
                    },
                    {
                        "id": "R-002",
                        "text": "As a member, I want to borrow books, so that I can study.",
                        "labels": ["functional"],
                        "source_location": {"line_start": 2, "excerpt": "As a member, I want to borrow books, so that I can study."},
                    },
                ],
                "actors": [{"name": "Librarian", "description": "Manages library"}],
                "entities": [{"name": "Member", "description": "Library member"}],
                "processes": [],
                "data_flows": [],
                "data_stores": [],
            })

    monkeypatch.setattr(integrated.httpx, "AsyncClient", FakeExtractionAI)

    raw_text = (
        "FR1: The librarian shall register a member.\n"
        "As a member, I want to borrow books, so that I can study."
    )
    _, parsed_meta, _ = integrated.parse_input_requirements(raw_text)

    asyncio.run(
        integrated.extraction_worker(
            job_id="job_test123",
            project_id="proj_1",
            text=raw_text,
            project_name="Library System",
            document_id="doc_test123",
            source_document="requirements.pdf",
            skipped_pages=[3],
            parsed_metadata=parsed_meta,
        )
    )

    # Verify document and job status transitions
    assert any(f.get("status") == "processed" for _, f in doc_updates)
    assert any(f.get("status") == "succeeded" for _, f in job_updates)

    # Verify statements preserved FR1 and structured user story
    assert len(inserted_statements) == 2
    assert inserted_statements[0].get("source_label") == "FR1"
    assert inserted_statements[1].get("metadata") == {
        "role": "member",
        "goal": "to borrow books",
        "reason": "I can study",
        "structured": True,
    }


def test_docx_upload_and_extraction_end_to_end(monkeypatch):
    import routers.integrated as integrated
    import httpx
    from docx import Document

    # Create a real DOCX in memory
    buf = io.BytesIO()
    doc = Document()
    doc.add_paragraph("FR1: The system shall encrypt stored documents.")
    doc.add_paragraph("As an admin, I want to view reports, so that I track usage.")
    doc.save(buf)

    upload = UploadFile(filename="spec.docx", file=io.BytesIO(buf.getvalue()))
    extracted = asyncio.run(integrated.read_and_extract_upload(upload))

    assert "FR1: The system shall encrypt stored documents." in extracted["text"]
    assert "As an admin, I want to view reports, so that I track usage." in extracted["text"]
    assert extracted["page_count"] >= 1

    job_updates = []
    def fake_update_job(job_id, **fields):
        job_updates.append((job_id, fields))

    doc_updates = []
    def fake_update_doc(doc_id, **fields):
        doc_updates.append((doc_id, fields))

    inserted_statements = []
    def fake_insert_statements(pid, statements, source_document="pasted requirements"):
        inserted_statements.extend(statements)
        return [f"st_{i}" for i in range(len(statements))]

    monkeypatch.setattr(integrated.db, "update_job", fake_update_job)
    monkeypatch.setattr(integrated.db, "update_document", fake_update_doc)
    monkeypatch.setattr(integrated.db, "insert_statements", fake_insert_statements)
    monkeypatch.setattr(integrated.db, "add_system_items", lambda pid, items: None)
    monkeypatch.setattr(integrated.db, "touch_project", lambda pid, clear_confirmation=True: None)
    monkeypatch.setattr(integrated, "detect", lambda pid: True)

    class FakeDocxAI:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, json=None, **kwargs):
            req = httpx.Request("POST", url)
            return httpx.Response(200, request=req, json={
                "requirements": [
                    {
                        "id": "R-101",
                        "text": "The system shall encrypt stored documents.",
                        "labels": ["functional"],
                        "source_location": {"line_start": 1, "excerpt": "FR1: The system shall encrypt stored documents."},
                    },
                    {
                        "id": "R-102",
                        "text": "As an admin, I want to view reports, so that I track usage.",
                        "labels": ["functional"],
                        "source_location": {"line_start": 2, "excerpt": "As an admin, I want to view reports, so that I track usage."},
                    },
                ],
                "actors": [{"name": "Admin", "description": "System administrator"}],
                "entities": [{"name": "Report", "description": "Usage report"}],
                "processes": [],
                "data_flows": [],
                "data_stores": [],
            })

    monkeypatch.setattr(integrated.httpx, "AsyncClient", FakeDocxAI)

    text_for_ai, parsed_meta, _ = integrated.parse_input_requirements(extracted["text"])

    asyncio.run(
        integrated.extraction_worker(
            job_id="job_docx_456",
            project_id="proj_docx_1",
            text=text_for_ai,
            project_name="Docx System",
            document_id="doc_docx_456",
            source_document="spec.docx",
            skipped_pages=[],
            parsed_metadata=parsed_meta,
        )
    )

    assert any(f.get("status") == "processed" for _, f in doc_updates)
    assert any(f.get("status") == "succeeded" for _, f in job_updates)
    assert len(inserted_statements) == 2
    assert inserted_statements[0].get("source_label") == "FR1"
    assert inserted_statements[1].get("metadata") == {
        "role": "admin",
        "goal": "to view reports",
        "reason": "I track usage",
        "structured": True,
    }


def test_failed_extraction_updates_document_and_job_status_and_records_error(monkeypatch):
    import routers.integrated as integrated

    doc_updates = []
    job_updates = []
    failed_job_errors = []

    monkeypatch.setattr(integrated.db, "update_document", lambda doc_id, **kwargs: doc_updates.append((doc_id, kwargs)))
    monkeypatch.setattr(integrated.db, "update_job", lambda jid, **kwargs: job_updates.append((jid, kwargs)))
    monkeypatch.setattr(integrated, "fail_job", lambda jid, err: failed_job_errors.append((jid, err)))

    class FailingAIClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, json=None, **kwargs):
            req = httpx.Request("POST", url)
            return httpx.Response(500, request=req, text="AI model rate limited or crashed")

    monkeypatch.setattr(integrated.httpx, "AsyncClient", FailingAIClient)

    asyncio.run(
        integrated.extraction_worker(
            job_id="job_fail_789",
            project_id="proj_fail_1",
            text="Some requirements",
            project_name="Fail System",
            document_id="doc_fail_789",
            source_document="broken.pdf",
            skipped_pages=[],
            parsed_metadata={},
        )
    )

    # 1. Job must be marked failed with specific error
    assert len(failed_job_errors) == 1
    assert failed_job_errors[0][0] == "job_fail_789"
    assert "Extraction failed" in failed_job_errors[0][1]

    # 2. Document must transition to 'failed' (not remain in 'processing')
    assert any(f.get("status") == "failed" for _, f in doc_updates)
    last_doc_update = doc_updates[-1][1]
    assert last_doc_update.get("status") == "failed"
    assert "Extraction failed" in last_doc_update.get("warning", "")


def test_sample_pdf_extracts_statements_user_stories_and_fr_nfr_ids():
    import io
    from pathlib import Path
    from core.input_processing import read_and_extract_upload, extract_fallback_statements_and_items

    pdf_path = Path("/Users/kavya/Downloads/SDDG_FR1_FR2_Test_SRS.pdf")
    assert pdf_path.exists(), "Sample test PDF must exist"

    class MockUpload:
        def __init__(self, filename, data):
            self.filename = filename
            self._bio = io.BytesIO(data)
        async def read(self, size=-1):
            return self._bio.read(size)

    upload = MockUpload(pdf_path.name, pdf_path.read_bytes())
    extracted = asyncio.run(read_and_extract_upload(upload))
    assert extracted["page_count"] == 2
    assert "FR-001" in extracted["text"]
    assert "As a student" in extracted["text"]

    reqs, result_dict = extract_fallback_statements_and_items(extracted["text"], "CEMS")
    assert len(reqs) >= 20

    # Verify user stories have role, goal, reason
    user_stories = [r for r in reqs if r.get("metadata") and r["metadata"].get("structured")]
    assert len(user_stories) == 5
    assert all(us["metadata"].get("role") and us["metadata"].get("goal") for us in user_stories)

    # Verify FR-001 through FR-010 are parsed
    fr_labels = [r["source_label"] for r in reqs if r.get("source_label") and r["source_label"].startswith("FR-")]
    assert len(fr_labels) == 10
    assert "FR-001" in fr_labels
    assert "FR-010" in fr_labels

    # Verify NFR-001 through NFR-005 are parsed
    nfr_labels = [r["source_label"] for r in reqs if r.get("source_label") and r["source_label"].startswith("NFR-")]
    assert len(nfr_labels) == 5
    assert "NFR-001" in nfr_labels
    assert "NFR-005" in nfr_labels

    # Verify modeling items are created
    assert len(result_dict["actors"]) >= 3
    assert len(result_dict["processes"]) >= 10


def test_extraction_worker_persists_sample_pdf_and_recovers_when_ai_returns_empty(monkeypatch):
    import routers.integrated as integrated
    from pathlib import Path

    pdf_path = Path("/Users/kavya/Downloads/SDDG_FR1_FR2_Test_SRS.pdf")
    text = Path("/tmp/test_srs_text.txt").read_text() if Path("/tmp/test_srs_text.txt").exists() else "FR-001: The system shall register users."

    inserted_statements = []
    inserted_items = []
    job_updates = []
    doc_updates = []

    monkeypatch.setattr(integrated.db, "insert_statements", lambda pid, raw, source_document=None: (
        inserted_statements.extend([{"project_id": pid, **r} for r in raw]),
        [f"st_{i}" for i in range(len(raw))]
    )[1])
    monkeypatch.setattr(integrated.db, "add_system_items", lambda pid, items: inserted_items.extend([{"project_id": pid, **i} for i in items]))
    monkeypatch.setattr(integrated.db, "update_job", lambda jid, **kwargs: job_updates.append((jid, kwargs)))
    monkeypatch.setattr(integrated.db, "update_document", lambda did, **kwargs: doc_updates.append((did, kwargs)))
    monkeypatch.setattr(integrated.db, "touch_project", lambda pid, clear_confirmation=True: None)
    monkeypatch.setattr(integrated, "detect", lambda pid: True)

    class EmptyAIClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, json=None, **kwargs):
            # AI service returned empty requirements
            req = httpx.Request("POST", url)
            return httpx.Response(200, request=req, json={"requirements": []})

    monkeypatch.setattr(integrated.httpx, "AsyncClient", EmptyAIClient)

    asyncio.run(
        integrated.extraction_worker(
            job_id="job_pdf_test",
            project_id="proj_pdf_1",
            text=text,
            project_name="CEMS",
            document_id="doc_pdf_test",
            source_document="SDDG_FR1_FR2_Test_SRS.pdf",
            skipped_pages=[],
            parsed_metadata={},
        )
    )

    # 1. Fallback must have extracted and persisted statements with the correct project ID
    assert len(inserted_statements) >= 20
    assert all(s["project_id"] == "proj_pdf_1" for s in inserted_statements)

    # 2. Items must be persisted with the correct project ID
    assert len(inserted_items) >= 10
    assert all(i["project_id"] == "proj_pdf_1" for i in inserted_items)

    # 3. Statuses must be terminal success
    assert any(kwargs.get("status") == "succeeded" for _, kwargs in job_updates)
    assert any(kwargs.get("status") == "processed" for _, kwargs in doc_updates)


def test_extraction_worker_fails_when_zero_valid_statements(monkeypatch):
    import routers.integrated as integrated

    doc_updates = []
    job_updates = []
    failed_errors = []

    monkeypatch.setattr(integrated.db, "update_document", lambda did, **kwargs: doc_updates.append((did, kwargs)))
    monkeypatch.setattr(integrated.db, "update_job", lambda jid, **kwargs: job_updates.append((jid, kwargs)))
    monkeypatch.setattr(integrated, "fail_job", lambda jid, err: failed_errors.append((jid, err)))

    class EmptyAIClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, json=None, **kwargs):
            req = integrated.httpx.Request("POST", url)
            return integrated.httpx.Response(200, request=req, json={"requirements": []})

    monkeypatch.setattr(integrated.httpx, "AsyncClient", EmptyAIClient)

    # Text that contains no extractable requirements at all
    empty_text = "This is a document about general architecture. No requirements here."

    asyncio.run(
        integrated.extraction_worker(
            job_id="job_zero_req",
            project_id="proj_zero_1",
            text=empty_text,
            project_name="Zero Req",
            document_id="doc_zero_1",
            source_document="empty.pdf",
            skipped_pages=[],
            parsed_metadata={},
        )
    )

    # Document must be marked failed, NEVER marked processed
    assert not any(kwargs.get("status") == "processed" for _, kwargs in doc_updates)
    assert any(kwargs.get("status") == "failed" for _, kwargs in doc_updates)
    assert len(failed_errors) == 1
    assert "No requirements could be extracted" in failed_errors[0][1]


