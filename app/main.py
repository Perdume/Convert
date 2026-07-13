"""HWP·PPT·PDF 변환 웹서비스.

보안 설계:
  - 파일은 무작위 이름의 격리 폴더에만 저장, 원본은 변환 직후 즉시 삭제
  - 결과물은 1회 다운로드 후 즉시 삭제, 미다운로드 시 10분 뒤 자동 삭제
  - 삭제는 0으로 덮어쓴 뒤 수행 (복구 방지 최선 노력)
  - 매직 바이트로 실제 파일 형식 검증 (확장자 위조 차단)
  - 다운로드는 추측 불가능한 1회용 토큰으로만 가능
  - IP당 레이트리밋, 용량 제한, 변환 타임아웃, 동시 실행 제한
  - 외부 API로 파일을 전송하지 않음 (전 과정 서버 내부 처리)
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import config, security, storage
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


@app.post("/api/convert")
async def api_convert(
    request: Request,
    file: UploadFile = File(...),
    target: str = Form(...),
):
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client_ip):
        raise HTTPException(429, "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.")

    target = target.lower().strip()
    if target not in config.OUTPUT_FORMATS:
        raise HTTPException(400, "지원하지 않는 변환 형식입니다.")

    ext = Path(file.filename or "").suffix.lower().lstrip(".")
    if ext not in config.INPUT_FORMATS:
        raise HTTPException(400, "지원 형식: HWP, PPT/PPTX, PDF")

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

        actual_fmt = security.sniff_format(src)
        if actual_fmt != ext:
            raise HTTPException(400, "파일 내용이 확장자와 일치하지 않습니다.")

        async with convert_semaphore:
            result = await asyncio.to_thread(engine.convert, src, actual_fmt, target, job.dir)

        # 원본 업로드 파일과 중간 산출물은 변환이 끝나는 즉시 삭제 (결과물만 남김)
        await asyncio.to_thread(storage.cleanup_except, job.dir, result)

        job.result_path = result
        job.download_name = security.safe_download_name(file.filename, target)
        return {"token": job.token, "filename": job.download_name}

    except HTTPException:
        job_store.delete(job.token)
        raise
    except security.ValidationError as e:
        job_store.delete(job.token)
        raise HTTPException(400, str(e))
    except engine.ConversionError as e:
        job_store.delete(job.token)
        raise HTTPException(422, str(e))
    except Exception:
        logger.exception("conversion failed")
        job_store.delete(job.token)
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


app.mount("/", StaticFiles(directory=str(config.STATIC_DIR), html=True), name="static")
