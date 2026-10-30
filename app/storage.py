"""작업(Job) 저장소.

업로드·변환 파일은 무작위 이름의 격리 폴더에만 저장되며,
다운로드 직후 또는 TTL 초과 시 0으로 덮어쓴 뒤 삭제된다(복구 방지 최선 노력).
서버 재시작 시 이전 실행의 잔여 파일도 모두 제거한다.
"""
import os
import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config


def secure_delete_file(path: Path) -> None:
    """파일을 0으로 덮어쓴 뒤 삭제한다."""
    try:
        if path.is_file():
            size = path.stat().st_size
            with open(path, "r+b") as f:
                remaining = size
                zeros = b"\0" * (1024 * 1024)
                while remaining > 0:
                    n = min(remaining, len(zeros))
                    f.write(zeros[:n])
                    remaining -= n
                f.flush()
                os.fsync(f.fileno())
    except OSError:
        pass
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def secure_rmtree(root: Path) -> None:
    if not root.exists():
        return
    if root.is_file():
        secure_delete_file(root)
        return
    for p in sorted(root.rglob("*"), key=lambda p: -len(p.parts)):
        if p.is_file():
            secure_delete_file(p)
    shutil.rmtree(root, ignore_errors=True)


def cleanup_except(job_dir: Path, keep: Path) -> None:
    """작업 폴더에서 결과물(keep)을 제외한 모든 파일·폴더를 삭제한다."""
    for p in job_dir.iterdir():
        if p == keep:
            continue
        secure_rmtree(p)


@dataclass
class Job:
    token: str
    dir: Path
    created: float = field(default_factory=time.time)
    result_path: Path | None = None
    download_name: str = ""
    # 암호 문서가 비밀번호 입력을 기다리는 동안 보관하는 상태 (TTL 지나면 자동 삭제)
    src_path: Path | None = None
    src_fmt: str = ""
    target: str = ""
    original_filename: str = ""
    encrypted: bool = False
    attempts: int = 0


class JobStore:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
        for leftover in config.JOBS_DIR.iterdir():
            secure_rmtree(leftover)

    def create(self) -> Job:
        token = secrets.token_urlsafe(32)
        job_dir = config.JOBS_DIR / secrets.token_hex(16)
        job_dir.mkdir(parents=True)
        job = Job(token=token, dir=job_dir)
        with self._lock:
            self._jobs[token] = job
        return job

    def get(self, token: str) -> Job | None:
        with self._lock:
            return self._jobs.get(token)

    def delete(self, token: str) -> None:
        with self._lock:
            job = self._jobs.pop(token, None)
        if job:
            secure_rmtree(job.dir)

    def sweep(self) -> None:
        now = time.time()
        with self._lock:
            expired = [t for t, j in self._jobs.items()
                       if now - j.created > config.JOB_TTL_SECONDS]
        for token in expired:
            self.delete(token)

    def delete_all(self) -> None:
        with self._lock:
            tokens = list(self._jobs)
        for token in tokens:
            self.delete(token)
