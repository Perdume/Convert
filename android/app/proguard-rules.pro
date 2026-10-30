# WebView + JS 브리지 보존 (현재 JS 인터페이스는 없지만 안전하게 유지)
-keepclassmembers class * { @android.webkit.JavascriptInterface <methods>; }
