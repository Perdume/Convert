"""서비스 설정. 파일 보관·용량·동시성 한도와 '어떤 형식을 어떤 형식으로 바꿀 수
있는가'(변환 매트릭스)를 전부 여기서 한곳에 모아 관리한다.

프런트엔드와 백엔드가 같은 매트릭스를 공유하도록, 지원 변환 목록은
``capabilities()`` 하나에서 생성해 ``/api/capabilities`` 로도 그대로 내보낸다.
"""
import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CONVERT_DATA_DIR", str(BASE_DIR / "data")))
JOBS_DIR = DATA_DIR / "jobs"
STATIC_DIR = BASE_DIR / "static"

MAX_UPLOAD_BYTES = 100 * 1024 * 1024     # 업로드 최대 100MB
MAX_PDF_PAGES = 300                       # 이미지 변환 시 페이지 상한 (DoS 방지)
IMAGE_DPI = 150                           # PDF 페이지를 이미지로 렌더링할 해상도
JOB_TTL_SECONDS = 600                     # 미다운로드 결과물·대기 중 작업 최대 보관 시간
SWEEP_INTERVAL_SECONDS = 30
CONVERT_TIMEOUT_SECONDS = 180
MAX_CONCURRENT_CONVERSIONS = int(os.environ.get("MAX_CONCURRENT_CONVERSIONS", "2"))
RATE_LIMIT_MAX = 15                       # IP당 분당 변환 요청 수
RATE_LIMIT_WINDOW = 60
MAX_PASSWORD_ATTEMPTS = 5                 # 암호 문서 1건당 비밀번호 시도 횟수 상한

# ── 입력 형식 ───────────────────────────────────────────────────────────────
CAT_DOC = {"doc", "docx", "odt", "rtf", "txt", "hwp"}          # 글 문서
CAT_PRES = {"ppt", "pptx", "odp"}                              # 프레젠테이션
CAT_SHEET = {"xls", "xlsx", "ods", "csv"}                      # 스프레드시트
CAT_IMAGE = {"jpg", "jpeg", "png", "bmp", "tiff", "tif", "webp", "gif"}  # 이미지
CAT_PDF = {"pdf"}

INPUT_FORMATS = CAT_DOC | CAT_PRES | CAT_SHEET | CAT_IMAGE | CAT_PDF

# ── 출력 형식 ───────────────────────────────────────────────────────────────
#   editable  : 문서를 해석해 '편집 가능한' 형식으로 (LibreOffice)
#   pages     : 각 페이지를 이미지로 배치 (모양 유지, 편집 제한)
#   unlock    : 비밀번호로 암호를 해제한 '같은 형식' 원본
OUTPUT_FORMATS = {"pdf", "docx", "odt", "pptx", "xlsx", "hwpx", "images", "txt", "unlock"}

# 형식별 한국어 라벨 — 입력/출력 공용
FORMAT_LABEL = {
    "pdf": "PDF", "doc": "워드 (DOC)", "docx": "워드 (DOCX)", "odt": "ODT",
    "rtf": "서식 텍스트 (RTF)", "txt": "텍스트 (TXT)", "hwp": "한글 (HWP)",
    "ppt": "파워포인트 (PPT)", "pptx": "파워포인트 (PPTX)", "odp": "ODP",
    "xls": "엑셀 (XLS)", "xlsx": "엑셀 (XLSX)", "ods": "ODS", "csv": "CSV",
    "jpg": "JPG", "jpeg": "JPEG", "png": "PNG", "bmp": "BMP", "tiff": "TIFF",
    "tif": "TIFF", "webp": "WebP", "gif": "GIF",
    "images": "이미지 (PNG)", "unlock": "암호 해제",
}

# 출력 형식별 기본 안내 문구
TARGET_HINT = {
    "pdf": "어디서나 똑같이 보이는 표준 문서 형식입니다.",
    "docx": "MS 워드·구글 문서에서 열고 편집할 수 있습니다.",
    "odt": "LibreOffice·구글 문서 등에서 열리는 개방형 문서 형식입니다.",
    "pptx": "MS 파워포인트에서 열 수 있는 슬라이드 형식입니다.",
    "xlsx": "MS 엑셀·구글 시트에서 열 수 있는 표 형식입니다.",
    "hwpx": "한글 2014 이상에서 열리는 형식입니다. 페이지가 이미지로 들어가 모양은 유지되지만 편집은 제한됩니다.",
    "images": "각 페이지를 고해상도 PNG 이미지로 저장해 ZIP으로 묶어 드립니다.",
    "txt": "문서의 글자만 뽑아 순수 텍스트로 저장합니다. (서식·이미지 제외)",
    "unlock": "입력한 비밀번호로 암호를 해제한 원본 형식 파일을 그대로 돌려드립니다.",
}


def targets_for(src_fmt: str) -> list[str]:
    """입력 형식 하나가 바뀔 수 있는 출력 형식 목록(의미 없는 자기 변환 제외)."""
    if src_fmt in CAT_DOC:
        t = ["pdf", "docx", "odt", "hwpx", "images", "txt"]
    elif src_fmt in CAT_PRES:
        t = ["pdf", "pptx", "hwpx", "docx", "images"]
    elif src_fmt in CAT_SHEET:
        t = ["pdf", "xlsx", "images"]
    elif src_fmt in CAT_IMAGE:
        t = ["pdf"]
    elif src_fmt == "pdf":
        t = ["docx", "pptx", "hwpx", "images", "txt"]
    else:
        t = []
    # 자기 자신으로의 변환과 같은-계열(한글 hwp↔hwpx) 변환은 뺀다
    skip = {src_fmt}
    if src_fmt == "hwp":
        skip.add("hwpx")
    return [x for x in t if x not in skip]


def capabilities() -> dict:
    """프런트엔드가 그대로 쓰는 변환 매트릭스.

    { fmt: {label, category, targets:[{value,label,hint}]} }
    """
    cat_of = {
        **{f: "doc" for f in CAT_DOC},
        **{f: "pres" for f in CAT_PRES},
        **{f: "sheet" for f in CAT_SHEET},
        **{f: "image" for f in CAT_IMAGE},
        "pdf": "pdf",
    }
    out: dict = {}
    for fmt in sorted(INPUT_FORMATS):
        targets = targets_for(fmt)
        if not targets:
            continue
        out[fmt] = {
            "label": FORMAT_LABEL.get(fmt, fmt.upper()),
            "category": cat_of.get(fmt, "other"),
            "targets": [
                {"value": v, "label": FORMAT_LABEL.get(v, v.upper()),
                 "hint": TARGET_HINT.get(v, "")}
                for v in targets
            ],
        }
    return {
        "formats": out,
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "unlock": {"label": FORMAT_LABEL["unlock"], "hint": TARGET_HINT["unlock"]},
    }


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
