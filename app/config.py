"""서비스 설정. 파일 보관·용량·동시성 한도는 전부 여기서 조정한다."""
import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CONVERT_DATA_DIR", str(BASE_DIR / "data")))
JOBS_DIR = DATA_DIR / "jobs"
STATIC_DIR = BASE_DIR / "static"

MAX_UPLOAD_BYTES = 50 * 1024 * 1024      # 업로드 최대 50MB
MAX_PDF_PAGES = 300                       # 이미지 변환 시 페이지 상한 (DoS 방지)
JOB_TTL_SECONDS = 600                     # 미다운로드 결과물 최대 보관 시간
SWEEP_INTERVAL_SECONDS = 30
CONVERT_TIMEOUT_SECONDS = 180
MAX_CONCURRENT_CONVERSIONS = int(os.environ.get("MAX_CONCURRENT_CONVERSIONS", "2"))
RATE_LIMIT_MAX = 10                       # IP당 분당 변환 요청 수
RATE_LIMIT_WINDOW = 60

INPUT_FORMATS = {"hwp", "ppt", "pptx", "pdf"}
OUTPUT_FORMATS = {"pdf", "pptx", "hwpx", "docx"}


def _find_soffice() -> str | None:
    candidates = [os.environ.get("SOFFICE_PATH")]
    candidates += [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
        "/opt/libreoffice/program/soffice",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return shutil.which("soffice")


SOFFICE = _find_soffice()
