"""업로드 검증(매직 바이트), 암호화 여부 탐지, IP 레이트리밋, 보안 응답 헤더.

확장자는 믿지 않는다 — 파일의 실제 내용(시그니처·내부 구조)으로 형식을 판별해
확장자를 위조한 업로드를 막는다. 암호가 걸린 문서는 여기서 탐지만 하고,
실제 해제는 사용자가 비밀번호를 제공할 때 decrypt 모듈이 수행한다.
"""
import re
import threading
import time
import zipfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import olefile
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from . import config


class ValidationError(Exception):
    pass


_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_UNSUPPORTED = "지원하지 않는 파일 형식입니다. (HWP·DOC·PPT·XLS·PDF·이미지 등)"


@dataclass
class Probe:
    """업로드 파일을 들여다본 결과."""
    fmt: str                 # 판별된 실제 형식 (ooxml-encrypted는 복호화 전까지 "ooxml")
    encrypted: bool = False  # 비밀번호가 걸려 있는가


def _image_fmt(head: bytes) -> str:
    if head[:3] == b"\xff\xd8\xff":
        return "jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:2] == b"BM":
        return "bmp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return ""


def _zip_fmt(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            mimetype = ""
            if "mimetype" in names:
                try:
                    mimetype = z.read("mimetype").decode("ascii", "replace").strip()
                except Exception:
                    mimetype = ""
    except zipfile.BadZipFile:
        raise ValidationError("손상되었거나 지원하지 않는 파일입니다.")
    if "[Content_Types].xml" in names:
        if any(n.startswith("ppt/") for n in names):
            return "pptx"
        if any(n.startswith("word/") for n in names):
            return "docx"
        if any(n.startswith("xl/") for n in names):
            return "xlsx"
    if mimetype == "application/vnd.oasis.opendocument.text":
        return "odt"
    if mimetype == "application/vnd.oasis.opendocument.presentation":
        return "odp"
    if mimetype == "application/vnd.oasis.opendocument.spreadsheet":
        return "ods"
    return ""


def _office_is_encrypted(path: Path) -> bool:
    """MS 오피스(구/신) 파일에 비밀번호가 걸려 있는지 확인."""
    try:
        import msoffcrypto
        with open(path, "rb") as f:
            return bool(msoffcrypto.OfficeFile(f).is_encrypted())
    except Exception:
        return False


def _ole_probe(path: Path) -> Probe:
    try:
        ole = olefile.OleFileIO(str(path))
    except Exception:
        raise ValidationError("손상되었거나 지원하지 않는 파일입니다.")
    try:
        comps = {p.lower() for entry in ole.listdir() for p in entry}
        # 암호화된 OOXML(docx/xlsx/pptx)은 OLE 컨테이너 안에 암호화 스트림만 있다.
        # 실제 하위 형식은 복호화해 봐야 알 수 있으므로 "ooxml"로 표시한다.
        if "encryptedpackage" in comps or "encryptioninfo" in comps:
            return Probe("ooxml", encrypted=True)
        fmt = ""
        if ole.exists("FileHeader"):
            sig = ole.openstream("FileHeader").read(32)
            if sig.startswith(b"HWP Document File"):
                fmt = "hwp"
        if not fmt and "worddocument" in comps:
            fmt = "doc"
        if not fmt and "powerpoint document" in comps:
            fmt = "ppt"
        if not fmt and ("workbook" in comps or "book" in comps):
            fmt = "xls"
    finally:
        ole.close()
    if not fmt:
        raise ValidationError(_UNSUPPORTED)
    return Probe(fmt, encrypted=_office_is_encrypted(path))


def _pdf_is_encrypted(path: Path) -> bool:
    try:
        import pymupdf
        doc = pymupdf.open(str(path))
        try:
            return bool(doc.needs_pass)
        finally:
            doc.close()
    except Exception:
        return False


def looks_like_text(path: Path, declared_ext: str) -> str:
    """시그니처가 없는 순수 텍스트(txt/csv)를 내용으로 검증한다.

    바이너리(널 바이트 포함)는 거부하고, UTF-8 또는 한글 완성형(CP949)으로
    해독되는 경우에만 선언된 확장자(txt/csv)를 그대로 인정한다.
    """
    if declared_ext not in ("txt", "csv"):
        return ""
    try:
        with open(path, "rb") as f:
            sample = f.read(1024 * 1024)
    except OSError:
        return ""
    if not sample or b"\x00" in sample:
        return ""
    for enc in ("utf-8", "cp949"):
        try:
            sample.decode(enc)
            return declared_ext
        except UnicodeDecodeError:
            continue
    return ""


def probe(path: Path, declared_ext: str = "") -> Probe:
    """파일 내용으로 실제 형식과 암호화 여부를 판별한다."""
    with open(path, "rb") as f:
        head = f.read(16)

    if head.startswith(b"%PDF-"):
        return Probe("pdf", encrypted=_pdf_is_encrypted(path))

    img = _image_fmt(head)
    if img:
        return Probe(img)

    if head.startswith(b"PK\x03\x04"):
        fmt = _zip_fmt(path)
        if fmt:
            return Probe(fmt)
        raise ValidationError(_UNSUPPORTED)

    if head.startswith(_OLE_MAGIC):
        return _ole_probe(path)

    text = looks_like_text(path, declared_ext)
    if text:
        return Probe(text)

    raise ValidationError(_UNSUPPORTED)


def safe_download_name(original: str | None, final_ext: str) -> str:
    """원본 파일명에서 경로·제어문자를 제거한 다운로드용 이름을 만든다."""
    stem = Path(original or "").stem
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", stem).strip(" .")[:80]
    return f"{stem or 'converted'}.{final_ext}"


class RateLimiter:
    """IP당 슬라이딩 윈도 레이트리밋 (메모리 기반)."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max = max_requests
        self.window = window_seconds
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.max:
                return False
            q.append(now)
            if len(self._hits) > 10000:
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; form-action 'self'; "
            "worker-src 'self'; manifest-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
