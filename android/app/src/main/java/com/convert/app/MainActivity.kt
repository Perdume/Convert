package com.convert.app

import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.webkit.CookieManager
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout

/**
 * 문서 변환기를 전체 화면 WebView 로 감싸는 얇은 네이티브 셸.
 *
 * 변환 자체는 (LibreOffice·PyMuPDF 등이 필요하므로) 서버에서 수행된다. 이 앱은
 * 파일 업로드, 결과 다운로드, 뒤로가기, 당겨서 새로고침을 네이티브로 연결하고,
 * 접속할 **서버 주소를 앱 안에서 직접 설정**하게 해(최초 실행/연결 실패 시) 한 번
 * 빌드한 APK 를 어떤 배포 주소에서도 쓸 수 있게 한다.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var swipe: SwipeRefreshLayout
    private lateinit var setup: LinearLayout
    private lateinit var urlInput: EditText
    private lateinit var setupMsg: TextView
    private var filePathCallback: ValueCallback<Array<Uri>>? = null
    private lateinit var fileChooser: ActivityResultLauncher<Intent>
    private var loadFailed = false

    private val prefs by lazy { getSharedPreferences("convert", MODE_PRIVATE) }
    private fun savedUrl(): String? = prefs.getString(KEY_URL, null)
    private fun currentUrl(): String = savedUrl() ?: BuildConfig.CONVERTER_URL

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        swipe = findViewById(R.id.swipe)
        webView = findViewById(R.id.webview)
        setup = findViewById(R.id.setup)
        urlInput = findViewById(R.id.urlInput)
        setupMsg = findViewById(R.id.setupMsg)

        fileChooser = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val cb = filePathCallback ?: return@registerForActivityResult
            cb.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data))
            filePathCallback = null
        }

        with(webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            allowFileAccess = false
            allowContentAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = "$userAgentString ConvertApp/1.0"
        }
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false)

        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                loadFailed = false
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                swipe.isRefreshing = false
                if (!loadFailed && url != null && !url.startsWith("about:")) showWeb()
            }

            override fun onReceivedError(view: WebView, req: WebResourceRequest, err: WebResourceError) {
                if (req.isForMainFrame) { loadFailed = true; showSetup(getString(R.string.setup_error)) }
            }

            override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean {
                val u = req.url
                if (u.scheme == "http" || u.scheme == "https") return false
                return try { startActivity(Intent(Intent.ACTION_VIEW, u)); true } catch (e: Exception) { true }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                view: WebView, cb: ValueCallback<Array<Uri>>, params: FileChooserParams
            ): Boolean {
                filePathCallback?.onReceiveValue(null)
                filePathCallback = cb
                return try {
                    fileChooser.launch(params.createIntent()); true
                } catch (e: Exception) {
                    filePathCallback = null
                    Toast.makeText(this@MainActivity, "파일 선택기를 열 수 없습니다.", Toast.LENGTH_SHORT).show()
                    false
                }
            }
        }

        webView.setDownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
            try {
                val fileName = URLUtil.guessFileName(url, contentDisposition, mimeType)
                val req = DownloadManager.Request(Uri.parse(url)).apply {
                    setMimeType(mimeType)
                    addRequestHeader("User-Agent", userAgent)
                    CookieManager.getInstance().getCookie(url)?.let { addRequestHeader("Cookie", it) }
                    setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                    setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName)
                    setTitle(fileName)
                }
                (getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager).enqueue(req)
                Toast.makeText(this, "다운로드를 시작합니다: $fileName", Toast.LENGTH_LONG).show()
            } catch (e: Exception) {
                Toast.makeText(this, "다운로드에 실패했습니다.", Toast.LENGTH_SHORT).show()
            }
        }

        swipe.setOnRefreshListener { webView.reload() }
        findViewById<Button>(R.id.connectBtn).setOnClickListener { connect() }
        urlInput.setOnEditorActionListener { _, _, _ -> connect(); true }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (setup.visibility == View.VISIBLE && savedUrl() != null) { showWeb() }
                else if (webView.canGoBack()) webView.goBack()
                else { isEnabled = false; onBackPressedDispatcher.onBackPressed() }
            }
        })

        if (savedInstanceState != null) {
            webView.restoreState(savedInstanceState); showWeb()
        } else if (savedUrl() == null) {
            showSetup(getString(R.string.setup_prompt))   // 최초 실행: 서버 주소 입력
        } else {
            showWeb(); webView.loadUrl(currentUrl())
        }
    }

    private fun showSetup(message: String) {
        setupMsg.text = message
        if (urlInput.text.isNullOrBlank()) urlInput.setText(currentUrl())
        setup.visibility = View.VISIBLE
        swipe.visibility = View.GONE
    }

    private fun showWeb() {
        setup.visibility = View.GONE
        swipe.visibility = View.VISIBLE
    }

    private fun connect() {
        var u = urlInput.text.toString().trim()
        if (u.isEmpty()) return
        if (!u.startsWith("http://", true) && !u.startsWith("https://", true)) u = "https://$u"
        u = u.trimEnd('/')
        prefs.edit().putString(KEY_URL, u).apply()
        (getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager)
            .hideSoftInputFromWindow(urlInput.windowToken, 0)
        showWeb()
        webView.loadUrl(u)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        webView.saveState(outState)
    }

    companion object { private const val KEY_URL = "server_url" }
}
