package com.swasthya.sahayak

import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import android.webkit.WebChromeClient
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * Supervisor / Doctor Dashboard — loads the backend HTML dashboard in a WebView.
 * Shows triage stats, photo review queue, and outbreak radar.
 */
class DashboardActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val dp = resources.displayMetrics.density

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#F0F4FF"))
        }

        // Header bar
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            val headerGradient = GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                intArrayOf(Color.parseColor("#0A3672"), Color.parseColor("#0D47A1"), Color.parseColor("#1565C0"))
            )
            background = headerGradient
            val padH = (20 * dp).toInt()
            setPadding(padH, (40 * dp).toInt(), padH, (18 * dp).toInt())
        }
        header.addView(TextView(this).apply {
            text = "←"
            textSize = 22f
            setTextColor(Color.WHITE)
            setPadding(0, 0, (16 * dp).toInt(), 0)
            setOnClickListener { finish() }
        })
        header.addView(TextView(this).apply {
            text = "🩺  Supervisor Dashboard"
            textSize = 20f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.WHITE)
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        })
        root.addView(header)

        // Progress bar for loading
        val progressBar = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                (3 * dp).toInt()
            )
            isIndeterminate = false
            max = 100
            progressDrawable.setColorFilter(
                Color.parseColor("#5E35B1"), android.graphics.PorterDuff.Mode.SRC_IN
            )
        }
        root.addView(progressBar)

        val webView = WebView(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f
            )
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.loadWithOverviewMode = true
            settings.useWideViewPort = true
            webViewClient = WebViewClient()
            webChromeClient = object : WebChromeClient() {
                override fun onProgressChanged(view: WebView?, newProgress: Int) {
                    progressBar.progress = newProgress
                    progressBar.visibility = if (newProgress < 100) View.VISIBLE else View.GONE
                }
            }
        }
        root.addView(webView)
        setContentView(root)

        val url = BuildConfig.BACKEND_URL
        webView.loadUrl(url)
    }
}
