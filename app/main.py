"""HWP·PPT·PDF·오피스·이미지 상호 변환 웹서비스.

보안 설계:
  - 파일은 무작위 이름의 격리 폴더에만 저장, 원본은 변환 직후 즉시 삭제
  - 결과물은 1회 다운로드 후 즉시 삭제, 미다운로드 시 10분 뒤 자동 삭제
  - 삭제는 0으로 덮어쓴 뒤 수행 (복구 방지 최선 노력)
  - 매직 바이트로 실제 파일 형식 검증 (확장자 위조 차단)
  - 다운로드는 추측 불가능한 1회용 토큰으로만 가능
  - 암호 문서는 '사용자가 입력한 비밀번호'로만 해제 (추측·우회 없음, 시도 횟수 제한)
  - IP당 레이트리밋, 용량 제한, 변환 타임아웃, 동시 실행 제한
  - 외부 API로 파일을 전송하지 않음 (전 과정 서버 내부 처리)
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import config, decrypt, security, storage
from . import convert as engine

logger = logging.getLogger("converter")

job_store = storage.JobStore()
rate_limiter = security.RateLimiter(config.RATE_LIMIT_MAX, config.RATE_LIMIT_WINDOW)
convert_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_CONVERSIONS)


async def _sweeper():
    while True:
        await asyncio.sleep(config.SWEEP_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(job_store.sweep)
        except Exception:
            logger.exception("sweep failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_sweeper())
    yield
    task.cancel()
    job_store.delete_all()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(security.SecurityHeadersMiddleware)


def _final_ext(target: str, real_fmt: str) -> str:
    if target == "images":
        return "zip"
    if target == "unlock":
        return real_fmt
    return target


def _finish(job: storage.Job, result_path: Path, original: str, final_ext: str) -> dict:
    # 원본·중간 산출물은 변환이 끝나는 즉시 삭제 (결과물만 남김)
    storage.cleanup_except(job.dir, result_path)
    job.result_path = result_path
    job.src_path = None
    job.download_name = security.safe_download_name(original, final_ext)
    return {"ok": True, "token": job.token, "filename": job.download_name}


def _decrypt_job(job: storage.Job, src: Path, pr: security.Probe, password: str):
    """사용자가 준 비밀번호로 복호화해 (복호화 경로, 실제 형식)을 돌려준다."""
    if pr.fmt == "pdf":
        dst = job.dir / "decrypted.pdf"
        decrypt.decrypt_pdf(src, password, dst)
        return dst, "pdf"
    raw = job.dir / "decrypted.bin"
    decrypt.decrypt_office(src, password, raw)
    real = security.probe(raw).fmt
    if not real or real == "ooxml":
        raise decrypt.DecryptError("암호는 해제했지만 파일 형식을 인식하지 못했습니다.")
    dst = job.dir / f"decrypted.{real}"
    raw.replace(dst)
    return dst, real


def _validate_target(fmt: str, target: str, encrypted: bool) -> None:
    allowed = set(config.targets_for(fmt))
    if encrypted:
        allowed.add("unlock")
    if target not in allowed:
        raise HTTPException(400, f"'{config.FORMAT_LABEL.get(fmt, fmt)}'은(는) 해당 형식으로 변환할 수 없습니다.")


def _do_convert(src: Path, fmt: str, target: str, outdir: Path) -> Path:
    if target == "unlock":
        return src  # 복호화된 파일 자체가 결과물
    return engine.convert(src, fmt, target, outdir)


@app.get("/api/capabilities")
async def api_capabilities():
    return JSONResponse(config.capabilities())


@app.post("/api/convert")
async def api_convert(
    request: Request,
    file: UploadFile = File(...),
    target: str = Form(...),
    password: str = Form(""),
):
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client_ip):
        raise HTTPException(429, "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.")

    target = target.lower().strip()
    if target not in config.OUTPUT_FORMATS:
        raise HTTPException(400, "지원하지 않는 변환 형식입니다.")

    ext = Path(file.filename or "").suffix.lower().lstrip(".")
    if ext not in config.INPUT_FORMATS:
        raise HTTPException(400, "지원하지 않는 파일 형식입니다. (HWP·DOC·PPT·XLS·PDF·이미지 등)")

    job = job_store.create()
    src = job.dir / f"input.{ext}"
    try:
        size = 0
        with open(src, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > config.MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        413, f"파일이 너무 큽니다. (최대 {config.MAX_UPLOAD_BYTES // (1024*1024)}MB)")
                out.write(chunk)
        if size == 0:
            raise HTTPException(400, "빈 파일입니다.")

        pr = security.probe(src, ext)

        if pr.encrypted and not password:
            # 비밀번호 대기: 업로드 파일을 보관하고 재업로드 없이 비밀번호만 받는다
            job.src_path = src
            job.src_fmt = pr.fmt
            job.target = target
            job.original_filename = file.filename or ""
            job.encrypted = True
            return JSONResponse({
                "ok": False,
                "need_password": True,
                "token": job.token,
                "filename": file.filename or "",
            })

        async with convert_semaphore:
            if pr.encrypted:
                src, fmt = await asyncio.to_thread(_decrypt_job, job, src, pr, password)
            else:
                fmt = pr.fmt
            _validate_target(fmt, target, pr.encrypted)
            result = await asyncio.to_thread(_do_convert, src, fmt, target, job.dir)
        return _finish(job, result, file.filename or "", _final_ext(target, fmt))

    except HTTPException:
        job_store.delete(job.token)
        raise
    except decrypt.WrongPassword:
        job_store.delete(job.token)
        raise HTTPException(400, "비밀번호가 올바르지 않습니다.")
    except (decrypt.DecryptError, security.ValidationError, engine.ConversionError) as e:
        job_store.delete(job.token)
        code = 422 if isinstance(e, engine.ConversionError) else 400
        raise HTTPException(code, str(e))
    except Exception:
        logger.exception("conversion failed")
        job_store.delete(job.token)
        raise HTTPException(500, "변환 중 오류가 발생했습니다.")


@app.post("/api/password")
async def api_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    target: str = Form(""),
):
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client_ip):
        raise HTTPException(429, "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.")

    job = job_store.get(token)
    if not job or not job.encrypted or not job.src_path or not job.src_path.exists():
        raise HTTPException(404, "대기 중인 파일이 없습니다. 파일을 다시 올려주세요.")

    target = (target.lower().strip() or job.target)
    if target not in config.OUTPUT_FORMATS:
        raise HTTPException(400, "지원하지 않는 변환 형식입니다.")

    job.attempts += 1
    if job.attempts > config.MAX_PASSWORD_ATTEMPTS:
        job_store.delete(token)
        raise HTTPException(429, "비밀번호 시도 횟수를 초과했습니다. 파일을 다시 올려주세요.")

    pr = security.Probe(job.src_fmt, encrypted=True)
    try:
        async with convert_semaphore:
            dec, fmt = await asyncio.to_thread(_decrypt_job, job, job.src_path, pr, password)
            _validate_target(fmt, target, True)
            result = await asyncio.to_thread(_do_convert, dec, fmt, target, job.dir)
        return _finish(job, result, job.original_filename, _final_ext(target, fmt))

    except decrypt.WrongPassword:
        left = max(0, config.MAX_PASSWORD_ATTEMPTS - job.attempts)
        if left == 0:
            job_store.delete(token)
            raise HTTPException(429, "비밀번호 시도 횟수를 초과했습니다. 파일을 다시 올려주세요.")
        return JSONResponse({
            "ok": False,
            "need_password": True,
            "token": token,
            "error": "비밀번호가 올바르지 않습니다.",
            "attempts_left": left,
        })
    except HTTPException:
        raise
    except (decrypt.DecryptError, security.ValidationError, engine.ConversionError) as e:
        job_store.delete(token)
        code = 422 if isinstance(e, engine.ConversionError) else 400
        raise HTTPException(code, str(e))
    except Exception:
        logger.exception("password conversion failed")
        job_store.delete(token)
        raise HTTPException(500, "변환 중 오류가 발생했습니다.")


@app.get("/api/download/{token}")
async def api_download(token: str):
    job = job_store.get(token)
    if not job or not job.result_path or not job.result_path.exists():
        raise HTTPException(404, "파일이 존재하지 않거나 이미 삭제되었습니다.")
    # 1회 다운로드: 응답 전송이 끝나면 작업 폴더 전체를 즉시 삭제
    return FileResponse(
        job.result_path,
        filename=job.download_name,
        media_type="application/octet-stream",
        background=BackgroundTask(job_store.delete, token),
        headers={"Cache-Control": "no-store"},
    )


# ── PWA(설치형 앱) 파일: 올바른 MIME 타입과 서비스워커 스코프로 직접 서빙 ──
@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(config.STATIC_DIR / "manifest.webmanifest",
                        media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(config.STATIC_DIR / "sw.js", media_type="text/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=str(config.STATIC_DIR), html=True), name="static")
