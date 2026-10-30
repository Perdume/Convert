"""API 동작 테스트.

실행: pip install pytest httpx && pytest -q
LibreOffice가 없는 환경에서는 LibreOffice가 필요한 변환 테스트만 건너뛴다.
"""
import io
import os
import tempfile

import pytest

os.environ.setdefault("CONVERT_DATA_DIR", tempfile.mkdtemp(prefix="convert-test-"))

import pymupdf as fitz  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.util import Inches  # noqa: E402

from app import config, main  # noqa: E402

needs_soffice = pytest.mark.skipif(config.SOFFICE is None, reason="LibreOffice 미설치")


@pytest.fixture()
def client():
    main.rate_limiter._hits.clear()
    with TestClient(main.app) as c:
        yield c


def make_pdf(pages: int = 2) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"Page {i + 1}", fontsize=24)
    data = doc.tobytes()
    doc.close()
    return data


def make_pptx() -> bytes:
    pres = Presentation()
    slide = pres.slides.add_slide(pres.slide_layouts[5])
    slide.shapes.title.text = "Hello"
    slide.shapes.add_textbox(Inches(1), Inches(2), Inches(4), Inches(1)).text = "test"
    buf = io.BytesIO()
    pres.save(buf)
    return buf.getvalue()


def test_info_lists_conversions(client):
    r = client.get("/api/info")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "convert"
    assert body["max_upload_mb"] == 50
    assert body["conversions"]["pdf"] == ["pptx", "hwpx", "docx"]
    assert set(body["conversions"]) == {"hwp", "ppt", "pptx", "pdf"}
    assert r.headers["cache-control"] == "no-store"


def test_rejects_unsupported_pair_before_converting(client):
    r = client.post("/api/convert", data={"target": "pdf"},
                    files={"file": ("a.pdf", make_pdf(), "application/pdf")})
    assert r.status_code == 400
    assert "PPTX, HWPX, DOCX" in r.json()["detail"]


def test_rejects_extension_mismatch(client):
    r = client.post("/api/convert", data={"target": "pptx"},
                    files={"file": ("a.pdf", make_pptx(), "application/pdf")})
    assert r.status_code == 400


def test_rate_limit_sends_retry_after(client):
    for _ in range(config.RATE_LIMIT_MAX):
        client.post("/api/convert", data={"target": "pdf"},
                    files={"file": ("a.txt", b"x", "text/plain")})
    r = client.post("/api/convert", data={"target": "pdf"},
                    files={"file": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 429
    wait = int(r.headers["retry-after"])
    assert 1 <= wait <= config.RATE_LIMIT_WINDOW


def test_pdf_to_pptx_and_one_time_download(client):
    r = client.post("/api/convert", data={"target": "pptx"},
                    files={"file": ("보고서.pdf", make_pdf(3), "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filename"] == "보고서.pptx"

    d = client.get(f"/api/download/{body['token']}")
    assert d.status_code == 200
    assert len(Presentation(io.BytesIO(d.content)).slides) == 3

    # 1회용 토큰: 두 번째 다운로드는 불가
    assert client.get(f"/api/download/{body['token']}").status_code == 404


@needs_soffice
def test_pptx_to_pdf(client):
    r = client.post("/api/convert", data={"target": "pdf"},
                    files={"file": ("slides.pptx", make_pptx(), "application/octet-stream")})
    assert r.status_code == 200, r.text
    d = client.get(f"/api/download/{r.json()['token']}")
    assert d.content.startswith(b"%PDF-")
