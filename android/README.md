# 문서 변환기 — 안드로이드 앱 (APK)

웹 변환 서비스를 전체 화면으로 감싼 가벼운 네이티브 **WebView 앱**입니다.
문서 변환은 (LibreOffice·PyMuPDF 등이 필요하므로) 서버에서 수행되고, 앱은
파일 업로드·결과 다운로드·뒤로가기·당겨서 새로고침·오프라인 안내를 네이티브로
매끄럽게 연결합니다.

> 먼저 변환 서버를 배포해 주소(예: `https://내서비스.onrender.com`)를 준비하세요.
> 저장소 루트의 README 참고 (Render 원클릭 배포 지원).

## 가장 쉬운 방법 — GitHub Actions 로 APK 받기 (설치 불필요)

1. 이 저장소를 본인 GitHub 계정으로 올립니다.
2. **Actions** 탭 → **Build Android APK** → **Run workflow**.
3. `converterUrl` 에 배포한 서버 주소를 입력하고 실행합니다.
4. 빌드가 끝나면 실행 결과의 **Artifacts** 에서 `document-converter-apk` 를
   내려받아 압축을 풀면 `app-debug.apk` 가 나옵니다.
5. 안드로이드 휴대폰으로 옮긴 뒤 설치합니다. (설정에서 "출처를 알 수 없는 앱 설치" 허용)

## 직접 빌드 (로컬)

필요: JDK 17, Android SDK (Android Studio 설치 시 함께 설치됨).

```bash
cd android
./gradlew assembleDebug -PconverterUrl="https://내서비스.onrender.com"
# 결과: app/build/outputs/apk/debug/app-debug.apk
```

Android Studio 에서 열어 **Run** 해도 됩니다. 서버 주소는 `app/build.gradle.kts`
의 `converterUrl` 기본값을 바꾸거나 위처럼 `-PconverterUrl` 로 지정합니다.

### 에뮬레이터·같은 PC 서버로 테스트

에뮬레이터에서 PC 의 로컬 서버(`http://127.0.0.1:8000`)에 붙으려면
`-PconverterUrl="http://10.0.2.2:8000"` 로 빌드하세요. (10.0.2.2 는 에뮬레이터가
보는 호스트 PC 주소이며, 개발용 cleartext 는 `network_security_config.xml` 에서
이 주소에 한해 허용되어 있습니다.)

## 배포용 서명 APK

스토어 배포나 안정적 설치를 원하면 서명 키로 release 빌드를 만듭니다.

```bash
keytool -genkey -v -keystore convert.keystore -alias convert -keyalg RSA -keysize 2048 -validity 10000
cd android
./gradlew assembleRelease -PconverterUrl="https://내서비스.onrender.com"
# 생성된 app-release-unsigned.apk 를 apksigner 로 서명
```

## 구조

- `app/src/main/java/com/convert/app/MainActivity.kt` — WebView 셸(업로드/다운로드/뒤로가기/새로고침/오프라인)
- `app/src/main/assets/offline.html` — 오프라인 안내 화면
- 서버 주소는 `BuildConfig.CONVERTER_URL` (빌드 시 `-PconverterUrl` 로 주입)
