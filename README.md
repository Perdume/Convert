# 문서 변환기 (HWP · PDF · 오피스 · 이미지)

한글(HWP), 워드/파워포인트/엑셀, PDF, 이미지를 서로 변환하는 웹앱입니다.
암호가 걸린 문서는 **비밀번호를 입력해 암호를 해제한 뒤** 변환할 수 있고,
**브라우저 앱(PWA) 설치**와 **안드로이드 앱(APK)** 으로도 쓸 수 있습니다.
**업로드 → (필요 시 암호 해제) → 변환 → 다운로드** 후 파일은 서버에서 완전히 삭제됩니다.

## 주요 기능

- **여러 형식 상호 변환** — 아래 표 참고. 오피스 문서는 **편집 가능한 형식**으로,
  PDF·이미지 기반은 **페이지 이미지**로 배치합니다.
- **암호 문서 해제** — 비밀번호가 걸린 PDF·오피스(docx/xlsx/pptx 등)를
  **내가 아는 비밀번호를 입력**해 암호를 해제한 뒤 변환하거나, 암호만 푼 원본을 받습니다.
  (비밀번호는 서버에 저장하지 않으며, 추측·우회 없이 입력값으로만 해제합니다.)
- **이미지/텍스트 추출** — 문서를 페이지별 PNG(ZIP)나 순수 텍스트(TXT)로 추출합니다.
- **설치형 앱** — 라이트/다크 테마, 모바일 최적화, 홈 화면에 **앱으로 설치(PWA)**,
  **안드로이드 APK** 빌드 지원.
- **안전한 처리** — 전 과정 서버 내부 처리, 1회용 토큰 다운로드, 변환·다운로드 후 즉시 삭제.

## 지원 변환

| 입력 | 변환할 수 있는 형식 |
|---|---|
| **HWP** | PDF · 워드(DOCX) · ODT · 이미지(PNG) · 텍스트(TXT) |
| **DOC / DOCX / ODT / RTF / TXT** | PDF · 워드(DOCX) · ODT · 한글(HWPX) · 이미지 · 텍스트 |
| **PPT / PPTX / ODP** | PDF · 파워포인트(PPTX) · 한글(HWPX) · 워드(DOCX) · 이미지 |
| **XLS / XLSX / ODS / CSV** | PDF · 엑셀(XLSX) · 이미지 |
| **PDF** | 워드(DOCX) · 파워포인트(PPTX) · 한글(HWPX) · 이미지 · 텍스트 |
| **이미지(JPG/PNG/… )** | PDF |
| **암호 걸린 PDF·오피스** | 위 변환 + **암호만 해제(원본 형식 그대로)** |

- **편집 가능한 변환**(오피스↔오피스, HWP→DOCX 등)은 문서를 해석해 변환하므로
  복잡한 서식은 일부 달라질 수 있습니다.
- **PDF·이미지 기반 변환**(→ PPTX/HWPX/DOCX)은 페이지를 고해상도 이미지로 배치해
  모양은 원본과 같지만 글자 편집은 제한됩니다.
- 한글 출력은 HWPX(한글 2014 이상)로 저장됩니다.
- 모든 변환은 서버 내부에서만 처리되며 **외부 API로 파일을 전송하지 않습니다.**

## 암호 해제에 대하여

이 기능은 **사용자가 비밀번호를 아는 자신의 문서**의 암호를 푸는, Adobe·qpdf 등과
같은 일반적인 기능입니다. 입력한 비밀번호로만 복호화하며(PDF는 pikepdf,
오피스는 msoffcrypto), 비밀번호를 **추측하거나 우회하지 않습니다.** 비밀번호는
메모리에서만 쓰이고 저장되지 않으며, 문서 1건당 시도 횟수를 제한합니다.

## 보안 설계

1. **변환 후 파일 삭제** — 업로드 원본은 변환 즉시, 결과물은 1회 다운로드 직후
   삭제(0으로 덮어쓴 뒤 제거). 미다운로드·미입력 시 10분 뒤 자동 삭제, 재시작 시 전체 정리.
2. **업로드 검증** — 확장자가 아닌 **매직 바이트(내용)** 로 실제 형식 검증, 용량·페이지 제한.
3. **암호 처리** — 비밀번호 비저장, 문서당 시도 횟수 제한, 암호 해제는 입력값으로만.
4. **접근 통제** — 추측 불가능한 1회용 토큰 다운로드, IP 레이트리밋, 동시 변환·타임아웃 제한.
5. **웹 보안 헤더** — 엄격한 CSP(인라인 스크립트/스타일 불가), nosniff, no-referrer, HSTS(HTTPS 시).

## 앱으로 쓰기

### 브라우저 앱 설치 (PWA — 설치 불필요, 가장 간단)

접속 후 브라우저 메뉴의 **"홈 화면에 추가 / 앱 설치"** 를 누르거나, 화면 하단의
**"앱으로 설치하기"** 버튼을 누르면 홈 화면 아이콘으로 설치됩니다. (안드로이드·iOS·PC 공통)

### 안드로이드 앱 (APK)

`android/` 폴더에 네이티브 WebView 앱이 들어 있습니다. GitHub Actions 로 클릭 몇 번에
APK 를 받거나 직접 빌드할 수 있습니다 — 자세한 방법은 [`android/README.md`](android/README.md).

## 실행 방법

### Render 원클릭 배포 (무료)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Perdume/Convert)

버튼 클릭 → GitHub 로그인 → **Apply** → 빌드 후 `https://<이름>.onrender.com` 접속.
> 무료 플랜은 15분간 요청이 없으면 잠들었다가 첫 접속 시 30초~1분 걸려 깨어납니다.

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
> 실서비스 공개 시 반드시 리버스 프록시(nginx·Caddy 등) 뒤에서 **HTTPS** 로 서비스하세요.

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SOFFICE_PATH` | 자동 탐지 | LibreOffice 실행 파일 경로 |
| `CONVERT_DATA_DIR` | `./data` | 임시 작업 폴더 (자동 정리됨) |
| `MAX_CONCURRENT_CONVERSIONS` | `2` | 동시 변환 수 (무료 플랜은 1 권장) |

## 기술 구성

- **FastAPI + Uvicorn** — 웹 서버 / REST API
- **LibreOffice (headless, writer·impress·calc)** — 오피스·한글 문서 변환
- **pyhwp** — HWP 5.0 해석 (HWP → ODT)
- **PyMuPDF + python-pptx/docx + python-hwpx** — PDF↔이미지 배치, 텍스트 추출
- **pikepdf / msoffcrypto-tool** — 비밀번호 기반 암호 해제 (PDF / MS 오피스)
- **PWA (manifest + service worker)** / **Android (Kotlin WebView)** — 설치형 앱
