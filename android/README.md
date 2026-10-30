# 문서 변환기 — 안드로이드 앱 (APK)

웹 변환 서비스를 전체 화면으로 감싼 가벼운 네이티브 **WebView 앱**입니다.
문서 변환은 (LibreOffice·PyMuPDF 등이 필요하므로) 서버에서 수행되고, 앱은
파일 업로드·결과 다운로드·뒤로가기·당겨서 새로고침을 네이티브로 연결합니다.

**서버 주소는 앱 안에서 직접 입력**합니다 — 최초 실행(또는 연결 실패) 시 주소 입력
화면이 뜨므로, 한 번 빌드한 APK 를 **어떤 배포 주소에서도** 그대로 쓸 수 있습니다.
(먼저 변환 서버를 배포해 주소(예: `https://내서비스.onrender.com`)를 준비하세요 —
저장소 루트 README 의 Render 원클릭 배포 참고.)

## GitHub Actions 로 APK 받기 (설치 불필요)

워크플로 파일이 [`android/ci/build-apk.yml`](ci/build-apk.yml) 에 들어 있습니다.
(보안상 자동화 도구가 `.github/workflows/` 에 직접 커밋할 수 없어 이 위치에 두었습니다.)

1. 이 파일을 저장소의 **`.github/workflows/android.yml`** 로 복사합니다.
   - 깃허브 웹에서 **Add file → Create new file** 로 경로 `.github/workflows/android.yml`
     를 만들고 내용을 붙여넣거나, 로컬에서 복사 후 push 하면 됩니다.
2. **Actions** 탭 → **Build Android APK** → **Run workflow** 실행.
   (선택) `converterUrl` 에 서버 주소를 넣으면 그 주소가 앱 기본값이 됩니다. 비워 둬도
   앱 첫 화면에서 주소를 입력할 수 있습니다.
3. 끝나면 **Artifacts** 의 `document-converter-apk` 를 받아 압축을 풀면 `app-debug.apk`.
4. 안드로이드 폰으로 옮겨 설치합니다. (설정에서 "출처를 알 수 없는 앱 설치" 허용)

## 직접 빌드 (로컬)

필요: JDK 17, Android SDK (Android Studio 설치 시 함께 설치됨).

```bash
cd android
./gradlew assembleDebug
# 결과: app/build/outputs/apk/debug/app-debug.apk
```

서버 기본 주소를 미리 넣고 싶으면 `-PconverterUrl` 로 지정합니다(없어도 앱에서 입력 가능):

```bash
./gradlew assembleDebug -PconverterUrl="https://내서비스.onrender.com"
```

### 에뮬레이터·같은 PC 서버로 테스트

에뮬레이터에서 PC 로컬 서버(`http://127.0.0.1:8000`)에 붙으려면 앱 주소 입력 화면에
`http://10.0.2.2:8000` 을 넣으세요. (10.0.2.2 는 에뮬레이터가 보는 호스트 PC 주소이며,
개발용 cleartext 는 `network_security_config.xml` 에서 이 주소에 한해 허용됩니다.)

## 배포용 서명 APK

스토어 배포나 안정적 설치를 원하면 서명 키로 release 빌드를 만듭니다.

```bash
keytool -genkey -v -keystore convert.keystore -alias convert -keyalg RSA -keysize 2048 -validity 10000
cd android
./gradlew assembleRelease
# 생성된 app-release-unsigned.apk 를 apksigner 로 서명
```

## 구조

- `app/src/main/java/com/convert/app/MainActivity.kt` — WebView 셸(주소 설정·업로드·다운로드·뒤로가기·새로고침)
- 서버 주소: 앱 내 저장(SharedPreferences), 기본값은 빌드 시 `BuildConfig.CONVERTER_URL`
- `ci/build-apk.yml` — APK 빌드용 GitHub Actions 워크플로(위 설명대로 `.github/workflows/` 로 복사)
