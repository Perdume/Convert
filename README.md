# 문서 변환기 (HWP · PPT · PDF)

한글(HWP), 파워포인트(PPT/PPTX), PDF를 서로 변환하는 웹서비스입니다.
**업로드 → 변환 → 다운로드** 후 파일은 서버에서 완전히 삭제됩니다.

## 지원 변환

| 입력 \ 출력 | PDF | PPTX | 한글(HWPX) |
|---|---|---|---|
| **HWP** | ✅ | ✅ | — |
| **PPT / PPTX** | ✅ | — | ✅ |
| **PDF** | — | ✅ | ✅ |

- HWP → PDF는 문서를 해석해 변환하므로 원본 서식과 일부 차이가 있을 수 있습니다.
- PDF/PPT → 다른 형식 변환은 **페이지를 고해상도 이미지로 배치**하는 방식이라
  화면 모양은 원본과 동일하지만 텍스트 편집은 제한됩니다.
- 한글 출력은 HWPX 형식(한글 2014 이상에서 열림)으로 저장됩니다.
- 모든 변환은 서버 내부에서만 처리되며 **외부 API로 파일을 전송하지 않습니다.**

## 보안 설계

1. **변환 후 파일 삭제**
   - 업로드 원본: 변환이 끝나는 즉시 삭제
   - 변환 결과물: 1회 다운로드 직후 즉시 삭제, 미다운로드 시 10분 뒤 자동 삭제
   - 삭제 시 파일을 0으로 덮어쓴 뒤 제거 (복구 방지 최선 노력)
   - 서버 재시작 시 잔여 파일 전체 정리
2. **업로드 검증**
   - 확장자가 아닌 **매직 바이트(파일 내용)** 로 실제 형식 검증 → 확장자 위조 차단
   - 용량 제한(50MB), 페이지 수 제한, 빈 파일 거부
   - 파일은 무작위 이름의 격리 폴더에 저장 — 원본 파일명은 디스크에 사용하지 않음
3. **접근 통제**
   - 다운로드는 추측 불가능한 1회용 토큰(43자 무작위)으로만 가능
   - IP당 분당 10회 레이트리밋, 동시 변환 2건 제한, 변환 타임아웃 180초
4. **웹 보안 헤더**
   - CSP, X-Frame-Options, nosniff, no-referrer, API 응답 no-store
   - API 문서(/docs) 비공개, 디렉터리 목록 노출 없음

## 실행 방법

### Render 원클릭 배포 (무료)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Perdume/Convert)

1. 위 버튼 클릭 → GitHub 계정으로 Render 로그인
2. 서비스 이름 확인 후 **Apply** → 빌드가 끝나면 `https://<이름>.onrender.com` 주소로 접속

> 무료 플랜은 15분간 요청이 없으면 잠들었다가 첫 접속 시 30초~1분 정도 걸려 깨어납니다.

### Windows (로컬)

사전 설치: [Python 3.12+](https://www.python.org/downloads/), [LibreOffice](https://www.libreoffice.org/download/)

```bat
run.bat
```

브라우저에서 http://127.0.0.1:8000 접속.

### Docker (서버 배포 권장)

```bash
docker build -t converter .
docker run -p 8000:8000 converter
```

> 실서비스로 공개할 때는 반드시 리버스 프록시(nginx, Caddy 등) 뒤에서
> **HTTPS**로 서비스하세요. 전송 구간 암호화까지 되어야 보안이 완성됩니다.

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SOFFICE_PATH` | 자동 탐지 | LibreOffice 실행 파일 경로 |
| `CONVERT_DATA_DIR` | `./data` | 임시 작업 폴더 (자동 정리됨) |

## 기술 구성

- **FastAPI + Uvicorn** — 웹 서버
- **LibreOffice (headless)** — PPT/ODT → PDF 변환
- **pyhwp** — HWP 5.0 문서 해석 (HWP → ODT)
- **PyMuPDF + python-pptx** — PDF → PPTX (페이지 이미지 배치)
- **python-hwpx** — HWPX 문서 생성 (한컴오피스 불필요)
