"""파일 변환 엔진.

모든 변환은 서버 내부에서만 수행된다 — 파일이 외부 서비스로 전송되지 않는다.

변환 경로:
  무엇이든 → PDF        : 오피스/한글은 LibreOffice, 이미지는 PyMuPDF
  오피스 ↔ 오피스(편집) : LibreOffice (doc/odt/rtf/txt↔docx, ppt/odp→pptx, xls/ods→xlsx)
  HWP → 편집 가능 문서  : pyhwp(HWP→ODT) → LibreOffice(ODT→docx/pdf/txt…)
  PDF/문서 → PPTX/HWPX/DOCX : 각 페이지를 고해상도 이미지로 렌더링해 배치
  문서 → 이미지(ZIP)    : 각 페이지를 PNG로 렌더링해 ZIP으로 묶음
  문서 → TXT            : 글자만 추출 (PDF는 PyMuPDF, 그 외는 LibreOffice)
"""
import io
import logging
import subprocess
import sys
import zipfile
from pathlib import Path

import pymupdf as fitz  # PyMuPDF (구 fitz)
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
        detail = (proc.stderr or proc.stdout or b"")[:4000].decode("utf-8", "replace")
        logger.error("conversion subprocess failed (rc=%s, cmd=%s): %s",
                      proc.returncode, cmd[0], detail.strip())
        lowered = detail.lower()
        if "password" in lowered or "encrypt" in lowered or "distribut" in lowered:
            raise ConversionError("암호화되었거나 배포용(보안) 문서는 변환할 수 없습니다. 먼저 암호를 해제해 주세요.")
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


def _image_to_pdf(src: Path, outdir: Path) -> Path:
    try:
        doc = fitz.open(str(src))
        try:
            pdf_bytes = doc.convert_to_pdf()
        finally:
            doc.close()
    except ConversionError:
        raise
    except Exception:
        raise ConversionError("이미지를 열 수 없습니다. 파일이 손상되었을 수 있습니다.")
    out = outdir / "result.pdf"
    out.write_bytes(pdf_bytes)
    return out


def _render_pdf_pages(pdf_path: Path, dpi: int | None = None):
    """PDF 각 페이지를 (PNG bytes, 폭 pt, 높이 pt)로 렌더링한다."""
    dpi = dpi or config.IMAGE_DPI
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        raise ConversionError("PDF 파일을 열 수 없습니다. 파일이 손상되었을 수 있습니다.")
    try:
        if doc.needs_pass:
            raise ConversionError("암호로 보호된 PDF입니다. 먼저 암호를 해제해 주세요.")
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
    from docx.shared import Emu as DocxEmu

    doc = Document()
    section = doc.sections[0]
    first = True
    for png, w_pt, h_pt in _render_pdf_pages(pdf_path):
        if first:
            section.page_width = DocxEmu(int(w_pt * _EMU_PER_PT))
            section.page_height = DocxEmu(int(h_pt * _EMU_PER_PT))
            section.left_margin = section.right_margin = DocxEmu(0)
            section.top_margin = section.bottom_margin = DocxEmu(0)
            section.header_distance = section.footer_distance = DocxEmu(0)
            first = False
        p = doc.add_paragraph()  # 한 문단 = 한 페이지
        p.paragraph_format.space_before = DocxEmu(0)
        p.paragraph_format.space_after = DocxEmu(0)
        p.add_run().add_picture(io.BytesIO(png),
                                width=DocxEmu(int(w_pt * _EMU_PER_PT)),
                                height=DocxEmu(int(h_pt * _EMU_PER_PT)))
    out = outdir / "result.docx"
    doc.save(str(out))
    return out


def _pdf_to_images_zip(pdf_path: Path, outdir: Path) -> Path:
    """PDF 각 페이지를 PNG로 렌더링해 ZIP 한 개로 묶는다."""
    out = outdir / "result.zip"
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for i, (png, _w, _h) in enumerate(_render_pdf_pages(pdf_path), 1):
            z.writestr(f"page_{i:03d}.png", png)
            count += 1
    if count == 0:
        raise ConversionError("변환할 페이지가 없습니다.")
    return out


def _to_txt(src: Path, src_fmt: str, outdir: Path) -> Path:
    out = outdir / "result.txt"
    if src_fmt == "pdf":
        try:
            doc = fitz.open(str(src))
        except Exception:
            raise ConversionError("PDF 파일을 열 수 없습니다.")
        try:
            if doc.needs_pass:
                raise ConversionError("암호로 보호된 PDF입니다. 먼저 암호를 해제해 주세요.")
            parts = [page.get_text() for page in doc]
        finally:
            doc.close()
        out.write_text("\n\n".join(parts), encoding="utf-8")
        return out
    if src_fmt == "hwp":
        odt = _hwp_to_odt(src, outdir)
        return _soffice_convert(odt, "txt", outdir)
    if src_fmt in config.CAT_DOC:
        return _soffice_convert(src, "txt", outdir)
    raise ConversionError("이 형식은 텍스트로 변환할 수 없습니다.")


def _to_pdf(src: Path, src_fmt: str, outdir: Path) -> Path:
    if src_fmt == "pdf":
        return src
    if src_fmt in config.CAT_IMAGE:
        return _image_to_pdf(src, outdir)
    if src_fmt == "hwp":
        odt = _hwp_to_odt(src, outdir)
        return _soffice_convert(odt, "pdf", outdir)
    if src_fmt in (config.CAT_DOC | config.CAT_PRES | config.CAT_SHEET):
        return _soffice_convert(src, "pdf", outdir)
    raise ConversionError("지원하지 않는 입력 형식입니다.")


def convert(src: Path, src_fmt: str, target: str, outdir: Path) -> Path:
    """src(형식 src_fmt)를 target 형식으로 변환해 결과 경로를 돌려준다."""
    DOC, PRES, SHEET = config.CAT_DOC, config.CAT_PRES, config.CAT_SHEET

    if target == "pdf":
        if src_fmt == "pdf":
            raise ConversionError("이미 PDF 파일입니다.")
        return _to_pdf(src, src_fmt, outdir)

    if target == "docx":
        if src_fmt == "docx":
            raise ConversionError("이미 워드(DOCX) 파일입니다.")
        if src_fmt == "hwp":
            odt = _hwp_to_odt(src, outdir)
            return _soffice_convert(odt, "docx", outdir)
        if src_fmt in DOC:                      # doc/odt/rtf/txt → 편집 가능한 워드
            return _soffice_convert(src, "docx", outdir)
        return _pdf_to_docx(_to_pdf(src, src_fmt, outdir), outdir)  # pdf/ppt/이미지 → 페이지 이미지

    if target == "odt":
        if src_fmt == "odt":
            raise ConversionError("이미 ODT 파일입니다.")
        if src_fmt == "hwp":
            return _hwp_to_odt(src, outdir)      # HWP → ODT (바로 생성됨)
        if src_fmt in DOC:
            return _soffice_convert(src, "odt", outdir)
        raise ConversionError("이 형식은 ODT로 변환할 수 없습니다.")

    if target == "pptx":
        if src_fmt == "pptx":
            raise ConversionError("이미 파워포인트(PPTX) 파일입니다.")
        if src_fmt in PRES:                      # ppt/odp → 편집 가능한 pptx
            return _soffice_convert(src, "pptx", outdir)
        return _pdf_to_pptx(_to_pdf(src, src_fmt, outdir), outdir)

    if target == "xlsx":
        if src_fmt == "xlsx":
            raise ConversionError("이미 엑셀(XLSX) 파일입니다.")
        if src_fmt in SHEET:                     # xls/ods/csv → 편집 가능한 엑셀
            return _soffice_convert(src, "xlsx", outdir)
        raise ConversionError("이 형식은 엑셀로 변환할 수 없습니다.")

    if target == "hwpx":
        if src_fmt == "hwp":
            raise ConversionError("이미 한글 파일입니다.")
        return _pdf_to_hwpx(_to_pdf(src, src_fmt, outdir), outdir)

    if target == "images":
        return _pdf_to_images_zip(_to_pdf(src, src_fmt, outdir), outdir)

    if target == "txt":
        if src_fmt == "txt":
            raise ConversionError("이미 텍스트 파일입니다.")
        return _to_txt(src, src_fmt, outdir)

    raise ConversionError("지원하지 않는 변환 형식입니다.")
