"""파일 변환 엔진.

모든 변환은 서버 내부에서만 수행된다 — 파일이 외부 서비스로 전송되지 않는다.

변환 경로:
  PPT/PPTX → PDF   : LibreOffice headless
  HWP → PDF        : pyhwp(HWP→ODT) → LibreOffice(ODT→PDF)
  PDF → PPTX       : 페이지를 고해상도 이미지로 렌더링해 슬라이드로 배치
  HWP → PPTX       : HWP→PDF→PPTX
  PDF/PPT → HWPX   : 페이지 이미지를 한글(HWPX) 문서로 배치
"""
import io
import logging
import subprocess
import sys
from pathlib import Path

import fitz  # PyMuPDF
from pptx import Presentation
from pptx.util import Emu

from . import config

# HWPX 내부 단위: 1 HWPUNIT = 1/7200 inch, PDF 포인트(1/72 inch) = 100 HWPUNIT
_HWPUNIT_PER_PT = 100
_MM_PER_PT = 25.4 / 72
_EMU_PER_PT = 12700


logger = logging.getLogger("converter")


class ConversionError(Exception):
    pass


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    try:
        proc = subprocess.run(
            cmd, capture_output=True,
            timeout=config.CONVERT_TIMEOUT_SECONDS,
            cwd=str(cwd) if cwd else None,
        )
    except subprocess.TimeoutExpired:
        raise ConversionError("변환 시간이 초과되었습니다.")
    if proc.returncode != 0:
        # 내부 오류 상세는 서버 로그에만 남기고, 사용자에게는 일반화된 메시지만 보낸다
        detail = (proc.stderr or proc.stdout or b"")[:4000].decode("utf-8", "replace")
        logger.error("conversion subprocess failed (rc=%s, cmd=%s): %s",
                      proc.returncode, cmd[0], detail.strip())
        lowered = detail.lower()
        if "password" in lowered or "encrypt" in lowered or "distribut" in lowered:
            raise ConversionError("암호화되었거나 배포용(보안) 문서는 변환할 수 없습니다.")
        raise ConversionError(
            "파일을 변환하지 못했습니다. 문서가 손상되었거나 "
            "지원하지 않는 형식·기능을 포함하고 있을 수 있습니다.")


def _soffice_convert(src: Path, target_ext: str, outdir: Path) -> Path:
    if not config.SOFFICE:
        raise ConversionError("서버에 LibreOffice가 설치되어 있지 않습니다.")
    # 작업별 격리 프로필 — 동시 실행 충돌과 사용자 프로필 오염을 막는다
    profile = outdir / "lo_profile"
    cmd = [
        config.SOFFICE, "--headless", "--norestore", "--nolockcheck", "--nodefault",
        f"-env:UserInstallation={profile.absolute().as_uri()}",
        "--convert-to", target_ext, "--outdir", str(outdir), str(src),
    ]
    _run(cmd)
    out = outdir / f"{src.stem}.{target_ext}"
    if not out.exists():
        raise ConversionError("변환 결과가 생성되지 않았습니다. 파일이 손상되었을 수 있습니다.")
    return out


def _hwp_to_odt(src: Path, outdir: Path) -> Path:
    # RelaxNG 검증을 끈 전용 워커 사용 — hwp5odt_worker.py 참고
    worker = Path(__file__).with_name("hwp5odt_worker.py")
    out = outdir / f"{src.stem}.odt"
    _run([sys.executable, str(worker), str(src), str(out)])
    if not out.exists() or out.stat().st_size == 0:
        raise ConversionError("HWP 파일을 읽지 못했습니다. 암호화되었거나 지원하지 않는 버전일 수 있습니다.")
    return out


def _render_pdf_pages(pdf_path: Path, dpi: int = 150):
    """PDF 각 페이지를 (PNG bytes, 폭 pt, 높이 pt)로 렌더링한다."""
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        raise ConversionError("PDF 파일을 열 수 없습니다. 파일이 손상되었을 수 있습니다.")
    try:
        if doc.needs_pass:
            raise ConversionError("암호로 보호된 PDF는 변환할 수 없습니다.")
        if doc.page_count == 0:
            raise ConversionError("페이지가 없는 PDF입니다.")
        if doc.page_count > config.MAX_PDF_PAGES:
            raise ConversionError(f"페이지 수가 너무 많습니다. (최대 {config.MAX_PDF_PAGES}페이지)")
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            yield pix.tobytes("png"), page.rect.width, page.rect.height
    finally:
        doc.close()


def _pdf_to_pptx(pdf_path: Path, outdir: Path) -> Path:
    pres = Presentation()
    blank = pres.slide_layouts[6]
    first = True
    for png, w_pt, h_pt in _render_pdf_pages(pdf_path):
        if first:
            pres.slide_width = Emu(int(w_pt * _EMU_PER_PT))
            pres.slide_height = Emu(int(h_pt * _EMU_PER_PT))
            first = False
        slide = pres.slides.add_slide(blank)
        slide.shapes.add_picture(io.BytesIO(png), 0, 0,
                                 width=pres.slide_width, height=pres.slide_height)
    out = outdir / "result.pptx"
    pres.save(str(out))
    return out


def _pdf_to_hwpx(pdf_path: Path, outdir: Path) -> Path:
    from hwpx import HwpxDocument

    doc = HwpxDocument.new()
    first = True
    for png, w_pt, h_pt in _render_pdf_pages(pdf_path):
        if first:
            doc.set_page_size(
                width=int(w_pt * _HWPUNIT_PER_PT),
                height=int(h_pt * _HWPUNIT_PER_PT),
                orientation="landscape" if w_pt > h_pt else "portrait",
            )
            try:
                doc.set_page_margins(left=0, right=0, top=0, bottom=0,
                                     header=0, footer=0, gutter=0)
            except TypeError:
                doc.set_page_margins(left=0, right=0, top=0, bottom=0)
            first = False
        doc.add_picture(png, "png",
                        width_mm=w_pt * _MM_PER_PT, height_mm=h_pt * _MM_PER_PT)
    out = outdir / "result.hwpx"
    doc.save_to_path(str(out))
    return out


def _pdf_to_docx(pdf_path: Path, outdir: Path) -> Path:
    """PDF 페이지를 전면 이미지로 배치한 워드 문서를 만든다."""
    from docx import Document
    from docx.shared import Emu

    doc = Document()
    section = doc.sections[0]
    first = True
    for png, w_pt, h_pt in _render_pdf_pages(pdf_path):
        if first:
            section.page_width = Emu(int(w_pt * _EMU_PER_PT))
            section.page_height = Emu(int(h_pt * _EMU_PER_PT))
            section.left_margin = section.right_margin = Emu(0)
            section.top_margin = section.bottom_margin = Emu(0)
            section.header_distance = section.footer_distance = Emu(0)
            first = False
        p = doc.add_paragraph()  # 한 문단 = 한 페이지
        p.paragraph_format.space_before = Emu(0)
        p.paragraph_format.space_after = Emu(0)
        p.add_run().add_picture(io.BytesIO(png),
                                width=Emu(int(w_pt * _EMU_PER_PT)),
                                height=Emu(int(h_pt * _EMU_PER_PT)))
    out = outdir / "result.docx"
    doc.save(str(out))
    return out


def _to_pdf(src: Path, src_fmt: str, outdir: Path) -> Path:
    if src_fmt == "pdf":
        return src
    if src_fmt in ("ppt", "pptx"):
        return _soffice_convert(src, "pdf", outdir)
    if src_fmt == "hwp":
        odt = _hwp_to_odt(src, outdir)
        return _soffice_convert(odt, "pdf", outdir)
    raise ConversionError("지원하지 않는 입력 형식입니다.")


def convert(src: Path, src_fmt: str, target: str, outdir: Path) -> Path:
    """src(형식 src_fmt)를 target 형식으로 변환해 결과 경로를 돌려준다."""
    if target == "pdf":
        result = _to_pdf(src, src_fmt, outdir)
        if result == src:
            raise ConversionError("이미 PDF 파일입니다.")
        return result
    if target == "pptx":
        if src_fmt in ("ppt", "pptx"):
            raise ConversionError("이미 PPT 파일입니다.")
        return _pdf_to_pptx(_to_pdf(src, src_fmt, outdir), outdir)
    if target == "hwpx":
        if src_fmt == "hwp":
            raise ConversionError("이미 한글 파일입니다.")
        return _pdf_to_hwpx(_to_pdf(src, src_fmt, outdir), outdir)
    if target == "docx":
        # 한컴오피스 없이 MS워드·구글 Docs에서 열 수 있는 형식.
        # HWP는 문서를 해석해 편집 가능한 워드로, PDF/PPT는 페이지 이미지로 배치한다.
        if src_fmt == "hwp":
            odt = _hwp_to_odt(src, outdir)
            return _soffice_convert(odt, "docx", outdir)
        return _pdf_to_docx(_to_pdf(src, src_fmt, outdir), outdir)
    raise ConversionError("지원하지 않는 변환 형식입니다.")
