package com.swasthya.sahayak

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.View
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.work.*
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.Locale
import java.util.UUID

class MainActivity : AppCompatActivity() {

    private lateinit var btnVoice: Button
    private lateinit var cbAgeUnder5: CheckBox
    private lateinit var cbFever: CheckBox
    private lateinit var cbFastBreathing: CheckBox
    private lateinit var btnEvaluate: Button
    private lateinit var cardResult: LinearLayout
    private lateinit var tvTriageLevel: TextView
    private lateinit var tvResult: TextView
    private lateinit var btnNewPatient: Button

    // ── Voice input launcher ──────────────────────────────────────────────
    private val speechLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            val text = result.data
                ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                ?.firstOrNull() ?: return@registerForActivityResult
            parseVoiceInput(text)
            Toast.makeText(this, "Heard: $text", Toast.LENGTH_SHORT).show()
        }
    }

    private val micPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startVoiceInput()
        else Toast.makeText(this, "Microphone permission required", Toast.LENGTH_SHORT).show()
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        btnVoice        = findViewById(R.id.btnVoice)
        cbAgeUnder5     = findViewById(R.id.cbAgeUnder5)
        cbFever         = findViewById(R.id.cbFever)
        cbFastBreathing = findViewById(R.id.cbFastBreathing)
        btnEvaluate     = findViewById(R.id.btnEvaluate)
        cardResult      = findViewById(R.id.cardResult)
        tvTriageLevel   = findViewById(R.id.tvTriageLevel)
        tvResult        = findViewById(R.id.tvResult)
        btnNewPatient   = findViewById(R.id.btnNewPatient)

        btnVoice.setOnClickListener {
            if (!SpeechRecognizer.isRecognitionAvailable(this)) {
                Toast.makeText(
                    this,
                    "Voice recognition not available — please use checkboxes",
                    Toast.LENGTH_LONG
                ).show()
                return@setOnClickListener
            }
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED
            ) startVoiceInput()
            else micPermission.launch(Manifest.permission.RECORD_AUDIO)
        }

        btnEvaluate.setOnClickListener { runTriage() }
        btnNewPatient.setOnClickListener { resetForm() }
    }

    // ── Voice input ───────────────────────────────────────────────────────
    private fun startVoiceInput() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault())
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Describe the patient's symptoms")
        }
        try {
            speechLauncher.launch(intent)
        } catch (e: Exception) {
            Toast.makeText(this, "Voice recognition unavailable — use checkboxes below", Toast.LENGTH_LONG).show()
        }
    }

    /**
     * Keyword parser: maps spoken words to symptom checkboxes.
     * Supports common Hindi/English terms used by ASHA workers.
     */
    private fun parseVoiceInput(text: String) {
        val lower = text.lowercase()
        if ("child" in lower || "baby" in lower || "infant" in lower ||
            "bachcha" in lower || "shishu" in lower || "5 year" in lower
        ) cbAgeUnder5.isChecked = true

        if ("fever" in lower || "hot" in lower || "temperature" in lower ||
            "bukhar" in lower || "tapman" in lower
        ) cbFever.isChecked = true

        if ("breath" in lower || "breathing" in lower || "saans" in lower ||
            "laboured" in lower || "difficult" in lower
        ) cbFastBreathing.isChecked = true
    }

    // ── Triage evaluation ─────────────────────────────────────────────────
    private fun runTriage() {
        val symptoms = mapOf(
            "age_under_5"    to cbAgeUnder5.isChecked,
            "fever"          to cbFever.isChecked,
            "fast_breathing" to cbFastBreathing.isChecked,
        )

        val result = TriageEngine.evaluate(this, symptoms)
        showResult(result)

        lifecycleScope.launch {
            val record = VisitRecord(
                patientId    = UUID.randomUUID().toString(),
                symptomsJson = JSONObject(symptoms as Map<*, *>).toString(),
                triage       = result.triage,
            )
            VisitDatabase.get(this@MainActivity).visitDao().insert(record)
            scheduleSyncIfNeeded()
        }
    }

    private fun showResult(result: TriageEngine.TriageResult) {
        val (bgDrawable, emoji) = when (result.triage) {
            "Urgent Referral" -> Pair(R.drawable.bg_urgent,   "🚨  URGENT REFERRAL")
            "PHC Visit"       -> Pair(R.drawable.bg_phc,      "⚠️  PHC VISIT")
            else              -> Pair(R.drawable.bg_homecare,  "✅  HOME CARE")
        }

        cardResult.setBackgroundResource(bgDrawable)
        tvTriageLevel.text = emoji
        tvResult.text = result.description

        cardResult.visibility    = View.VISIBLE
        btnNewPatient.visibility = View.VISIBLE
        btnEvaluate.visibility   = View.GONE

        cardResult.post {
            (cardResult.parent as? android.view.View)?.let { parent ->
                val scrollView = parent.parent as? android.widget.ScrollView
                scrollView?.smoothScrollTo(0, cardResult.top)
            }
        }
    }

    private fun resetForm() {
        cbAgeUnder5.isChecked     = false
        cbFever.isChecked         = false
        cbFastBreathing.isChecked = false

        cardResult.visibility    = View.GONE
        btnNewPatient.visibility = View.GONE
        btnEvaluate.visibility   = View.VISIBLE
        tvTriageLevel.text       = ""
        tvResult.text            = ""
    }

    // ── Background sync ───────────────────────────────────────────────────
    private fun scheduleSyncIfNeeded() {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val syncRequest = OneTimeWorkRequestBuilder<SyncWorker>()
            .setConstraints(constraints)
            .build()
        WorkManager.getInstance(this)
            .enqueueUniqueWork("sync", ExistingWorkPolicy.KEEP, syncRequest)
    }
}
