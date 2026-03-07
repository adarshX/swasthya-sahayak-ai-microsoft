package com.swasthya.sahayak

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
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

    private lateinit var tvResult: TextView
    private lateinit var btnVoice: Button
    private lateinit var cbAgeUnder5: CheckBox
    private lateinit var cbFever: CheckBox
    private lateinit var cbFastBreathing: CheckBox
    private lateinit var btnEvaluate: Button

    private val speechLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            val text = result.data
                ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                ?.firstOrNull() ?: return@registerForActivityResult
            parseVoiceInput(text)
        }
    }

    private val micPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startVoiceInput()
        else Toast.makeText(this, "Microphone permission required", Toast.LENGTH_SHORT).show()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        tvResult = findViewById(R.id.tvResult)
        btnVoice = findViewById(R.id.btnVoice)
        cbAgeUnder5 = findViewById(R.id.cbAgeUnder5)
        cbFever = findViewById(R.id.cbFever)
        cbFastBreathing = findViewById(R.id.cbFastBreathing)
        btnEvaluate = findViewById(R.id.btnEvaluate)

        btnVoice.setOnClickListener {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED
            ) startVoiceInput()
            else micPermission.launch(Manifest.permission.RECORD_AUDIO)
        }

        btnEvaluate.setOnClickListener { runTriage() }
    }

    private fun startVoiceInput() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault())
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Describe the patient's symptoms")
        }
        speechLauncher.launch(intent)
    }

    /**
     * Very simple keyword parser for demo.
     * Production: replace with Azure AI Speech + NLP.
     */
    private fun parseVoiceInput(text: String) {
        val lower = text.lowercase()
        if ("child" in lower || "baby" in lower || "infant" in lower) cbAgeUnder5.isChecked = true
        if ("fever" in lower || "hot" in lower || "temperature" in lower) cbFever.isChecked = true
        if ("breathing" in lower || "breath" in lower || "fast breath" in lower) cbFastBreathing.isChecked = true
        Toast.makeText(this, "Parsed: $text", Toast.LENGTH_SHORT).show()
    }

    private fun runTriage() {
        val symptoms = mapOf(
            "age_under_5" to cbAgeUnder5.isChecked,
            "fever" to cbFever.isChecked,
            "fast_breathing" to cbFastBreathing.isChecked,
        )

        val result = TriageEngine.evaluate(this, symptoms)
        tvResult.text = "Triage: ${result.triage}\n${result.description}"

        lifecycleScope.launch {
            val record = VisitRecord(
                patientId = UUID.randomUUID().toString(),
                symptomsJson = JSONObject(symptoms as Map<*, *>).toString(),
                triage = result.triage
            )
            VisitDatabase.get(this@MainActivity).visitDao().insert(record)
            scheduleSyncIfNeeded()
        }
    }

    private fun scheduleSyncIfNeeded() {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val syncRequest = OneTimeWorkRequestBuilder<SyncWorker>()
            .setConstraints(constraints)
            .build()
        WorkManager.getInstance(this).enqueue(syncRequest)
    }
}
