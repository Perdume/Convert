"""업로드 검증(매직 바이트), IP 레이트리밋, 보안 응답 헤더."""
import re
import threading
import time
import zipfile
from collections import deque
from pathlib import Path

import olefile
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from . import config


class ValidationError(Exception):
    pass


_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def sniff_format(path: Path) -> str:
    """파일 내용(매직 바이트·내부 구조)으로 실제 형식을 판별한다.

    확장자만 믿지 않는다 — 확장자를 위조한 악성 파일 업로드를 차단하기 위함.
    """
    with open(path, "rb") as f:
        head = f.read(8)

    if head.startswith(b"%PDF-"):
        return "pdf"

    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
        except zipfile.BadZipFile:
            raise ValidationError("손상되었거나 지원하지 않는 파일입니다.")
        if "[Content_Types].xml" in names and any(n.startswith("ppt/") for n in names):
            return "pptx"
        raise ValidationError("지원하지 않는 파일 형식입니다. (HWP, PPT/PPTX, PDF만 가능)")

    if head.startswith(_OLE_MAGIC):
        try:
            ole = olefile.OleFileIO(str(path))
        except Exception:
            raise ValidationError("손상되었거나 지원하지 않는 파일입니다.")
        try:
            if ole.exists("FileHeader"):
                sig = ole.openstream("FileHeader").read(32)
                if sig.startswith(b"HWP Document File"):
                    return "hwp"
            if ole.exists("PowerPoint Document"):
                return "ppt"
        finally:
            ole.close()
        raise ValidationError("지원하지 않는 파일 형식입니다. (HWP, PPT/PPTX, PDF만 가능)")

    raise ValidationError("지원하지 않는 파일 형식입니다. (HWP, PPT/PPTX, PDF만 가능)")


def safe_download_name(original: str | None, target_ext: str) -> str:
    """원본 파일명에서 경로·제어문자를 제거한 다운로드용 이름을 만든다."""
    stem = Path(original or "").stem
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", stem).strip(" .")[:80]
    return f"{stem or 'converted'}.{target_ext}"


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
            # 오래된 키 정리
            if len(self._hits) > 10000:
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # HTTPS로 서비스될 때만 의미 있음 — 브라우저가 이후 접속을 HTTPS로 강제
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
