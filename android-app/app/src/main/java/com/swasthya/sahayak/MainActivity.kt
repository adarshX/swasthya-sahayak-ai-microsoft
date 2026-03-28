package com.swasthya.sahayak

import android.Manifest
import android.animation.ObjectAnimator
import android.animation.AnimatorSet
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.view.MotionEvent
import android.view.View
import android.view.animation.AnimationUtils
import android.view.animation.DecelerateInterpolator
import android.view.animation.OvershootInterpolator
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import androidx.work.*
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.File
import java.util.Locale
import java.util.UUID
import okhttp3.MediaType.Companion.toMediaType

class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener {

    private var tts: TextToSpeech? = null
    private var ttsReady = false

    // ── Symptom category model ────────────────────────────────────────────
    data class SymptomItem(val key: String, val label: String)
    data class SymptomCategory(
        val title: String,
        val emoji: String,
        val color: Int,
        val symptoms: List<SymptomItem>
    )

    // Track all checkboxes by symptom key
    private val symptomCheckboxes = mutableMapOf<String, CheckBox>()
    private val categoryBodies = mutableListOf<LinearLayout>()

    // Patient section
    private lateinit var etPatientName: EditText
    private lateinit var btnSearchPatient: Button
    private lateinit var tvPatientBadge: TextView
    private lateinit var cardPatientSummary: LinearLayout
    private lateinit var tvPatientSummary: TextView
    private lateinit var tvLastVisit: TextView
    private lateinit var tvRiskLevel: TextView
    private lateinit var patientListContainer: LinearLayout
    private lateinit var patientListItems: LinearLayout

    // New patient details
    private lateinit var cardNewPatientDetails: LinearLayout
    private lateinit var etPatientAge: EditText
    private lateinit var spinnerGender: Spinner
    private lateinit var cbNewPatientPregnant: CheckBox
    private lateinit var etPatientVillage: EditText
    private lateinit var btnSaveNewPatient: Button

    // Core UI
    private lateinit var btnVoice: Button
    private lateinit var btnEvaluate: Button
    private lateinit var cardResult: LinearLayout
    private lateinit var resultHeader: LinearLayout
    private lateinit var tvTriageLevel: TextView
    private lateinit var tvResult: TextView
    private lateinit var btnNewPatient: Button
    private lateinit var tvVoiceStatus: TextView
    private lateinit var tvPatientId: TextView
    private lateinit var tvSyncStatus: TextView
    private lateinit var confidenceBar: ProgressBar
    private lateinit var tvConfidence: TextView
    private lateinit var tvUncertain: TextView
    private lateinit var symptomCategoriesContainer: LinearLayout
    private lateinit var cardExtraSymptoms: LinearLayout
    private lateinit var tvExtraSymptoms: TextView

    private var currentPatientId: String = ""
    private var currentPatientName: String = ""
    private var voiceMode: String = "symptoms"
    private var lastTriageSpeechText: String = ""
    // Registration state machine: idle → name → age → gender → pregnant → village → done
    private var regStep: String = "idle"
    private var regLang: String = "en" // "hi", "kn", "te", "en"
    private var regName: String = ""
    private var regAge: String = ""
    private var regGender: String = ""
    private var regVillage: String = ""
    private var extraSymptoms: MutableList<String> = mutableListOf()

    // ── Multilingual prompts ──────────────────────────────────────────────
    private fun t(hi: String, kn: String, te: String, en: String): String = when (regLang) {
        "hi" -> hi; "kn" -> kn; "te" -> te; else -> en
    }

    // ── Symptom categories definition (multilingual) ──────────────────
    private fun getSymptomCategories(): List<SymptomCategory> = listOf(
        SymptomCategory(
            t("सामान्य", "ಸಾಮಾನ್ಯ", "సాధారణ", "General"), "🌡️", R.color.colorPrimary, listOf(
            SymptomItem("age_under_5", t("👶  5 साल से कम उम्र का बच्चा", "👶  5 ವರ್ಷಕ್ಕಿಂತ ಕಡಿಮೆ ಮಗು", "👶  5 సంవత్సరాల లోపు పిల్లవాడు", "👶  Child under 5 years")),
            SymptomItem("fever", t("🌡️  बुखार / तेज़ तापमान", "🌡️  ಜ್ವರ / ಹೆಚ್ಚಿನ ತಾಪಮಾನ", "🌡️  జ్వరం / అధిక ఉష్ణోగ్రత", "🌡️  Fever / high temperature")),
            SymptomItem("severe_headache", t("🤕  तेज़ सिरदर्द", "🤕  ತೀವ್ರ ತಲೆನೋವು", "🤕  తీవ్ర తలనొప్పి", "🤕  Severe headache")),
            SymptomItem("weakness", t("😰  कमज़ोरी / थकान", "😰  ದೌರ್ಬಲ್ಯ / ಆಯಾಸ", "😰  బలహీనత / అలసట", "😰  Weakness / fatigue")),
        )),
        SymptomCategory(
            t("सांस और छाती", "ಉಸಿರಾಟ ಮತ್ತು ಎದೆ", "శ్వాస మరియు ఛాతీ", "Breathing & Chest"), "💨", R.color.colorUrgent, listOf(
            SymptomItem("fast_breathing", t("💨  तेज़ या कठिन सांस", "💨  ವೇಗದ ಅಥವಾ ಕಷ್ಟಕರ ಉಸಿರಾಟ", "💨  వేగంగా లేదా కష్టంగా శ్వాస", "💨  Fast or difficult breathing")),
            SymptomItem("chest_indrawing", t("🫁  छाती धंसना", "🫁  ಎದೆ ಒಳಗೆ ಹೋಗುವುದು", "🫁  ఛాతీ లోపలికి లాగడం", "🫁  Chest indrawing")),
        )),
        SymptomCategory(
            t("पेट और पाचन", "ಹೊಟ್ಟೆ ಮತ್ತು ಜೀರ್ಣಕ್ರಿಯೆ", "కడుపు మరియు జీర్ణక్రియ", "Stomach & Digestion"), "💧", R.color.colorPHC, listOf(
            SymptomItem("diarrhea", t("💧  दस्त / पतला पॉटी", "💧  ಭೇದಿ / ಸಡಿಲ ಮಲ", "💧  విరేచనాలు / పలచని మలం", "💧  Diarrhea / loose stools")),
            SymptomItem("vomiting", t("🤢  उल्टी", "🤢  ವಾಂತಿ", "🤢  వాంతులు", "🤢  Vomiting")),
            SymptomItem("abdominal_pain", t("🤢  पेट दर्द / ऐंठन", "🤢  ಹೊಟ್ಟೆ ನೋವು / ಸೆಳೆತ", "🤢  కడుపు నొప్పి / నొక్కులు", "🤢  Abdominal pain / cramps")),
        )),
        SymptomCategory(
            t("खतरे के लक्षण", "ಅಪಾಯದ ಚಿಹ್ನೆಗಳು", "ప్రమాద సంకేతాలు", "Danger Signs"), "⚡", R.color.colorUrgent, listOf(
            SymptomItem("convulsions", t("⚡  दौरे / मिर्गी", "⚡  ಸೆಳವು / ಮೂರ್ಛೆ", "⚡  మూర్ఛలు / ఫిట్స్", "⚡  Convulsions / seizures")),
            SymptomItem("unable_to_feed", t("🍼  खाना-पीना नहीं कर पा रहा", "🍼  ಕುಡಿಯಲು ಅಥವಾ ತಿನ್ನಲು ಸಾಧ್ಯವಿಲ್ಲ", "🍼  తాగలేకపోతున్నాడు లేదా తినలేకపోతున్నాడు", "🍼  Unable to drink or feed")),
        )),
        SymptomCategory(
            t("महिला स्वास्थ्य", "ಮಹಿಳಾ ಆರೋಗ್ಯ", "మహిళా ఆరోగ్యం", "Women's Health"), "🤰", R.color.colorAccent, listOf(
            SymptomItem("pregnant", t("🤰  गर्भवती है", "🤰  ಗರ್ಭಿಣಿ", "🤰  గర్భవతి", "🤰  Patient is pregnant")),
            SymptomItem("vaginal_bleeding", t("🩸  योनि से खून बहना", "🩸  ಯೋನಿ ರಕ್ತಸ್ರಾವ", "🩸  యోని రక్తస్రావం", "🩸  Vaginal bleeding")),
            SymptomItem("abnormal_discharge", t("🩹  असामान्य सफ़ेद पानी", "🩹  ಅಸಾಮಾನ್ಯ ಯೋನಿ ಸ್ರಾವ", "🩹  అసాధారణ యోని స్రావం", "🩹  Abnormal vaginal discharge")),
            SymptomItem("painful_urination", t("🚽  पेशाब में जलन / दर्द", "🚽  ನೋವಿನ ಮೂತ್ರ ವಿಸರ್ಜನೆ", "🚽  మూత్ర విసర్జనలో నొప్పి", "🚽  Painful or frequent urination")),
        )),
        SymptomCategory(
            t("पोषण और रक्त", "ಪೋಷಣೆ ಮತ್ತು ರಕ್ತ", "పోషణ మరియు రక్తం", "Nutrition & Blood"), "🩺", R.color.colorHomeCare, listOf(
            SymptomItem("pallor", t("😶  पीलापन (त्वचा / आँखें पीली)", "😶  ಪೇಲವತೆ (ಚರ್ಮ / ಕಣ್ಣುಗಳು)", "😶  పాలిపోవడం (చర్మం / కళ్ళు)", "😶  Pallor (pale skin / eyes)")),
            SymptomItem("visible_wasting", t("🦴  दिखने में बहुत कमज़ोर / पतला", "🦴  ಗೋಚರ ಕ್ಷೀಣತೆ / ತೆಳ್ಳಗೆ", "🦴  కనిపించే క్షీణత / చాలా సన్నగా", "🦴  Visible wasting / very thin")),
            SymptomItem("bilateral_edema", t("🫧  दोनों पैरों में सूजन", "🫧  ಎರಡೂ ಪಾದಗಳಲ್ಲಿ ಊತ", "🫧  రెండు పాదాలలో వాపు", "🫧  Bilateral feet swelling")),
        )),
        SymptomCategory(
            t("त्वचा और सूजन", "ಚರ್ಮ ಮತ್ತು ಊತ", "చర్మం మరియు వాపు", "Skin & Swelling"), "🦵", R.color.colorPHC, listOf(
            SymptomItem("limb_swelling", t("🦵  हाथ-पैर में सूजन / हाथीपांव", "🦵  ಅಂಗ ಊತ / ಆನೆಕಾಲು", "🦵  కాళ్ళ వాపు / ఏనుగకాలు", "🦵  Limb swelling / elephantiasis")),
            SymptomItem("groin_swelling", t("🫁  जांघ/अंडकोष में सूजन", "🫁  ತೊಡೆ/ವೃಷಣ ಊತ", "🫁  తొడ/వృషణ వాపు", "🫁  Groin / scrotal swelling")),
        )),
    )

    // ── Voice launcher ────────────────────────────────────────────────────
    // ── TTS ─────────────────────────────────────────────────────────────
    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            ttsReady = true
            // Set Hindi as default with natural-sounding parameters
            val hindiLocale = Locale("hi", "IN")
            val result = tts?.setLanguage(hindiLocale)
            if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                // Fallback — try installing Hindi voice data
                tts?.language = Locale("hi")
            }
            // Slower pace + slightly lower pitch = more natural Hindi
            tts?.setSpeechRate(0.85f)
            tts?.setPitch(0.95f)

            // Try to pick female voice (ASHA workers are women, female voice feels more natural)
            try {
                val voices = tts?.voices
                val hindiVoice = voices?.filter {
                    it.locale.language == "hi" && !it.isNetworkConnectionRequired
                }?.minByOrNull { it.quality }
                if (hindiVoice != null) tts?.voice = hindiVoice
            } catch (_: Exception) { }
        }
    }

    private fun speakHindi(text: String) {
        if (!ttsReady) return
        // Clear any pending listener that would auto-open voice input
        tts?.setOnUtteranceProgressListener(null)
        val clean = text.replace(Regex("[✓✗🎙🌡️💨⚡🤰🩸🤕🦵🩹🚽🤢😶😰🦴🫧👶🍼🫁💧📡▶●⚠️🔍👤📸🔒🩺]"), "")
            .replace(Regex("\\n+"), ". ")
            .replace(Regex("\\s+"), " ").trim()
        val locale = when (regLang) {
            "hi" -> Locale("hi", "IN"); "kn" -> Locale("kn", "IN"); "te" -> Locale("te", "IN"); else -> Locale.ENGLISH
        }
        tts?.language = locale
        tts?.speak(clean, TextToSpeech.QUEUE_FLUSH, null, "speak_${System.currentTimeMillis()}")
    }

    private fun speak(text: String, thenListen: Boolean = false) {
        tvVoiceStatus.text = text
        tvVoiceStatus.setTextColor(getColor(R.color.colorPrimary))

        // Clean text for TTS (remove emoji/symbols)
        val clean = text.replace(Regex("[✓✗🎙🌡️💨⚡🤰🩸🤕🦵🩹🚽🤢😶😰🦴🫧👶🍼🫁💧📡▶●⚠️🔍👤]"), "")
            .replace("\n", ". ")

        val locale = when (regLang) {
            "hi" -> Locale("hi", "IN"); "kn" -> Locale("kn", "IN"); "te" -> Locale("te", "IN"); else -> Locale.ENGLISH
        }

        if (ttsReady) {
            tts?.language = locale
            tts?.setSpeechRate(0.85f)
            tts?.setPitch(0.95f)
            if (thenListen) {
                tts?.setOnUtteranceProgressListener(object : android.speech.tts.UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) {}
                    override fun onDone(utteranceId: String?) {
                        runOnUiThread { startVoiceInput() }
                    }
                    @Deprecated("Deprecated") override fun onError(utteranceId: String?) {}
                })
                tts?.speak(clean, TextToSpeech.QUEUE_FLUSH, null, "reg_prompt")
            } else {
                // Clear any lingering listener so TTS doesn't auto-open voice input
                tts?.setOnUtteranceProgressListener(null)
                tts?.speak(clean, TextToSpeech.QUEUE_FLUSH, null, "info")
            }
        } else if (thenListen) {
            // TTS not ready, just open mic after a short delay
            tvVoiceStatus.postDelayed({ startVoiceInput() }, 800)
        }
    }

    override fun onDestroy() {
        tts?.stop()
        tts?.shutdown()
        super.onDestroy()
    }

    private val speechLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            resetVoiceButton()
            val text = result.data
                ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                ?.firstOrNull() ?: return@registerForActivityResult
            Toast.makeText(this, "Heard: $text", Toast.LENGTH_SHORT).show()

            // If ASHABot question voice is pending, fill it
            if (pendingQuestionField != null) {
                pendingQuestionField?.setText(text)
                pendingQuestionField = null
                return@registerForActivityResult
            }

            // If follow-up voice mode, route to follow-up handler
            if (voiceMode == "followup") {
                handleFollowUpVoiceAnswer(text)
                return@registerForActivityResult
            }

            when (regStep) {
                "name"     -> onRegName(text)
                "age"      -> onRegAge(text)
                "gender"   -> onRegGender(text)
                "pregnant" -> onRegPregnant(text)
                "village"  -> onRegVillage(text)
                else       -> handleVoiceCommand(text)
            }
        } else {
            resetVoiceButton()
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

        etPatientName    = findViewById(R.id.etPatientName)
        btnSearchPatient = findViewById(R.id.btnSearchPatient)
        tvPatientBadge   = findViewById(R.id.tvPatientBadge)
        cardPatientSummary = findViewById(R.id.cardPatientSummary)
        tvPatientSummary = findViewById(R.id.tvPatientSummary)
        tvLastVisit      = findViewById(R.id.tvLastVisit)
        tvRiskLevel      = findViewById(R.id.tvRiskLevel)
        patientListContainer = findViewById(R.id.patientListContainer)
        patientListItems = findViewById(R.id.patientListItems)

        cardNewPatientDetails = findViewById(R.id.cardNewPatientDetails)
        etPatientAge     = findViewById(R.id.etPatientAge)
        etPatientVillage = findViewById(R.id.etPatientVillage)
        spinnerGender    = findViewById(R.id.spinnerGender)
        cbNewPatientPregnant = findViewById(R.id.cbNewPatientPregnant)
        btnSaveNewPatient = findViewById(R.id.btnSaveNewPatient)

        btnVoice        = findViewById(R.id.btnVoice)
        btnEvaluate     = findViewById(R.id.btnEvaluate)
        cardResult      = findViewById(R.id.cardResult)
        resultHeader    = findViewById(R.id.resultHeader)
        tvTriageLevel   = findViewById(R.id.tvTriageLevel)
        tvResult        = findViewById(R.id.tvResult)
        btnNewPatient   = findViewById(R.id.btnNewPatient)
        tvVoiceStatus   = findViewById(R.id.tvVoiceStatus)
        tvPatientId     = findViewById(R.id.tvPatientId)
        tvSyncStatus    = findViewById(R.id.tvSyncStatus)
        confidenceBar   = findViewById(R.id.confidenceBar)
        tvConfidence    = findViewById(R.id.tvConfidence)
        tvUncertain     = findViewById(R.id.tvUncertain)
        symptomCategoriesContainer = findViewById(R.id.symptomCategoriesContainer)
        cardExtraSymptoms = findViewById(R.id.cardExtraSymptoms)
        tvExtraSymptoms   = findViewById(R.id.tvExtraSymptoms)

        // Gender spinner
        val genders = arrayOf("Select gender", "Male", "Female", "Other")
        spinnerGender.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, genders)

        // Init TTS
        tts = TextToSpeech(this, this)

        // Language spinner for symptoms
        val spinnerLang: Spinner = findViewById(R.id.spinnerLanguage)
        val languages = arrayOf("English", "हिंदी (Hindi)", "ಕನ್ನಡ (Kannada)", "తెలుగు (Telugu)")
        spinnerLang.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, languages)
        spinnerLang.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, pos: Int, id: Long) {
                val newLang = when (pos) { 1 -> "hi"; 2 -> "kn"; 3 -> "te"; else -> "en" }
                if (newLang != regLang) {
                    regLang = newLang
                    buildSymptomCategories()
                    updateStaticUI()
                }
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }

        newPatient()
        buildSymptomCategories()
        updateStaticUI()

        lifecycleScope.launch {
            SeedData.seedIfNeeded(this@MainActivity)
            showPatientList()
        }

        btnSearchPatient.setOnClickListener { searchPatient() }
        etPatientName.setOnEditorActionListener { _, _, _ -> searchPatient(); true }
        btnSaveNewPatient.setOnClickListener { saveNewPatientDetails() }

        // Cancel new patient — go back to patient list
        findViewById<Button>(R.id.btnCancelNewPatient).setOnClickListener {
            cardNewPatientDetails.visibility = View.GONE
            etPatientName.text.clear()
            etPatientAge.text.clear()
            etPatientVillage.text.clear()
            spinnerGender.setSelection(0)
            cbNewPatientPregnant.isChecked = false
            tvPatientBadge.text = "NEW"
            showPatientList()
            newPatient()
        }

        // Back to patient list button
        val btnBackToList: Button = findViewById(R.id.btnBackToList)
        btnBackToList.setOnClickListener {
            currentPatientId = ""
            currentPatientName = ""
            etPatientName.text.clear()
            tvPatientId.text = "— select patient —"
            tvPatientBadge.text = "NEW"
            btnBackToList.visibility = View.GONE
            cardPatientSummary.visibility = View.GONE
            cardNewPatientDetails.visibility = View.GONE
            for ((_, cb) in symptomCheckboxes) cb.isChecked = false
            showPatientList()
            newPatient()
        }

        // Listen to triage result
        val btnListen: Button = findViewById(R.id.btnListenResult)
        btnListen.setOnClickListener {
            val text = lastTriageSpeechText
            if (text.isNotEmpty()) speakHindi(text)
        }

        btnVoice.setOnClickListener {
            if (!SpeechRecognizer.isRecognitionAvailable(this)) {
                Toast.makeText(this, "Voice not available — use checkboxes", Toast.LENGTH_LONG).show()
                return@setOnClickListener
            }
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED
            ) startVoiceInput()
            else micPermission.launch(Manifest.permission.RECORD_AUDIO)
        }

        btnEvaluate.setOnClickListener { runTriage() }
        btnNewPatient.setOnClickListener { resetForm() }

        // Stigma-safe private mode
        val btnStigmaSafe: Button = findViewById(R.id.btnStigmaSafe)
        btnStigmaSafe.setOnClickListener { enterStigmaSafeMode() }

        // Photo for doctor review
        val btnTakePhoto: Button = findViewById(R.id.btnTakePhoto)
        btnTakePhoto.setOnClickListener { capturePhoto() }

        // ASHABot Q&A button
        val btnAskQuestion: Button = findViewById(R.id.btnAskQuestion)
        btnAskQuestion.setOnClickListener { openAshaBot() }

        // Doctor Dashboard button
        val btnDashboard: Button = findViewById(R.id.btnDoctorDashboard)
        btnDashboard.setOnClickListener {
            startActivity(Intent(this, DashboardActivity::class.java))
            overridePendingTransition(R.anim.slide_up_fade, R.anim.fade_in)
        }

        // Vaccination Tracker button
        val btnVaccination: Button = findViewById(R.id.btnVaccination)
        btnVaccination.setOnClickListener {
            val ageMonths = if (currentPatientId.isNotEmpty()) {
                lifecycleScope.launch {
                    val patient = VisitDatabase.get(this@MainActivity).patientDao().getById(currentPatientId)
                    val months = if (patient?.dobMillis != null) {
                        ((System.currentTimeMillis() - patient.dobMillis) / (30L * 24 * 60 * 60 * 1000)).toInt()
                    } else 0
                    val intent = Intent(this@MainActivity, VaccinationActivity::class.java).apply {
                        putExtra("patient_id", currentPatientId)
                        putExtra("patient_name", currentPatientName.ifEmpty { patient?.name ?: "Patient" })
                        putExtra("age_months", months)
                        putExtra("lang", regLang)
                    }
                    startActivity(intent)
                    overridePendingTransition(R.anim.slide_up_fade, R.anim.fade_in)
                }
            } else {
                Toast.makeText(this, "Select a patient first", Toast.LENGTH_SHORT).show()
            }
        }

        // ── Button press animations ──
        addPressAnimation(btnVoice)
        addPressAnimation(btnEvaluate)
        addPressAnimation(btnDashboard)
        addPressAnimation(btnVaccination)
        addPressAnimation(btnStigmaSafe)
        addPressAnimation(btnListen)
        addPressAnimation(btnSearchPatient)

        // ── Entrance stagger animation ──
        btnVoice.post { runEntranceAnimations() }
    }

    // ── Photo Capture ─────────────────────────────────────────────────────
    private var photoUri: Uri? = null

    private val cameraLauncher = registerForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { success ->
        if (success && photoUri != null) {
            extraSymptoms.add("📸 Photo captured for doctor review")
            showExtraSymptoms()
            Toast.makeText(this, "Photo saved. Doctor will review soon.", Toast.LENGTH_LONG).show()
        }
    }

    private fun capturePhoto() {
        // Request camera permission at runtime
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED) {
            cameraPermission.launch(Manifest.permission.CAMERA)
            return
        }
        launchCamera()
    }

    private val cameraPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) launchCamera()
        else Toast.makeText(this, "Camera permission required for photos", Toast.LENGTH_SHORT).show()
    }

    private fun launchCamera() {
        try {
            val photoDir = File(filesDir, "visit_photos")
            photoDir.mkdirs()
            val photoFile = File(photoDir, "${currentPatientId}_${System.currentTimeMillis()}.jpg")
            photoUri = FileProvider.getUriForFile(this, "$packageName.fileprovider", photoFile)
            cameraLauncher.launch(photoUri!!)
        } catch (e: Exception) {
            Toast.makeText(this, "Camera error: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    // ── ASHABot Q&A ─────────────────────────────────────────────────────
    private fun openAshaBot() {
        val builder = android.app.AlertDialog.Builder(this)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (20 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad, pad, pad)
        }

        layout.addView(TextView(this).apply {
            text = "💬 ASHABot — Ask a Health Question"
            textSize = 18f
            setTypeface(null, Typeface.BOLD)
            setTextColor(getColor(R.color.colorPrimary))
            setPadding(0, 0, 0, (16 * resources.displayMetrics.density).toInt())
        })

        layout.addView(TextView(this).apply {
            text = "Type or speak a question about health protocols, medications, or patient care in any language."
            textSize = 13f
            setTextColor(getColor(R.color.colorTextSecondary))
            setPadding(0, 0, 0, (12 * resources.displayMetrics.density).toInt())
        })

        val etQuestion = EditText(this).apply {
            hint = "e.g. Pregnancy mein BP badhne par kya karein?"
            textSize = 15f
            minLines = 2
            setTextColor(getColor(R.color.colorTextPrimary))
            setBackgroundResource(R.drawable.bg_voice_hint)
            val pad = (12 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad, pad, pad)
        }
        layout.addView(etQuestion)

        val tvAnswer = TextView(this).apply {
            text = ""
            textSize = 14f
            setTextColor(getColor(R.color.colorTextPrimary))
            setPadding(0, (16 * resources.displayMetrics.density).toInt(), 0, 0)
            visibility = View.GONE
        }
        layout.addView(tvAnswer)

        val dialog = builder.setView(layout)
            .setPositiveButton("🎙 Voice") { _, _ -> }
            .setNeutralButton("📤 Ask") { _, _ -> }
            .setNegativeButton("Close", null)
            .create()

        dialog.show()

        // Override button click to prevent auto-dismiss
        dialog.getButton(android.app.AlertDialog.BUTTON_NEUTRAL)?.setOnClickListener {
            val question = etQuestion.text.toString().trim()
            if (question.isEmpty()) {
                Toast.makeText(this, "Type a question first", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            tvAnswer.text = "⏳ Asking..."
            tvAnswer.visibility = View.VISIBLE

            lifecycleScope.launch {
                try {
                    val url = "${BuildConfig.BACKEND_URL}/ask-knowledge"
                    val body = JSONObject().apply {
                        put("question", question)
                        put("language", regLang)
                        put("patient_context", "Patient: $currentPatientName")
                    }.toString()

                    val client = okhttp3.OkHttpClient()
                    val request = okhttp3.Request.Builder()
                        .url(url)
                        .post(body.toByteArray().let {
                            okhttp3.RequestBody.create(
                                "application/json".toMediaType(), it)
                        })
                        .build()

                    kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                        val response = client.newCall(request).execute()
                        val resBody = response.body?.string() ?: "{}"
                        val json = JSONObject(resBody)
                        val answer = json.optString("answer", "No answer available")
                        runOnUiThread {
                            tvAnswer.text = answer
                            tvAnswer.visibility = View.VISIBLE
                            // Speak the answer aloud in natural Hindi
                            speakHindi(answer)
                        }
                        response.close()
                    }
                } catch (e: Exception) {
                    runOnUiThread {
                        tvAnswer.text = "⚠️ Could not reach server. Check if backend is running.\n${e.message}"
                        tvAnswer.visibility = View.VISIBLE
                    }
                }
            }
        }

        // Voice button
        dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE)?.setOnClickListener {
            voiceMode = "symptoms" // reuse voice, result goes to question field
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, when (regLang) { "hi" -> "hi-IN"; "kn" -> "kn-IN"; "te" -> "te-IN"; else -> "en-IN" })
                putExtra(RecognizerIntent.EXTRA_PROMPT, t("स्वास्थ्य सवाल पूछें", "ಆರೋಗ್ಯ ಪ್ರಶ್ನೆ ಕೇಳಿ", "ఆరోగ్య ప్రశ్న అడగండి", "Ask your health question"))
            }
            // Store reference to fill etQuestion after voice returns
            pendingQuestionField = etQuestion
            try { speechLauncher.launch(intent) }
            catch (_: Exception) { Toast.makeText(this, "Voice unavailable", Toast.LENGTH_SHORT).show() }
        }
    }

    private var pendingQuestionField: EditText? = null

    // ── Stigma-Safe Mode ──────────────────────────────────────────────────
    private var stigmaSafeActive = false

    private fun enterStigmaSafeMode() {
        stigmaSafeActive = true
        // Show a patient-facing dialog with large text yes/no questions
        val builder = android.app.AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Light_NoActionBar_Fullscreen)
        val scroll = ScrollView(this)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (32 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad, pad, pad)
            setBackgroundColor(getColor(R.color.colorBackground))
        }

        // Title
        layout.addView(TextView(this).apply {
            text = "🔒 Private — Patient answers directly"
            textSize = 20f
            setTypeface(null, Typeface.BOLD)
            setTextColor(getColor(R.color.colorPrimary))
            gravity = android.view.Gravity.CENTER
            setPadding(0, 0, 0, (24 * resources.displayMetrics.density).toInt())
        })

        // Sensitive questions — large checkboxes for patient to tap
        data class StigmaQ(val key: String, val hi: String, val en: String)
        val questions = listOf(
            StigmaQ("missed_period", "क्या मासिक धर्म छूटा है?", "Have you missed your period?"),
            StigmaQ("contraception_needed", "क्या गर्भनिरोधक चाहिए?", "Do you need contraception?"),
            StigmaQ("domestic_violence", "क्या घर में हिंसा हो रही है?", "Are you facing violence at home?"),
            StigmaQ("mental_health", "क्या मन बहुत उदास रहता है?", "Do you feel very sad or anxious?"),
            StigmaQ("sexual_health", "क्या यौन स्वास्थ्य की समस्या है?", "Do you have a sexual health concern?"),
        )

        val stigmaChecks = mutableMapOf<String, CheckBox>()
        for (q in questions) {
            val cb = CheckBox(this).apply {
                text = "${q.hi}\n${q.en}"
                textSize = 20f
                setTextColor(getColor(R.color.colorTextPrimary))
                buttonTintList = android.content.res.ColorStateList.valueOf(getColor(R.color.colorPrimary))
                val padV = (20 * resources.displayMetrics.density).toInt()
                setPadding((8 * resources.displayMetrics.density).toInt(), padV, 0, padV)
            }
            stigmaChecks[q.key] = cb
            layout.addView(cb)
            layout.addView(View(this).apply {
                layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT,
                    (2 * resources.displayMetrics.density).toInt())
                setBackgroundColor(getColor(R.color.colorDivider))
            })
        }

        // Done button
        val btnDone = Button(this).apply {
            text = "✓  DONE"
            textSize = 20f
            setTextColor(getColor(R.color.colorWhite))
            backgroundTintList = android.content.res.ColorStateList.valueOf(getColor(R.color.colorPrimary))
            val pad = (16 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad, pad, pad)
        }
        layout.addView(btnDone)

        scroll.addView(layout)
        val dialog = builder.setView(scroll).create()
        dialog.setCancelable(false)

        btnDone.setOnClickListener {
            // Capture stigma answers as extra symptoms
            for ((key, cb) in stigmaChecks) {
                if (cb.isChecked) {
                    extraSymptoms.add("🔒 $key")
                }
            }
            if (extraSymptoms.isNotEmpty()) showExtraSymptoms()
            stigmaSafeActive = false
            dialog.dismiss()
            Toast.makeText(this, "Private answers recorded securely", Toast.LENGTH_SHORT).show()
        }

        dialog.show()
    }

    // ── Build collapsible symptom categories ──────────────────────────────
    private fun buildSymptomCategories() {
        symptomCategoriesContainer.removeAllViews()
        symptomCheckboxes.clear()
        categoryBodies.clear()

        for (cat in getSymptomCategories()) {
            // Category card
            val card = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setBackgroundResource(R.drawable.bg_card_elevated)
                elevation = 2f
                val params = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                )
                params.bottomMargin = (8 * resources.displayMetrics.density).toInt()
                layoutParams = params
            }

            // Header (tap to expand/collapse)
            val header = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = android.view.Gravity.CENTER_VERTICAL
                val padH = (16 * resources.displayMetrics.density).toInt()
                val padV = (14 * resources.displayMetrics.density).toInt()
                setPadding(padH, padV, padH, padV)
            }
            val headerText = TextView(this).apply {
                text = "${cat.emoji}  ${cat.title}"
                textSize = 14f
                setTypeface(null, Typeface.BOLD)
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.colorTextPrimary))
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            }
            val arrow = TextView(this).apply {
                text = "▼"
                textSize = 11f
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.colorTextHint))
                tag = "arrow"
            }
            header.addView(headerText)
            header.addView(arrow)

            // Body (checkboxes, initially collapsed except first category)
            val body = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                val padStart = (8 * resources.displayMetrics.density).toInt()
                val padEnd = (16 * resources.displayMetrics.density).toInt()
                val padBot = (6 * resources.displayMetrics.density).toInt()
                setPadding(padStart, 0, padEnd, padBot)
                visibility = View.GONE
            }

            for ((i, symptom) in cat.symptoms.withIndex()) {
                val cb = CheckBox(this).apply {
                    text = symptom.label
                    textSize = 15f
                    setTextColor(ContextCompat.getColor(this@MainActivity, R.color.colorTextPrimary))
                    buttonTintList = ContextCompat.getColorStateList(this@MainActivity, R.color.colorPrimary)
                    val padV = (11 * resources.displayMetrics.density).toInt()
                    setPadding(0, padV, 0, padV)
                }
                symptomCheckboxes[symptom.key] = cb

                // Stigma-safe: show private mode button when sensitive symptoms checked
                val sensitiveKeys = setOf("pregnant", "vaginal_bleeding", "abnormal_discharge", "painful_urination")
                if (symptom.key in sensitiveKeys) {
                    cb.setOnCheckedChangeListener { _, _ ->
                        val btnStigma = findViewById<Button>(R.id.btnStigmaSafe)
                        val anySensitive = sensitiveKeys.any { symptomCheckboxes[it]?.isChecked == true }
                        btnStigma.visibility = if (anySensitive) View.VISIBLE else View.GONE
                    }
                }

                body.addView(cb)

                if (i < cat.symptoms.size - 1) {
                    val divider = View(this).apply {
                        layoutParams = LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            (1 * resources.displayMetrics.density).toInt()
                        ).apply { marginStart = (12 * resources.displayMetrics.density).toInt() }
                        setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.colorDivider))
                    }
                    body.addView(divider)
                }
            }

            categoryBodies.add(body)

            // Tap header to toggle with animation
            header.setOnClickListener {
                val isVisible = body.visibility == View.VISIBLE
                if (isVisible) {
                    animateOut(body)
                } else {
                    animateIn(body)
                }
                // Rotate arrow with animation
                val targetRotation = if (isVisible) 0f else 180f
                arrow.animate().rotation(targetRotation).setDuration(250)
                    .setInterpolator(DecelerateInterpolator()).start()
            }

            card.addView(header)
            card.addView(body)
            symptomCategoriesContainer.addView(card)
        }

        // Expand first category by default
        if (categoryBodies.isNotEmpty()) {
            categoryBodies[0].visibility = View.VISIBLE
        }
    }

    // ── Update all static UI text when language changes ───────────────────
    private fun updateStaticUI() {
        // Step labels
        findViewById<TextView>(R.id.tvStep1Label).text = t(
            "  चरण 1 — लक्षण बोलें", "  ಹಂತ 1 — ರೋಗಲಕ್ಷಣಗಳನ್ನು ಹೇಳಿ",
            "  దశ 1 — లక్షణాలు చెప్పండి", "  STEP 1 — SPEAK SYMPTOMS"
        )
        findViewById<TextView>(R.id.tvStep2Label).text = t(
            "  चरण 2 — लक्षण चुनें", "  ಹಂತ 2 — ರೋಗಲಕ್ಷಣ ದೃಢೀಕರಿಸಿ",
            "  దశ 2 — లక్షణాలు నిర్ధారించండి", "  STEP 2 — CONFIRM SYMPTOMS"
        )
        // Voice button (only if not currently recording)
        if (!btnVoice.text.toString().contains("LISTENING") && !btnVoice.text.toString().contains("सुन")) {
            btnVoice.text = t("🎙  बोलें", "🎙  ಮಾತಾಡಿ", "🎙  మాట్లాడండి", "🎙  TAP TO SPEAK")
        }
        // Voice status hint (only when idle)
        if (regStep == "idle") {
            tvVoiceStatus.text = t(
                "लक्षण बोलें या 'नया patient' कहें",
                "ಲಕ್ಷಣಗಳನ್ನು ಹೇಳಿ ಅಥವಾ 'hosa patient' ಅನ್ನಿ",
                "లక్షణాలు చెప్పండి లేదా 'kotta patient' అనండి",
                "Say symptoms or 'naya patient' to register"
            )
            tvVoiceStatus.setTextColor(getColor(R.color.colorTextHint))
        }
        // Gender spinner options
        val genders = when (regLang) {
            "hi" -> arrayOf("लिंग चुनें", "पुरुष", "महिला", "अन्य")
            "kn" -> arrayOf("ಲಿಂಗ ಆಯ್ಕೆ", "ಗಂಡು", "ಹೆಣ್ಣು", "ಇತರ")
            "te" -> arrayOf("లింగం ఎంచుకోండి", "పురుషుడు", "స్త్రీ", "ఇతర")
            else -> arrayOf("Select gender", "Male", "Female", "Other")
        }
        spinnerGender.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, genders)
        // Form hints
        etPatientAge.hint = t("उम्र (साल)", "ವಯಸ್ಸು (ವರ್ಷ)", "వయసు (సం.)", "Age (years)")
        etPatientVillage.hint = t("📍 गांव / राज्य", "📍 ಹಳ್ಳಿ / ರಾಜ್ಯ", "📍 గ్రామం / రాష్ట్రం", "📍 Village / State")
        // Pregnant checkbox
        cbNewPatientPregnant.text = t("🤰  गर्भवती हैं", "🤰  ಗರ್ಭಿಣಿ", "🤰  గర్భవతి", "🤰  Currently pregnant")
        // Buttons
        btnSaveNewPatient.text = t("✓  सेव करें", "✓  ಉಳಿಸಿ", "✓  సేవ్ చేయండి", "✓  SAVE PATIENT")
        btnEvaluate.text = t("▶  ट्राएज करें", "▶  ಮೌಲ್ಯಮಾಪನ ಮಾಡಿ", "▶  అంచనా వేయండి", "▶  GET TRIAGE DECISION")
        btnNewPatient.text = t("+ नया Patient", "+ ಹೊಸ ರೋಗಿ", "+ కొత్త రోగి", "+ NEW PATIENT")
    }

    // ── Patient list (max 8) ────────────────────────────────────────────
    private fun showPatientList() {
        lifecycleScope.launch {
            val patients = VisitDatabase.get(this@MainActivity).patientDao().getAllRecent()
            if (patients.isEmpty()) { patientListContainer.visibility = View.GONE; return@launch }
            patientListItems.removeAllViews()
            for (patient in patients.take(8)) {
                val villagePart = if (patient.village.isNotEmpty()) "  📍${patient.village}" else ""
                val row = TextView(this@MainActivity).apply {
                    text = "\uD83D\uDC64  ${patient.name}  ${if (patient.gender.isNotEmpty()) "· ${patient.gender}" else ""}$villagePart"
                    textSize = 15f
                    setTextColor(getColor(R.color.colorTextPrimary))
                    setPadding(0, (14 * resources.displayMetrics.density).toInt(), 0, (14 * resources.displayMetrics.density).toInt())
                    setOnClickListener { selectPatient(patient) }
                }
                patientListItems.addView(row)
                val divider = View(this@MainActivity).apply {
                    layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 1)
                    setBackgroundColor(getColor(R.color.colorDivider))
                }
                patientListItems.addView(divider)
            }
            animateIn(patientListContainer)
        }
    }

    private fun selectPatient(patient: Patient) {
        currentPatientId = patient.id
        currentPatientName = patient.name
        etPatientName.setText(patient.name)
        tvPatientId.text = patient.name
        tvPatientBadge.text = "RETURNING"
        patientListContainer.visibility = View.GONE
        cardNewPatientDetails.visibility = View.GONE
        findViewById<Button>(R.id.btnBackToList).visibility = View.VISIBLE
        showPatientSummary(patient)
    }

    // ── Patient search ────────────────────────────────────────────────────
    private fun searchPatient() {
        val name = etPatientName.text.toString().trim()
        if (name.isEmpty()) { Toast.makeText(this, "Enter a patient name", Toast.LENGTH_SHORT).show(); return }

        lifecycleScope.launch {
            val patients = VisitDatabase.get(this@MainActivity).patientDao().searchByName(name)
            if (patients.isNotEmpty()) {
                if (patients.size == 1) {
                    selectPatient(patients.first())
                } else {
                    // Show matching patients in list
                    patientListItems.removeAllViews()
                    for (p in patients) {
                        val row = TextView(this@MainActivity).apply {
                            text = "\uD83D\uDC64  ${p.name}  ${if (p.gender.isNotEmpty()) "· ${p.gender}" else ""}"
                            textSize = 15f
                            setTextColor(getColor(R.color.colorTextPrimary))
                            setPadding(0, 18, 0, 18)
                            setOnClickListener { selectPatient(p) }
                        }
                        patientListItems.addView(row)
                    }
                    patientListContainer.visibility = View.VISIBLE
                }
            } else {
                // New patient — show details form
                currentPatientId = UUID.randomUUID().toString()
                currentPatientName = name
                tvPatientId.text = "$name (NEW)"
                tvPatientBadge.text = "NEW"
                cardPatientSummary.visibility = View.GONE
                patientListContainer.visibility = View.GONE
                cardNewPatientDetails.visibility = View.VISIBLE
            }
        }
    }

    private fun saveNewPatientDetails() {
        val ageStr = etPatientAge.text.toString().trim()
        val villageStr = etPatientVillage.text.toString().trim()
        val genderIdx = spinnerGender.selectedItemPosition
        val gender = if (genderIdx > 0) spinnerGender.selectedItem.toString() else ""
        val isPregnant = cbNewPatientPregnant.isChecked

        val ageMillis = if (ageStr.isNotEmpty()) {
            System.currentTimeMillis() - (ageStr.toLongOrNull() ?: 0L) * 365L * 24 * 60 * 60 * 1000
        } else null

        lifecycleScope.launch {
            val patient = Patient(
                id = currentPatientId,
                name = currentPatientName,
                gender = gender,
                village = villageStr,
                dobMillis = ageMillis
            )
            val dao = VisitDatabase.get(this@MainActivity).patientDao()
            dao.insertPatient(patient)

            // Save village for SyncWorker backend sync
            if (villageStr.isNotEmpty()) {
                getSharedPreferences("swasthya", MODE_PRIVATE).edit()
                    .putString("village_code", villageStr).apply()
            }

            if (isPregnant) {
                dao.insertPregnancy(Pregnancy(
                    id = UUID.randomUUID().toString(),
                    patientId = currentPatientId,
                    week = 0,
                    highRisk = false
                ))
                // Auto-check pregnant symptom
                symptomCheckboxes["pregnant"]?.isChecked = true
            }

            // Auto-check age_under_5 if child
            if (ageStr.isNotEmpty() && (ageStr.toIntOrNull() ?: 99) < 5) {
                symptomCheckboxes["age_under_5"]?.isChecked = true
            }

            cardNewPatientDetails.visibility = View.GONE
            tvPatientBadge.text = "SAVED"
            Toast.makeText(this@MainActivity, "Patient saved: $currentPatientName", Toast.LENGTH_SHORT).show()
        }
    }

    private fun showPatientSummary(patient: Patient) {
        lifecycleScope.launch {
            val dao = VisitDatabase.get(this@MainActivity).patientDao()
            val visits = dao.getVisitsForPatient(patient.id, 5)
            val pregnancy = dao.getActivePregnancy(patient.id)
            val dueVax = dao.getDueVaccinations(patient.id)

            val lines = mutableListOf<String>()
            lines.add("${patient.name} · ${patient.gender}")

            if (visits.isNotEmpty()) {
                val last = visits.first()
                val daysAgo = ((System.currentTimeMillis() - last.timestamp) / (24 * 60 * 60 * 1000)).toInt()
                val triageLocal = when (last.triage) {
                    "Urgent Referral" -> t("🚨 तत्काल रेफरल", "🚨 ತುರ್ತು ರೆಫರಲ್", "🚨 అత్యవసర రిఫరల్", "🚨 Urgent Referral")
                    "PHC Visit" -> t("⚠️ PHC जाएं", "⚠️ PHC ಭೇಟಿ", "⚠️ PHC సందర్శన", "⚠️ PHC Visit")
                    else -> t("✅ घर पर देखभाल", "✅ ಮನೆ ಆರೈಕೆ", "✅ ఇంటి సంరక్షణ", "✅ Home Care")
                }
                val lastVisitLabel = t("पिछली विज़िट", "ಕೊನೆಯ ಭೇಟಿ", "చివరి సందర్శన", "Last visit")
                val daysLabel = t("दिन पहले", "ದಿನಗಳ ಹಿಂದೆ", "రోజుల క్రితం", "days ago")
                tvLastVisit.text = "$lastVisitLabel: $daysAgo $daysLabel — $triageLocal"
                tvLastVisit.visibility = View.VISIBLE
                val triageLabel = t("📋 पिछला ट्राएज", "📋 ಕೊನೆಯ ಟ್ರಯಾಜ್", "📋 చివరి ట్రయాజ్", "📋 Last triage")
                lines.add("$triageLabel: $triageLocal (${(last.confidence * 100).toInt()}%)")
            } else {
                tvLastVisit.text = t("पहले कोई विज़िट नहीं", "ಹಿಂದಿನ ಭೇಟಿ ಇಲ್ಲ", "ఇంతకు ముందు సందర్శనలు లేవు", "No previous visits")
                tvLastVisit.visibility = View.VISIBLE
            }

            if (pregnancy != null) {
                lines.add(t("🤰 गर्भवती: सप्ताह ${pregnancy.week}", "🤰 ಗರ್ಭಿಣಿ: ವಾರ ${pregnancy.week}", "🤰 గర్భవతి: వారం ${pregnancy.week}", "🤰 Pregnant: Week ${pregnancy.week}") +
                        if (pregnancy.highRisk) t(" (उच्च जोखिम)", " (ಅಧಿಕ ಅಪಾಯ)", " (అధిక ప్రమాదం)", " (HIGH RISK)") else "")
                symptomCheckboxes["pregnant"]?.isChecked = true
            }

            if (dueVax.isNotEmpty()) {
                val overdue = dueVax.count { it.isOverdue }
                val due = dueVax.count { it.isDue && !it.isOverdue }
                if (overdue > 0) lines.add(t("💉 $overdue टीकाकरण लेट", "💉 $overdue ಲಸಿಕೆಗಳು ತಡವಾಗಿವೆ", "💉 $overdue టీకాలు ఆలస్యం", "💉 $overdue vaccination(s) OVERDUE"))
                else if (due > 0) lines.add(t("💉 $due टीकाकरण बाकी", "💉 $due ಲಸಿಕೆಗಳು ಬಾಕಿ", "💉 $due టీకాలు మిగిలినవి", "💉 $due vaccination(s) due"))
            }

            // Auto-check age_under_5 based on DOB
            if (patient.dobMillis != null) {
                val ageYears = (System.currentTimeMillis() - patient.dobMillis) / (365L * 24 * 60 * 60 * 1000)
                if (ageYears < 5) symptomCheckboxes["age_under_5"]?.isChecked = true
            }

            tvPatientSummary.text = lines.joinToString("\n")

            val riskText = when {
                patient.riskScore >= 0.7f -> "Risk: HIGH"
                patient.riskScore >= 0.4f -> "Risk: MEDIUM"
                else -> "Risk: LOW"
            }
            val riskColor = when {
                patient.riskScore >= 0.7f -> getColor(R.color.colorUrgent)
                patient.riskScore >= 0.4f -> getColor(R.color.colorPHC)
                else -> getColor(R.color.colorHomeCare)
            }
            tvRiskLevel.text = riskText
            tvRiskLevel.setTextColor(riskColor)
            tvRiskLevel.visibility = View.VISIBLE
            animateIn(cardPatientSummary, 100)
        }
    }

    // ── Voice ─────────────────────────────────────────────────────────────
    private fun startVoiceInput() {
        voiceMode = "symptoms"

        // Animate voice button to "recording" state
        btnVoice.setBackgroundResource(R.drawable.bg_btn_voice_recording)
        btnVoice.text = "🔴  LISTENING..."
        val pulseAnim = AnimationUtils.loadAnimation(this, R.anim.pulse)
        btnVoice.startAnimation(pulseAnim)

        val prompt = if (regStep != "idle") promptForStep() else t("लक्षण बोलें, या 'नया patient' कहें", "ರೋಗಲಕ್ಷಣಗಳನ್ನು ಹೇಳಿ, ಅಥವಾ 'hosa patient' ಅನ್ನಿ", "లక్షణాలు చెప్పండి, లేదా 'kotta patient' అనండి", "Describe symptoms, or say 'naya patient'")
        val locale = when (regLang) {
            "hi" -> "hi-IN"; "kn" -> "kn-IN"; "te" -> "te-IN"; else -> Locale.getDefault().toLanguageTag()
        }
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, locale)
            putExtra(RecognizerIntent.EXTRA_PROMPT, prompt)
        }
        try { speechLauncher.launch(intent) }
        catch (_: Exception) {
            resetVoiceButton()
            Toast.makeText(this, "Voice unavailable", Toast.LENGTH_LONG).show()
        }
    }

    private fun resetVoiceButton() {
        btnVoice.clearAnimation()
        btnVoice.setBackgroundResource(R.drawable.bg_btn_voice)
        btnVoice.text = t("🎙  बोलें", "🎙  ಮಾತಾಡಿ", "🎙  మాట్లాడండి", "🎙  TAP TO SPEAK")
    }

    private fun promptForStep(): String = when (regStep) {
        "name"     -> t("कृपया patient का नाम बताएं", "ದಯವಿಟ್ಟು ರೋಗಿಯ ಹೆಸರು ಹೇಳಿ", "దయచేసి రోగి పేరు చెప్పండి", "Please say the patient's name")
        "age"      -> t("उम्र बताएं (साल में)", "ವಯಸ್ಸು ಹೇಳಿ (ವರ್ಷಗಳಲ್ಲಿ)", "వయసు చెప్పండి (సంవత్సరాలలో)", "Please say the age in years")
        "gender"   -> t("पुरुष या महिला?", "ಗಂಡು ಅಥವಾ ಹೆಣ್ಣು?", "పురుషుడు లేదా స్త్రీ?", "Male or Female?")
        "pregnant" -> t("क्या गर्भवती हैं? हाँ या ना", "ಗರ್ಭಿಣಿಯೇ? ಹೌದು ಅಥವಾ ಇಲ್ಲ", "గర్భవతా? అవును లేదా కాదు", "Is she pregnant? Yes or No")
        "village"  -> t("गांव और राज्य बताएं", "ಹಳ್ಳಿ ಮತ್ತು ರಾಜ್ಯ ಹೇಳಿ", "గ్రామం మరియు రాష్ట్రం చెప్పండి", "Say the village and state")
        else       -> "Speak"
    }

    private fun detectLanguage(text: String): String {
        val hasDevanagari = text.any { it.code in 0x0900..0x097F }
        val hasKannada = text.any { it.code in 0x0C80..0x0CFF }
        val hasTelugu = text.any { it.code in 0x0C00..0x0C7F }
        val hindiKeywords = listOf("naya", "naye", "patient", "mariz", "karein", "karo", "jodo", "bataye")
        val kannadaKeywords = listOf("hosa", "serisi", "roogi", "hesaru", "heli")
        val teluguKeywords = listOf("kotta", "kottha", "roogi", "cheppandi", "cherkandi", "peru")
        val lower = text.lowercase()
        return when {
            hasTelugu -> "te"
            hasKannada -> "kn"
            hasDevanagari -> "hi"
            teluguKeywords.any { it in lower } -> "te"
            kannadaKeywords.any { it in lower } -> "kn"
            hindiKeywords.any { it in lower } -> "hi"
            else -> "en"
        }
    }

    private fun handleVoiceCommand(text: String) {
        val lower = text.lowercase()
        // Only trigger new patient if BOTH a "new" word AND a "patient" word are present,
        // or specific full phrases are said. Standalone "मरीज़" in symptom sentences should NOT trigger.
        val newWords = listOf("naya", "naye", "new", "add", "jodo", "नया", "नये", "नई", "जोड़", "ऐड",
            "hosa", "ಹೊಸ", "ಸೇರಿಸಿ", "kotta", "kottha", "కొత్త", "చేర్కండి")
        val patientWords = listOf("patient", "mariz", "पेशेंट", "मरीज", "रोगी",
            "roogi", "ರೋಗಿ", "రోగి")
        val hasNewWord = newWords.any { it in lower }
        val hasPatientWord = patientWords.any { it in lower }
        val isFullPhrase = "naya patient" in lower || "new patient" in lower ||
                "naye patient" in lower || "patient add" in lower ||
                "add patient" in lower || "naya mariz" in lower ||
                "hosa patient" in lower || "roogi serisi" in lower ||
                "kotta patient" in lower || "kottha roogi" in lower || "roogi cherkandi" in lower
        val isNewPatient = isFullPhrase || (hasNewWord && hasPatientWord)

        if (isNewPatient) {
            regLang = detectLanguage(text)
            regStep = "name"
            regName = ""; regAge = ""; regGender = ""
            val msg = t(
                "✓ नया patient — कृपया नाम बताएं",
                "✓ ಹೊಸ ರೋಗಿ — ದಯವಿಟ್ಟು ಹೆಸರು ಹೇಳಿ",
                "✓ కొత్త రోగి — దయచేసి పేరు చెప్పండి",
                "✓ New patient — Please say the name"
            )
            tvVoiceStatus.text = msg
            tvVoiceStatus.setTextColor(getColor(R.color.colorPrimary))
            // Speak prompt, then auto-open mic
            speak(msg, thenListen = true)
            return
        }
        parseVoiceInput(text)
    }

    // ── Registration state machine steps ──────────────────────────────────
    private fun onRegName(text: String) {
        regName = text.trim()
        if (regName.isEmpty()) { regStep = "idle"; return }

        etPatientName.setText(regName)
        tvPatientId.text = "$regName (NEW)"
        tvPatientBadge.text = "NEW"
        currentPatientId = UUID.randomUUID().toString()
        currentPatientName = regName

        regStep = "age"
        val msg = t(
            "✓ नाम: $regName\n अब उम्र बताएं (साल में)",
            "✓ ಹೆಸರು: $regName\n ಈಗ ವಯಸ್ಸು ಹೇಳಿ (ವರ್ಷಗಳಲ್ಲಿ)",
            "✓ పేరు: $regName\n ఇప్పుడు వయసు చెప్పండి (సంవత్సరాలలో)",
            "✓ Name: $regName\n Now say the age (in years)"
        )
        speak(msg, thenListen = true)
    }

    private fun onRegAge(text: String) {
        // Extract number from speech (might say "25 saal" or "panchis" or just "25")
        val numberWords = mapOf(
            "ek" to 1, "do" to 2, "teen" to 3, "chaar" to 4, "paanch" to 5,
            "chhe" to 6, "saat" to 7, "aath" to 8, "nau" to 9, "das" to 10,
            "bees" to 20, "tees" to 30, "chalees" to 40, "pachaas" to 50,
            "one" to 1, "two" to 2, "three" to 3, "four" to 4, "five" to 5,
        )
        val lower = text.lowercase().trim()
        val num = lower.replace(Regex("[^0-9]"), "")
        regAge = if (num.isNotEmpty()) {
            num
        } else {
            val match = numberWords.entries.find { it.key in lower }
            match?.value?.toString() ?: ""
        }

        if (regAge.isEmpty()) {
            val msg = t("उम्र समझ नहीं आई, कृपया फिर बताएं", "ವಯಸ್ಸು ಅರ್ಥವಾಗಲಿಲ್ಲ, ಮತ್ತೆ ಹೇಳಿ", "వయసు అర్థం కాలేదు, మళ్ళీ చెప్పండి", "Didn't catch the age, please say again")
            speak(msg, thenListen = true)
            return
        }

        etPatientAge.setText(regAge)

        regStep = "gender"
        val msg = t(
            "✓ उम्र: $regAge साल\n पुरुष या महिला?",
            "✓ ವಯಸ್ಸು: $regAge ವರ್ಷ\n ಗಂಡು ಅಥವಾ ಹೆಣ್ಣು?",
            "✓ వయసు: $regAge సంవత్సరాలు\n పురుషుడు లేదా స్త్రీ?",
            "✓ Age: $regAge years\n Male or Female?"
        )
        speak(msg, thenListen = true)
    }

    private fun onRegGender(text: String) {
        val lower = text.lowercase().trim()
        // Check female FIRST (more specific words), then male
        // Use word boundary or exact checks to avoid "male" matching inside "female"
        val femaleWords = listOf("female", "mahila", "aurat", "ladki", "stree",
            "hennu", "woman", "girl", "महिला", "औरत", "लड़की", "स्त्री",
            "ಹೆಣ್ಣು", "ಮಹಿಳೆ", "ఆడ", "స్త్రీ", "aaada", "stree")
        val maleWords = listOf("purush", "aadmi", "ladka",
            "man", "boy", "पुरुष", "आदमी", "लड़का",
            "ಗಂಡು", "ಪುರುಷ", "మగ", "పురుషుడు", "maga")

        val isFemale = femaleWords.any { it in lower }
        // "male" alone — but NOT if "female" is the word
        val hasMaleWord = maleWords.any { it in lower } ||
                (Regex("\\bmale\\b").containsMatchIn(lower) && "female" !in lower)

        regGender = when {
            isFemale -> "Female"
            hasMaleWord -> "Male"
            else -> ""
        }

        if (regGender.isEmpty()) {
            val msg = t("समझ नहीं आया — पुरुष या महिला?", "ಅರ್ಥವಾಗಲಿಲ್ಲ — ಗಂಡು ಅಥವಾ ಹೆಣ್ಣು?", "అర్థం కాలేదు — పురుషుడు లేదా స్త్రీ?", "Didn't catch — Male or Female?")
            speak(msg, thenListen = true)
            return
        }

        // Set spinner
        val genderIdx = when (regGender) { "Male" -> 1; "Female" -> 2; else -> 0 }
        spinnerGender.setSelection(genderIdx)

        if (regGender == "Female") {
            regStep = "pregnant"
            val msg = t(
                "✓ महिला\n क्या गर्भवती हैं? हाँ या ना",
                "✓ ಹೆಣ್ಣು\n ಗರ್ಭಿಣಿಯೇ? ಹೌದು ಅಥವಾ ಇಲ್ಲ",
                "✓ స్త్రీ\n గర్భవతా? అవును లేదా కాదు",
                "✓ Female\n Is she pregnant? Yes or No"
            )
            speak(msg, thenListen = true)
        } else {
            // Male/Other — skip pregnancy, ask village
            askVillage()
        }
    }

    private fun onRegPregnant(text: String) {
        val lower = text.lowercase()
        val isYes = "haan" in lower || "ha" in lower || "yes" in lower ||
                "houdu" in lower || "ಹೌದು" in lower || "hau" in lower || "ji" in lower ||
                "avunu" in lower || "అవును" in lower || "unu" in lower ||
                "हां" in lower || "हा" in lower || "जी" in lower
        if (isYes) cbNewPatientPregnant.isChecked = true
        askVillage()
    }

    private fun askVillage() {
        regStep = "village"
        val msg = t(
            "✓ अब गांव और राज्य बताएं",
            "✓ ಈಗ ಹಳ್ಳಿ ಮತ್ತು ರಾಜ್ಯ ಹೇಳಿ",
            "✓ ఇప్పుడు గ్రామం మరియు రాష్ట్రం చెప్పండి",
            "✓ Now say the village and state"
        )
        speak(msg, thenListen = true)
    }

    private fun onRegVillage(text: String) {
        regVillage = text.trim()
        if (regVillage.isEmpty()) {
            val msg = t("गांव समझ नहीं आया, कृपया फिर बताएं", "ಹಳ್ಳಿ ಅರ್ಥವಾಗಲಿಲ್ಲ, ಮತ್ತೆ ಹೇಳಿ", "గ్రామం అర్థం కాలేదు, మళ్ళీ చెప్పండి", "Didn't catch the village, please say again")
            speak(msg, thenListen = true)
            return
        }
        etPatientVillage.setText(regVillage)
        finishVoiceRegistration(cbNewPatientPregnant.isChecked)
    }

    private fun finishVoiceRegistration(isPregnant: Boolean) {
        regStep = "idle"
        if (isPregnant) cbNewPatientPregnant.isChecked = true

        // Show the form filled with voice data — let user review and tap Save
        cardNewPatientDetails.visibility = View.VISIBLE
        patientListContainer.visibility = View.GONE
        cardPatientSummary.visibility = View.GONE

        val pregnantStr = if (isPregnant) t(" | गर्भवती ✓", " | ಗರ್ಭಿಣಿ ✓", " | గర్భవతి ✓", " | Pregnant ✓") else ""
        val villageStr = if (regVillage.isNotEmpty()) t(" | 📍 $regVillage", " | 📍 $regVillage", " | 📍 $regVillage", " | 📍 $regVillage") else ""
        val msg = t(
            "✓ $regName, $regAge साल, $regGender$pregnantStr$villageStr\n\nजानकारी जाँचें और Save दबाएं",
            "✓ $regName, $regAge ವರ್ಷ, $regGender$pregnantStr$villageStr\n\nಮಾಹಿತಿ ಪರಿಶೀಲಿಸಿ Save ಒತ್ತಿ",
            "✓ $regName, $regAge సంవత్సరాలు, $regGender$pregnantStr$villageStr\n\nసమాచారం చూసి Save నొక్కండి",
            "✓ $regName, $regAge yrs, $regGender$pregnantStr$villageStr\n\nReview and tap Save"
        )
        speak(msg)
    }

    private fun parseVoiceInput(text: String) {
        val lower = text.lowercase()
        val keywords = mapOf(
            "age_under_5" to listOf("child", "baby", "infant", "bachcha", "baccha", "shishu", "5 year", "5 sal", "5 saal", "chhota", "chhoti", "bache", "bacha",
                "बच्चा", "बच्चे", "बच्ची", "बच्चों", "शिशु", "छोटा", "छोटी", "5 साल", "chota baccha", "nanha"),
            "fever" to listOf("fever", "hot", "temperature", "bukhar", "bukhaar", "tapman", "tez bukhar", "badan garam", "garmi",
                "बुखार", "बुख़ार", "तापमान", "तेज बुखार", "बदन गरम", "गर्मी", "ज्वर",
                "jwar", "taap", "bukhar hai", "shareer garam"),
            "fast_breathing" to listOf("breath", "breathing", "saans", "sans", "sas", "laboured", "tez saans", "saans tez", "saans phool",
                "सांस", "सास", "तेज सांस", "सांस तेज", "सांस फूल", "सांस लेने में",
                "saans lene mein", "saans phoolna", "dum ghutna", "dam", "breathless"),
            "chest_indrawing" to listOf("chest", "indrawing", "seena", "dhansna", "chhati", "chaati", "seena dhansna",
                "छाती", "सीना", "छाती धंसना", "सीना धंसना", "chhati dhansna", "ribs pulling"),
            "diarrhea" to listOf("diarrhea", "loose", "dast", "potty", "watery", "patla", "patli potty", "pani jaisa", "daste",
                "दस्त", "पतला", "पतली पॉटी", "पानी जैसा", "दस्ते", "लूज मोशन",
                "loose motion", "jhada", "ulti dast", "patlaa", "liquid stool"),
            "vomiting" to listOf("vomit", "vomiting", "ulti", "ultee", "qay",
                "उल्टी", "उलटी", "क़ै", "मतली", "nausea", "ji machlana", "matli"),
            "convulsions" to listOf("convulsion", "seizure", "fit", "mirgi", "jhatkae", "jhatke", "daure",
                "दौरे", "मिर्गी", "झटके", "फिट", "epilepsy", "akdan", "fits"),
            "unable_to_feed" to listOf("not eating", "feed", "drink", "dudh nahi", "kha nahi", "kuch nahi kha", "peeta nahi", "khana nahi", "dudh",
                "खाना नहीं", "खा नहीं", "दूध नहीं", "पीता नहीं", "कुछ नहीं खा", "पी नहीं",
                "not drinking", "refuse milk", "refuse food", "nahi khata", "nahi peeta"),
            "pregnant" to listOf("pregnant", "garbhvati", "hamal", "garbh", "pet se", "paet se",
                "गर्भवती", "प्रेगनेंट", "गर्भ", "पेट से", "हामला", "pregnancy"),
            "vaginal_bleeding" to listOf("bleeding", "blood", "khoon", "khun", "rakt", "raktasrav", "khoon aa raha", "khoon nikal",
                "खून", "ख़ून", "रक्त", "ब्लीडिंग", "खून आ रहा", "खून निकल", "रक्तस्राव",
                "vaginal blood", "yoni se khoon"),
            "severe_headache" to listOf("headache", "sir dard", "sar dard", "sir me dard", "sar mein dard", "tez dard",
                "सर दर्द", "सिर दर्द", "सिरदर्द", "सर में दर्द", "सिर में दर्द", "तेज दर्द",
                "head pain", "sir pakad", "maatha dard", "migraine"),
            "limb_swelling" to listOf("swelling", "soojan", "sujan", "haathi pair", "elephantiasis", "filaria", "pair suja", "haath suja", "pair mein sujan",
                "सूजन", "हाथी पांव", "पैर सूजा", "हाथ सूजा", "पैर में सूजन",
                "elephant foot", "elephant leg", "elephantitis", "filariasis",
                "hatipav", "hathi pav", "hathipav", "haathi paon", "hathi paon",
                "haathipaav", "hathipaav", "swollen leg", "swollen arm", "swollen limb",
                "leg swelling", "arm swelling", "limb swelling", "hatipaw",
                "haathi", "tang sujan", "baanh sujan", "pair phoolna", "pair phool",
                "टांग सूजन", "बांह सूजन", "पैर फूलना", "हाथीपांव", "हाथी पाँव",
                "paer sujan", "paer suja", "haath sujan", "gooda sujan",
                "filarial", "lymphedema", "pair mota"),
            "groin_swelling" to listOf("groin", "groin swelling", "jangha", "andkosh", "andkosh sujan", "anguthi sujan",
                "जांघ", "अंडकोष", "अंडकोष सूजन", "गुप्तांग सूजन",
                "testicle", "scrotal", "scrotum swelling", "hydrocele", "inguinal",
                "jangha mein sujan", "niche sujan", "pait ke niche"),
            "abnormal_discharge" to listOf("discharge", "safed pani", "white discharge", "leucorrhoea", "likoria", "safed paani",
                "सफेद पानी", "डिस्चार्ज", "लिकोरिया", "योनि स्राव",
                "white water", "vaginal discharge", "yoni srav"),
            "painful_urination" to listOf("urine", "peshab", "painful urin", "jalan", "uti", "peshab mein jalan", "peshab mein dard", "pisab",
                "पेशाब", "जलन", "पेशाब में जलन", "पेशाब में दर्द", "मूत्र",
                "burning urine", "urine pain", "peshab ki jalan", "muthra"),
            "abdominal_pain" to listOf("stomach", "pet dard", "abdominal", "cramp", "pet mein", "pet me dard", "paet dard", "paet mein",
                "पेट दर्द", "पेट में दर्द", "पेट में", "ऐंठन", "पेट",
                "stomach pain", "tummy pain", "pet mein marod", "marod"),
            "pallor" to listOf("pale", "pallor", "peela", "pila", "safed chehra", "anemia", "khoon ki kami", "rang uda",
                "पीलापन", "पीला", "सफेद चेहरा", "एनीमिया", "खून की कमी", "रंग उड़ा",
                "anaemia", "paleness", "pili aankhen", "pila rang"),
            "weakness" to listOf("weakness", "kamzori", "kamjori", "thakan", "fatigue", "tired", "kamzor", "thakaan",
                "कमजोरी", "कमज़ोरी", "थकान", "थकावट", "कमजोर",
                "thakawat", "exhaustion", "low energy", "shakti nahi"),
            "visible_wasting" to listOf("wasting", "thin", "patla", "dubla", "malnutrition", "kuposhan", "bahut patla", "sukha",
                "पतला", "दुबला", "कुपोषण", "बहुत पतला", "सूखा",
                "malnourished", "very thin", "haddi", "bones visible", "sukhi haddi"),
            "bilateral_edema" to listOf("edema", "both feet", "dono pair", "swollen feet", "pair sujan", "paon mein sujan", "dono paon",
                "दोनों पैर", "पैर सूजन", "पांव में सूजन", "दोनों पांव", "एडिमा",
                "feet swelling", "dono pair sujan", "both legs swollen"),
            "severe_cough" to listOf("severe cough", "bad cough", "khansi", "khaansi", "buri khansi", "tez khansi",
                "खांसी", "खाँसी", "बुरी खांसी", "तेज़ खांसी", "ज़ोर की खांसी",
                "coughing badly", "continuous cough", "lagatar khansi"),
            "breathing_issues" to listOf("breathing issue", "breathing problem", "cannot breathe", "saans nahi", "saans ki taklif",
                "सांस की तकलीफ", "सांस नहीं आ रही", "दम घुटना",
                "suffocating", "choking", "dum", "dum ghutna"),
        )

        val matchedKeys = mutableSetOf<String>()
        val matchedWordSpans = mutableListOf<String>()

        for ((key, words) in keywords) {
            val matchedWord = words.find { it in lower }
            if (matchedWord != null) {
                symptomCheckboxes[key]?.isChecked = true
                matchedKeys.add(key)
                matchedWordSpans.add(matchedWord)
            }
        }

        // Collapse all categories, then expand only the matched ones
        smartExpandCategories(matchedKeys)

        // Detect unmatched portions of the input
        var remaining = lower
        for (word in matchedWordSpans) {
            remaining = remaining.replace(word, " ")
        }
        // Also strip common filler words
        val fillers = listOf("and", "aur", "hai", "hain", "ka", "ki", "ke", "ko", "mein",
            "se", "the", "is", "has", "have", "having", "with", "also", "patient", "male",
            "female", "man", "woman", "ek", "unko", "unhe", "body", "in")
        for (f in fillers) remaining = remaining.replace(Regex("\\b$f\\b"), " ")
        remaining = remaining.replace(Regex("[,\\.\\-]"), " ").trim()
        remaining = remaining.replace(Regex("\\s+"), " ").trim()

        if (remaining.length > 2 && remaining.split(" ").any { it.length > 2 }) {
            extraSymptoms.add(remaining)
            showExtraSymptoms()
        }

        val matchCount = matchedKeys.size
        val status = if (matchCount > 0) {
            "\u2713 Heard: \"$text\" — $matchCount symptom(s) matched"
        } else {
            "\u2713 Heard: \"$text\" — no checklist match, added as note"
        }
        tvVoiceStatus.text = status
        tvVoiceStatus.setTextColor(getColor(R.color.colorPrimary))

        // If nothing matched at all, capture entire text as extra symptom
        if (matchCount == 0 && text.trim().length > 2) {
            extraSymptoms.add(text.trim())
            showExtraSymptoms()
        }
    }

    private fun showExtraSymptoms() {
        if (extraSymptoms.isEmpty()) {
            cardExtraSymptoms.visibility = View.GONE
            return
        }
        tvExtraSymptoms.text = extraSymptoms.joinToString("\n") { "• $it" }
        if (cardExtraSymptoms.visibility != View.VISIBLE) {
            animateIn(cardExtraSymptoms)
        }
    }

    /** Collapse all categories, then expand only those containing matched symptom keys */
    private fun smartExpandCategories(matchedKeys: Set<String>) {
        val categories = getSymptomCategories()
        for ((i, cat) in categories.withIndex()) {
            if (i >= categoryBodies.size) continue
            val hasMatch = cat.symptoms.any { it.key in matchedKeys }
            if (hasMatch && categoryBodies[i].visibility != View.VISIBLE) {
                animateIn(categoryBodies[i])
            } else if (!hasMatch && categoryBodies[i].visibility == View.VISIBLE) {
                animateOut(categoryBodies[i])
            }
            // Update arrow rotation
            val card = symptomCategoriesContainer.getChildAt(i) as? LinearLayout ?: continue
            val header = card.getChildAt(0) as? LinearLayout ?: continue
            for (j in 0 until header.childCount) {
                val child = header.getChildAt(j)
                if (child is TextView && child.tag == "arrow") {
                    child.animate().rotation(if (hasMatch) 180f else 0f)
                        .setDuration(250).setInterpolator(DecelerateInterpolator()).start()
                }
            }
        }
    }

    private fun expandCategoryContaining(symptomKey: String) {
        val categories = getSymptomCategories()
        for ((i, cat) in categories.withIndex()) {
            if (cat.symptoms.any { it.key == symptomKey } && i < categoryBodies.size) {
                categoryBodies[i].visibility = View.VISIBLE
            }
        }
    }

    // ── Triage ────────────────────────────────────────────────────────────
    private fun newPatient() {
        currentPatientId = UUID.randomUUID().toString()
        currentPatientName = ""
        tvPatientId.text = currentPatientId.take(8).uppercase()
        tvPatientBadge.text = "NEW"
    }

    private fun runTriage() {
        val symptoms = mutableMapOf<String, Boolean>()
        for ((key, cb) in symptomCheckboxes) {
            symptoms[key] = cb.isChecked
        }
        // Also map dual-keys for protocols (only if not already a standalone checkbox)
        symptoms["foul_smell"] = symptoms["abnormal_discharge"] ?: false
        symptoms["frequent_urination"] = symptoms["painful_urination"] ?: false
        symptoms["breathlessness"] = symptoms["fast_breathing"] ?: false

        var result = TriageEngine.evaluate(this, symptoms)

        // If confidence is low and we have follow-up questions, show them first
        if (result.followUpQuestions.isNotEmpty()) {
            showFollowUpDialog(result, symptoms)
            return
        }

        finishTriage(result, symptoms)
    }

    // ── Follow-up Questions — Voice-Driven Sequential Flow ──────────────
    // State for voice-driven follow-up
    private var followUpQuestions: List<TriageEngine.FollowUpQuestion> = emptyList()
    private var followUpIndex: Int = 0
    private var followUpAnswers: MutableMap<String, Int> = mutableMapOf()
    private var followUpTotalBoost: Float = 0f
    private var followUpShouldOpenCamera: Boolean = false
    private var followUpInitialResult: TriageEngine.TriageResult? = null
    private var followUpSymptoms: MutableMap<String, Boolean>? = null
    private var followUpDialog: android.app.AlertDialog? = null
    private var followUpRadioGroups: MutableMap<String, android.widget.RadioGroup> = mutableMapOf()
    private var followUpCurrentQuestionTv: TextView? = null
    private var followUpStatusTv: TextView? = null
    private var followUpCards: MutableList<LinearLayout> = mutableListOf()
    private var followUpSummaryTv: TextView? = null

    private fun showFollowUpDialog(initialResult: TriageEngine.TriageResult, symptoms: MutableMap<String, Boolean>) {
        val questions = initialResult.followUpQuestions
        if (questions.isEmpty()) {
            finishTriage(initialResult, symptoms)
            return
        }

        // Initialize follow-up state
        followUpQuestions = questions
        followUpIndex = 0
        followUpAnswers.clear()
        followUpTotalBoost = 0f
        followUpShouldOpenCamera = false
        followUpInitialResult = initialResult
        followUpSymptoms = symptoms
        followUpRadioGroups.clear()
        followUpCards.clear()
        followUpSummaryTv = null

        val confPct = (initialResult.confidence * 100).toInt()
        val dp = resources.displayMetrics.density

        val builder = android.app.AlertDialog.Builder(this)
        val scroll = ScrollView(this)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (20 * dp).toInt()
            setPadding(pad, (16 * dp).toInt(), pad, (12 * dp).toInt())
        }

        // Title
        layout.addView(TextView(this).apply {
            text = t(
                "🔍 कुछ और सवाल (विश्वास: $confPct%)",
                "🔍 ಹೆಚ್ಚಿನ ಪ್ರಶ್ನೆಗಳು ($confPct%)",
                "🔍 మరిన్ని ప్రశ్నలు ($confPct%)",
                "🔍 Follow-up questions ($confPct%)"
            )
            textSize = 16f
            setTypeface(null, Typeface.BOLD)
            setTextColor(getColor(R.color.colorPrimary))
            setPadding(0, 0, 0, (4 * dp).toInt())
        })

        // Status bar
        val statusTv = TextView(this).apply {
            text = t(
                "सवाल 1/${questions.size} — सुनिए, फिर नंबर दबाएं",
                "ಪ್ರಶ್ನೆ 1/${questions.size} — ಕೇಳಿ, ನಂತರ ಸಂಖ್ಯೆ ಒತ್ತಿ",
                "ప్రశ్న 1/${questions.size} — వినండి, తర్వాత నంబర్ నొక్కండి",
                "Question 1/${questions.size} — listen, then tap number"
            )
            textSize = 12f
            setTextColor(getColor(R.color.colorTextSecondary))
            setPadding(0, 0, 0, (12 * dp).toInt())
        }
        followUpStatusTv = statusTv
        layout.addView(statusTv)

        // Current question text (large)
        val currentQTv = TextView(this).apply {
            val q = questions[0]
            val qText = if (regLang == "hi" && q.questionHi.isNotEmpty()) q.questionHi else q.questionEn
            text = "🔊  $qText"
            textSize = 17f
            setTypeface(null, Typeface.BOLD)
            setTextColor(getColor(R.color.colorTextPrimary))
            setPadding(0, 0, 0, (14 * dp).toInt())
        }
        followUpCurrentQuestionTv = currentQTv
        layout.addView(currentQTv)

        // Build one card per question with BIG TAP BUTTONS
        for ((qIdx, question) in questions.withIndex()) {
            val qCard = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                visibility = if (qIdx == 0) View.VISIBLE else View.GONE
            }

            // Big number buttons in a flow layout
            val buttonContainer = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(0, 0, 0, (8 * dp).toInt())
            }

            for ((optIdx, option) in question.options.withIndex()) {
                val localLabel = if (regLang != "en") localizeOptionLabel(option.label) else option.label
                val btn = Button(this).apply {
                    text = "${optIdx + 1}    $localLabel"
                    textSize = 16f
                    setTypeface(null, Typeface.BOLD)
                    isAllCaps = false
                    setTextColor(getColor(R.color.colorTextPrimary))
                    setBackgroundResource(R.drawable.bg_card_elevated)
                    elevation = 2f
                    gravity = android.view.Gravity.START or android.view.Gravity.CENTER_VERTICAL
                    val padH = (16 * dp).toInt()
                    val padV = (14 * dp).toInt()
                    setPadding(padH, padV, padH, padV)
                    val lp = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    )
                    lp.bottomMargin = (8 * dp).toInt()
                    layoutParams = lp

                    setOnClickListener {
                        onFollowUpOptionTapped(qIdx, optIdx)
                    }
                }
                buttonContainer.addView(btn)
            }

            qCard.addView(buttonContainer)
            followUpCards.add(qCard)
            layout.addView(qCard)
        }

        // Divider
        layout.addView(View(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                (1 * dp).toInt()
            )
            setBackgroundColor(getColor(R.color.colorDivider))
        })

        // Answered summary
        val answeredSummaryTv = TextView(this).apply {
            text = ""
            textSize = 13f
            setTextColor(getColor(R.color.colorHomeCare))
            setPadding(0, (8 * dp).toInt(), 0, 0)
        }
        layout.addView(answeredSummaryTv)
        followUpSummaryTv = answeredSummaryTv

        scroll.addView(layout)

        val dialog = builder.setView(scroll)
            .setPositiveButton(t("🔊 फिर से सुनें", "🔊 ಮತ್ತೆ ಕೇಳಿ", "🔊 మళ్ళీ వినండి", "🔊 Hear Again")) { _, _ -> }
            .setNeutralButton(t("✓ जांच करें", "✓ ಮೌಲ್ಯಮಾಪನ", "✓ అంచనా", "✓ Evaluate Now")) { _, _ -> }
            .setNegativeButton(t("छोड़ें", "ಬಿಡಿ", "వదిలేయండి", "Skip")) { _, _ ->
                followUpDialog = null
                finishTriage(initialResult, symptoms)
            }
            .create()

        dialog.setCancelable(false)
        dialog.show()
        followUpDialog = dialog

        // 🔊 Hear Again: replay current question via TTS
        dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE)?.setOnClickListener {
            speakFollowUpQuestionOnly()
        }

        // ✓ Evaluate Now: finish with whatever answers we have
        dialog.getButton(android.app.AlertDialog.BUTTON_NEUTRAL)?.setOnClickListener {
            finishFollowUp()
        }

        // Auto-speak the first question
        android.os.Handler(mainLooper).postDelayed({
            if (followUpDialog?.isShowing == true) speakFollowUpQuestionOnly()
        }, 500)
    }

    /** TTS speaks the question + options aloud — NO mic opening after */
    private fun speakFollowUpQuestionOnly() {
        if (followUpIndex >= followUpQuestions.size) return
        val question = followUpQuestions[followUpIndex]
        val qText = if (regLang != "en" && question.questionHi.isNotEmpty()) question.questionHi else question.questionEn

        val optionsSpeech = question.options.mapIndexed { i, opt ->
            val label = if (regLang != "en") localizeOptionLabel(opt.label) else opt.label
            "${i + 1}, $label"
        }.joinToString(". ")
        val tapPrompt = t(
            "नंबर दबाएं। फिर से सुनने के लिए, फिर से सुनें बटन दबाएं",
            "ಸಂಖ್ಯೆ ಒತ್ತಿ। ಮತ್ತೆ ಕೇಳಲು, ಮತ್ತೆ ಕೇಳಿ ಒತ್ತಿ",
            "నంబర్ నొక్కండి। మళ్ళీ వినడానికి, మళ్ళీ వినండి నొక్కండి",
            "Tap the number. To hear again, tap Hear Again"
        )

        val fullSpeech = "$qText. $optionsSpeech. $tapPrompt"

        if (ttsReady) {
            val locale = when (regLang) {
                "hi" -> Locale("hi", "IN"); "kn" -> Locale("kn", "IN"); "te" -> Locale("te", "IN"); else -> Locale.ENGLISH
            }
            tts?.language = locale
            tts?.setSpeechRate(0.85f)
            tts?.setPitch(0.95f)
            tts?.setOnUtteranceProgressListener(null) // No mic after speaking
            val clean = fullSpeech.replace(Regex("[🔊🎙📸⏱️📊🎨❓👆✓]"), "").replace("\n", ". ")
                .replace(Regex("(\\d+)-(\\d+)"), "$1 ${t("से", "ರಿಂದ", "నుండి", "to")} $2")
            tts?.speak(clean, TextToSpeech.QUEUE_FLUSH, null, "followup_q_${followUpIndex}")
        }
    }

    /** Called when user taps a numbered option button */
    private fun onFollowUpOptionTapped(questionIdx: Int, optionIdx: Int) {
        if (questionIdx != followUpIndex) return // safety
        val question = followUpQuestions[questionIdx]
        val option = question.options[optionIdx]

        // Record answer
        followUpAnswers[question.id] = optionIdx
        followUpTotalBoost += option.weightBoost
        if (option.triggersCamera) followUpShouldOpenCamera = true

        // Brief confirmation
        val localLabel = if (regLang != "en") localizeOptionLabel(option.label) else option.label
        Toast.makeText(this, "✓ $localLabel", Toast.LENGTH_SHORT).show()

        // Move to next question
        followUpIndex++
        updateFollowUpUI()

        if (followUpIndex < followUpQuestions.size) {
            // Speak next question after a short pause
            android.os.Handler(mainLooper).postDelayed({
                if (followUpDialog?.isShowing == true) speakFollowUpQuestionOnly()
            }, 600)
        } else {
            // All done — auto-finish
            val doneMsg = t("✓ सभी सवालों के जवाब मिले!", "✓ ಎಲ್ಲಾ ಉತ್ತರಗಳು ಬಂದವು!", "✓ అన్ని సమాధానాలు వచ్చాయి!", "✓ All answered!")
            Toast.makeText(this, doneMsg, Toast.LENGTH_SHORT).show()
            android.os.Handler(mainLooper).postDelayed({
                finishFollowUp()
            }, 800)
        }
    }

    private fun speakFollowUpQuestion() {
        if (followUpIndex >= followUpQuestions.size) {
            finishFollowUp()
            return
        }
        val question = followUpQuestions[followUpIndex]
        val qText = if (regLang != "en" && question.questionHi.isNotEmpty()) question.questionHi else question.questionEn

        // Build options text for speech — speak Hindi labels + tell user to say number only
        val optionsSpeech = question.options.mapIndexed { i, opt ->
            val label = if (regLang != "en") localizeOptionLabel(opt.label) else opt.label
            "${i + 1}, $label"
        }.joinToString(". ")
        val numberPrompt = t(
            "सिर्फ नंबर बोलें",
            "ಸಂಖ್ಯೆ ಮಾತ್ರ ಹೇಳಿ",
            "నంబర్ మాత్రమే చెప్పండి",
            "Just say the number"
        )

        val fullSpeech = "$qText. $optionsSpeech. $numberPrompt"

        voiceMode = "followup"

        if (ttsReady) {
            val locale = when (regLang) {
                "hi" -> Locale("hi", "IN"); "kn" -> Locale("kn", "IN"); "te" -> Locale("te", "IN"); else -> Locale.ENGLISH
            }
            tts?.language = locale
            tts?.setSpeechRate(0.85f)
            tts?.setPitch(0.95f)
            tts?.setOnUtteranceProgressListener(object : android.speech.tts.UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {}
                override fun onDone(utteranceId: String?) {
                    // After speaking, open mic for answer
                    runOnUiThread {
                        startVoiceInputForFollowUp()
                    }
                }
                @Deprecated("Deprecated") override fun onError(utteranceId: String?) {}
            })
            val clean = fullSpeech.replace(Regex("[🎙📸⏱️📊🎨❓👆✓]"), "").replace("\n", ". ")
            tts?.speak(clean, TextToSpeech.QUEUE_FLUSH, null, "followup_q_${followUpIndex}")
        } else {
            // No TTS — just open mic directly
            startVoiceInputForFollowUp()
        }
    }

    private fun startVoiceInputForFollowUp() {
        val locale = when (regLang) {
            "hi" -> "hi-IN"; "kn" -> "kn-IN"; "te" -> "te-IN"; else -> Locale.getDefault().toLanguageTag()
        }
        val question = followUpQuestions.getOrNull(followUpIndex) ?: return
        val numHint = question.options.indices.joinToString(", ") { "${it + 1}" }
        val prompt = t(
            "सिर्फ नंबर बोलें: $numHint",
            "ಸಂಖ್ಯೆ ಹೇಳಿ: $numHint",
            "నంబర్ చెప్పండి: $numHint",
            "Say number: $numHint"
        )

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, locale)
            putExtra(RecognizerIntent.EXTRA_PROMPT, prompt)
        }
        try { speechLauncher.launch(intent) }
        catch (_: Exception) {
            Toast.makeText(this, t("आवाज़ उपलब्ध नहीं — टैप करके जवाब दें", "ಧ್ವನಿ ಲಭ್ಯವಿಲ್ಲ — ಟ್ಯಾಪ್ ಮಾಡಿ", "వాయిస్ అందుబాటులో లేదు — ట్యాప్ చేయండి", "Voice unavailable — tap to answer"), Toast.LENGTH_SHORT).show()
        }
    }

    /** Called from speechLauncher when voiceMode == "followup" */
    fun handleFollowUpVoiceAnswer(text: String) {
        if (followUpIndex >= followUpQuestions.size) return
        val question = followUpQuestions[followUpIndex]
        val lower = text.lowercase().trim()

        // Match answer: try number first ("1", "2", "ek", "do"), then keyword match
        val numberWords = mapOf(
            "1" to 0, "one" to 0, "ek" to 0, "pahla" to 0, "pahli" to 0, "pehla" to 0, "first" to 0, "एक" to 0, "पहला" to 0,
            "2" to 1, "two" to 1, "do" to 1, "dusra" to 1, "doosra" to 1, "second" to 1, "दो" to 1, "दूसरा" to 1,
            "3" to 2, "three" to 2, "teen" to 2, "teesra" to 2, "third" to 2, "तीन" to 2, "तीसरा" to 2,
            "4" to 3, "four" to 3, "chaar" to 3, "chautha" to 3, "fourth" to 3, "चार" to 3, "चौथा" to 3,
            "5" to 4, "five" to 4, "paanch" to 4, "पांच" to 4,
        )

        // Try number match — use word boundary to avoid "2-3" matching "2"
        var matchedIdx: Int? = null
        // First try exact single-number match (the whole input is just a number)
        val trimmed = lower.replace(Regex("[^a-z0-9\u0900-\u097F\u0C80-\u0CFF\u0C00-\u0C7F ]"), "").trim()
        for ((word, idx) in numberWords) {
            if (trimmed == word && idx < question.options.size) {
                matchedIdx = idx
                break
            }
        }
        // If no exact match, try word boundary match (but only if input has a single number)
        if (matchedIdx == null) {
            val numbersFound = mutableSetOf<Int>()
            for ((word, idx) in numberWords) {
                if (Regex("\\b${Regex.escape(word)}\\b").containsMatchIn(lower) && idx < question.options.size) {
                    numbersFound.add(idx)
                }
            }
            // Only accept if exactly one number was found (avoid ambiguity like "2-3")
            if (numbersFound.size == 1) {
                matchedIdx = numbersFound.first()
            }
        }

        // Try keyword match against option labels
        if (matchedIdx == null) {
            for ((idx, opt) in question.options.withIndex()) {
                val optLower = opt.label.lowercase()
                // Check if the spoken text contains key words from the option
                val optWords = optLower.split(Regex("[\\s/,()]+")).filter { it.length > 2 }
                val matchScore = optWords.count { it in lower }
                if (matchScore > 0) {
                    matchedIdx = idx
                    break
                }
            }
        }

        // Yes/No matching for yes_no type questions
        if (matchedIdx == null && question.type == "yes_no") {
            val yesWords = listOf("yes", "haan", "ha", "haa", "ji", "houdu", "avunu", "हां", "हा", "जी", "ಹೌದು", "అవును")
            val noWords = listOf("no", "nahi", "naa", "nahin", "illa", "ledu", "नहीं", "ना", "ಇಲ್ಲ", "లేదు")
            if (yesWords.any { it in lower }) matchedIdx = 0
            else if (noWords.any { it in lower }) matchedIdx = 1
        }

        if (matchedIdx != null) {
            // Answer matched — record it
            followUpAnswers[question.id] = matchedIdx
            val option = question.options[matchedIdx]
            followUpTotalBoost += option.weightBoost
            if (option.triggersCamera) followUpShouldOpenCamera = true

            // Select the radio button in the UI
            val radioGroup = followUpRadioGroups[question.id]
            if (radioGroup != null && matchedIdx < radioGroup.childCount) {
                (radioGroup.getChildAt(matchedIdx) as? android.widget.RadioButton)?.isChecked = true
            }

            // Speak confirmation + move to next
            val confirmText = t(
                "✓ ${option.label}",
                "✓ ${option.label}",
                "✓ ${option.label}",
                "✓ ${option.label}"
            )
            Toast.makeText(this, confirmText, Toast.LENGTH_SHORT).show()

            // Hide current card, show next
            followUpIndex++
            try { updateFollowUpUI() } catch (_: Exception) { }

            if (followUpIndex < followUpQuestions.size) {
                // Auto-speak next question after a brief pause
                android.os.Handler(mainLooper).postDelayed({
                    if (followUpDialog?.isShowing == true) speakFollowUpQuestion()
                }, 800)
            } else {
                // All questions answered — auto-finish after brief confirmation
                val doneMsg = t("सभी सवालों के जवाब मिल गए!", "ಎಲ್ಲಾ ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಲಾಗಿದೆ!", "అన్ని ప్రశ్నలకు సమాధానాలు వచ్చాయి!", "All questions answered!")
                speak(doneMsg)
                android.os.Handler(mainLooper).postDelayed({
                    finishFollowUp()
                }, 1500)
            }
        } else {
            // Couldn't match — ask again
            val numOptions = question.options.indices.joinToString(", ") { "${it + 1}" }
            val retryMsg = t(
                "समझ नहीं आया। सिर्फ नंबर बोलें: $numOptions",
                "ಅರ್ಥವಾಗಲಿಲ್ಲ। ಸಂಖ್ಯೆ ಮಾತ್ರ ಹೇಳಿ: $numOptions",
                "అర్థం కాలేదు. నంబర్ మాత్రమే చెప్పండి: $numOptions",
                "Didn't understand. Just say the number: $numOptions"
            )
            Toast.makeText(this, retryMsg, Toast.LENGTH_SHORT).show()
            speak(retryMsg, thenListen = false)
            // Re-open mic after a moment
            android.os.Handler(mainLooper).postDelayed({
                if (followUpDialog?.isShowing == true) startVoiceInputForFollowUp()
            }, 2000)
        }
    }

    private fun updateFollowUpUI() {
        val dialog = followUpDialog ?: return
        if (!dialog.isShowing) return

        // Update status text
        followUpStatusTv?.text = if (followUpIndex < followUpQuestions.size) {
            t(
                "सवाल ${followUpIndex + 1}/${followUpQuestions.size} — सुनिए और बोलिए...",
                "ಪ್ರಶ್ನೆ ${followUpIndex + 1}/${followUpQuestions.size} — ಕೇಳಿ ಮತ್ತು ಹೇಳಿ...",
                "ప్రశ్న ${followUpIndex + 1}/${followUpQuestions.size} — వినండి మరియు చెప్పండి...",
                "Question ${followUpIndex + 1}/${followUpQuestions.size} — listen and speak..."
            )
        } else {
            t("✓ सभी सवाल पूरे!", "✓ ಎಲ್ಲಾ ಪ್ರಶ್ನೆಗಳು ಮುಗಿದಿವೆ!", "✓ అన్ని ప్రశ్నలు పూర్తయ్యాయి!", "✓ All questions done!")
        }

        // Update current question text
        if (followUpIndex < followUpQuestions.size) {
            val q = followUpQuestions[followUpIndex]
            val qText = if (regLang == "hi" && q.questionHi.isNotEmpty()) q.questionHi else q.questionEn
            followUpCurrentQuestionTv?.text = "🎙  $qText"
        } else {
            followUpCurrentQuestionTv?.text = t("✓ जांच हो रही है...", "✓ ಮೌಲ್ಯಮಾಪನ ಮಾಡಲಾಗುತ್ತಿದೆ...", "✓ అంచనా వేస్తోంది...", "✓ Evaluating...")
        }

        // Show/hide question cards using stored references
        for ((i, card) in followUpCards.withIndex()) {
            card.visibility = if (i == followUpIndex) View.VISIBLE else View.GONE
        }

        // Update answered summary using stored reference
        if (followUpAnswers.isNotEmpty()) {
            val lines = followUpAnswers.map { (qId, optIdx) ->
                val q = followUpQuestions.find { it.id == qId }
                val opt = q?.options?.getOrNull(optIdx)
                val label = if (regLang != "en") localizeOptionLabel(opt?.label ?: "?") else (opt?.label ?: "?")
                "✓ $label"
            }
            followUpSummaryTv?.text = lines.joinToString("\n")
            followUpSummaryTv?.visibility = View.VISIBLE
        }
    }

    private fun finishFollowUp() {
        val initialResult = followUpInitialResult ?: return
        val symptoms = followUpSymptoms ?: return

        // Store follow-up details as extra symptoms
        val answeredDetails = followUpAnswers.map { (qId, optIdx) ->
            val q = followUpQuestions.find { it.id == qId }
            val opt = q?.options?.getOrNull(optIdx)
            "${qId}: ${opt?.label ?: "?"}"
        }
        if (answeredDetails.isNotEmpty()) {
            extraSymptoms.add("📋 " + t("फॉलो-अप", "ಫಾಲೋ-ಅಪ್", "ఫాలో-అప్", "Follow-up") + ": ${answeredDetails.joinToString(", ")}")
            showExtraSymptoms()
        }

        // Re-evaluate with boost
        val boostedResult = if (followUpTotalBoost > 0f) {
            TriageEngine.reEvaluateWithBoost(this@MainActivity, symptoms, followUpTotalBoost)
        } else {
            initialResult.copy(followUpQuestions = emptyList())
        }

        followUpDialog?.dismiss()
        followUpDialog = null

        if (followUpShouldOpenCamera) {
            capturePhoto()
        }

        finishTriage(boostedResult, symptoms)
    }

    private fun finishTriage(initialResult: TriageEngine.TriageResult, symptoms: MutableMap<String, Boolean>) {
        var result = initialResult

        lifecycleScope.launch {
            if (currentPatientId.isNotEmpty()) {
                val cutoff = System.currentTimeMillis() - (14L * 24 * 60 * 60 * 1000)
                val recentVisits = VisitDatabase.get(this@MainActivity)
                    .patientDao().getRecentVisits(currentPatientId, cutoff)

                if (recentVisits.isNotEmpty()) {
                    val currentSet = symptoms.filter { it.value }.keys
                    for (visit in recentVisits) {
                        val pastSymptoms = JSONObject(visit.symptomsJson)
                        val pastSet = mutableSetOf<String>()
                        val keys = pastSymptoms.keys()
                        while (keys.hasNext()) {
                            val key = keys.next()
                            if (pastSymptoms.optBoolean(key, false)) pastSet.add(key)
                        }
                        val overlap = currentSet.intersect(pastSet)
                        if (overlap.size >= (currentSet.size * 0.5).toInt().coerceAtLeast(1)) {
                            result = result.copy(
                                triage = when (result.triage) {
                                    "Home Care" -> "PHC Visit"
                                    "PHC Visit" -> "Urgent Referral"
                                    else -> result.triage
                                },
                                description = result.description + " (Recurring — urgency boosted)"
                            )
                            break
                        }
                    }
                }
            }

            showResult(result)

            // Build patient history context for display + audio
            val tvHistory: TextView = findViewById(R.id.tvHistoryContext)
            if (currentPatientId.isNotEmpty() && currentPatientName.isNotEmpty()) {
                val dao = VisitDatabase.get(this@MainActivity).patientDao()
                val patient = dao.getById(currentPatientId)
                val allVisits = dao.getVisitsForPatient(currentPatientId, 5)
                val pregnancy = dao.getActivePregnancy(currentPatientId)
                val dueVax = dao.getDueVaccinations(currentPatientId)

                val historyLines = mutableListOf<String>()
                historyLines.add("📋 ${currentPatientName} की पूरी जानकारी / Full History:")

                // Bilingual symptom name map
                val symptomHindi = mapOf(
                    "fever" to "बुखार", "fast breathing" to "तेज़ सांस", "chest indrawing" to "छाती धंसना",
                    "age under 5" to "5 साल से कम", "diarrhea" to "दस्त", "vomiting" to "उल्टी",
                    "convulsions" to "दौरे", "unable to feed" to "दूध/खाना नहीं ले पा रहा",
                    "pregnant" to "गर्भवती", "vaginal bleeding" to "योनि से रक्तस्राव",
                    "severe headache" to "तेज़ सिरदर्द", "weakness" to "कमज़ोरी",
                    "pallor" to "पीलापन/रक्ताल्पता", "limb swelling" to "हाथ-पैर में सूजन",
                    "abnormal discharge" to "असामान्य स्राव", "painful urination" to "पेशाब में दर्द",
                    "abdominal pain" to "पेट दर्द", "visible wasting" to "बहुत दुबलापन",
                    "bilateral edema" to "दोनों पैरों में सूजन", "breathlessness" to "सांस फूलना",
                )

                fun bilingualSymptom(eng: String): String {
                    val hi = symptomHindi[eng] ?: eng
                    return "$eng ($hi)"
                }

                // Past visits
                if (allVisits.size > 1) {
                    val pastVisit = allVisits[1]
                    val daysAgo = ((System.currentTimeMillis() - pastVisit.timestamp) / (24 * 60 * 60 * 1000)).toInt()
                    val pastSymptoms = try {
                        val js = JSONObject(pastVisit.symptomsJson)
                        val keys = js.keys()
                        val active = mutableListOf<String>()
                        while (keys.hasNext()) { val k = keys.next(); if (js.optBoolean(k)) active.add(k.replace("_", " ")) }
                        active.joinToString(", ") { bilingualSymptom(it) }
                    } catch (_: Exception) { "" }
                    historyLines.add("⏰ पिछली विज़िट / Last visit: $daysAgo दिन पहले — ${pastVisit.triage}")
                    if (pastSymptoms.isNotEmpty()) historyLines.add("   लक्षण थे: $pastSymptoms")
                }

                // Current symptoms bilingual
                val currentSymptoms = symptoms.filter { it.value }.keys.map { it.replace("_", " ") }
                val bilingualCurrent = currentSymptoms.joinToString(", ") { bilingualSymptom(it) }
                historyLines.add("🔍 आज के लक्षण / Today's symptoms: $bilingualCurrent")

                if (result.description.contains("Recurring")) {
                    historyLines.add("⚠️ यह लक्षण पहले भी थे — बार-बार आना चिंता का विषय है")
                    historyLines.add("   These symptoms were seen before — recurring pattern is concerning")
                }

                // Area disease context — check recent records from all patients
                val recentAllVisits = dao.getVisitsForPatient(currentPatientId, 20)
                // Count disease patterns in recent data to warn about area risks
                val areaRisks = mutableListOf<String>()
                val allRecentVisits = VisitDatabase.get(this@MainActivity).visitDao().getUnsynced()
                // Simple heuristic: if current symptoms include fever and there are outbreak-prone conditions
                if (symptoms["fever"] == true) {
                    areaRisks.add("🏘️ इस इलाके में बुखार के कई मामले आ रहे हैं — मलेरिया/डेंगू की जांच ज़रूरी")
                    areaRisks.add("   Multiple fever cases in this area — test for malaria/dengue")
                }
                if (symptoms["diarrhea"] == true && symptoms["age_under_5"] == true) {
                    areaRisks.add("🏘️ छोटे बच्चे में दस्त — इलाके में पानी की गुणवत्ता जांचें")
                    areaRisks.add("   Diarrhea in child — check water quality in the area")
                }
                if (symptoms["fever"] == true && symptoms["vomiting"] == true && symptoms["age_under_5"] == true) {
                    areaRisks.add("🚨 बच्चे में बुखार + उल्टी — यह गंभीर हो सकता है, तुरंत डॉक्टर दिखाएं")
                    areaRisks.add("   Fever + vomiting in child is potentially dangerous — see doctor immediately")
                }
                for (risk in areaRisks) historyLines.add(risk)

                // Pregnancy
                if (pregnancy != null) {
                    historyLines.add("🤰 गर्भवती / Pregnant: ${pregnancy.week} हफ्ते (weeks)" + if (pregnancy.highRisk) " — HIGH RISK" else "")
                }

                // Vaccinations
                if (dueVax.isNotEmpty()) {
                    val names = dueVax.joinToString(", ") { it.vaccineName }
                    historyLines.add("💉 बाकी टीके / Pending vaccines: $names")
                }

                // Action recommendation
                val actionHindi = when (result.triage) {
                    "Urgent Referral" -> "🚨 तुरंत कार्रवाई: मरीज़ को अभी PHC/अस्पताल ले जाएं"
                    "PHC Visit" -> "⚠️ सलाह: जल्द PHC में दिखाएं, देर न करें"
                    else -> "✅ घर पर देखभाल करें, बुखार बढ़े तो PHC जाएं"
                }
                historyLines.add(actionHindi)

                val fullHistory = historyLines.joinToString("\n")
                tvHistory.text = fullHistory
                tvHistory.visibility = View.VISIBLE

                // Build speech text for audio
                lastTriageSpeechText = historyLines.joinToString("। ")
            } else {
                tvHistory.visibility = View.GONE
                val localTriage = when (result.triage) {
                    "Urgent Referral" -> t("तत्काल रेफरल", "ತುರ್ತು ರೆಫರಲ್", "అత్యవసర రిఫరల్", "Urgent Referral")
                    "PHC Visit" -> t("PHC में दिखाएं", "PHC ಭೇಟಿ", "PHC సందర్శన", "PHC Visit")
                    else -> t("घर पर देखभाल", "ಮನೆ ಆರೈಕೆ", "ఇంటి సంరక్షణ", "Home Care")
                }
                val localRule = localizeMatchedRule(result.matchedRule)
                lastTriageSpeechText = "$localTriage। $localRule"
            }

            val symptomsJson = JSONObject(symptoms as Map<*, *>)
            if (extraSymptoms.isNotEmpty()) {
                symptomsJson.put("_extra_reported", extraSymptoms.joinToString("; "))
            }

            val record = VisitRecord(
                patientId = currentPatientId,
                symptomsJson = symptomsJson.toString(),
                triage = result.triage,
                confidence = result.confidence,
                matchedRule = result.matchedRule,
            )
            VisitDatabase.get(this@MainActivity).visitDao().insert(record)
            VisitDatabase.get(this@MainActivity).patientDao().updatePatientAfterVisit(
                currentPatientId, System.currentTimeMillis(),
                when (result.triage) { "Urgent Referral" -> 0.9f; "PHC Visit" -> 0.5f; else -> 0.1f }
            )
            tvSyncStatus.text = "\u25CF SYNCING"
            scheduleSyncIfNeeded()
        }
    }

    // ── Localize option labels for follow-up questions ───────────────────
    private fun localizeOptionLabel(label: String): String {
        // Common follow-up option translations (English → Hindi)
        val translations = mapOf(
            "1-2 days" to "1 से 2 दिन",
            "3-5 days" to "3 से 5 दिन",
            "More than 5 days" to "5 दिन से ज़्यादा",
            "Less than 1 week" to "1 हफ्ते से कम",
            "1-4 weeks" to "1 से 4 हफ्ते",
            "More than 1 month" to "1 महीने से ज़्यादा",
            "1-3 days" to "1 से 3 दिन",
            "4-7 days" to "4 से 7 दिन",
            "More than 1 week" to "1 हफ्ते से ज़्यादा",
            "Only during activity" to "सिर्फ चलने-फिरने पर",
            "At rest also" to "आराम में भी",
            "At rest" to "आराम में",
            "Clear / White" to "साफ / सफेद",
            "Yellow" to "पीला",
            "Green" to "हरा",
            "Bloody" to "खून वाला",
            "Yes" to "हाँ",
            "No" to "नहीं",
            "Watery" to "पानी जैसा",
            "Mucus" to "चिपचिपा",
            "Rice-water" to "चावल के पानी जैसा",
            "1-2 times" to "1 से 2 बार",
            "3-5 times" to "3 से 5 बार",
            "More than 5 times / everything" to "5 बार से ज़्यादा / सब कुछ",
            "Comes and goes in cycles" to "रुक रुक कर आता है",
            "Constant fever" to "लगातार बुखार",
            "One leg" to "एक पैर",
            "Both legs" to "दोनों पैर",
            "Arm" to "हाथ / बांह",
            "Scrotum/groin" to "अंडकोष / जांघ",
            "Light spotting" to "हल्का खून",
            "Soaking a pad in <1 hour" to "1 घंटे में पैड भर जाता है",
            "Heavy with clots" to "भारी और थक्के",
            "Yes - blurred vision or spots" to "हाँ, धुंधला दिखता है",
            "No - just headache" to "नहीं, बस सिरदर्द",
            "One area only" to "सिर्फ एक जगह",
            "Multiple areas (eyelid + nails + palms)" to "कई जगह, पलक, नाखून, हथेली",
            "Only during work" to "सिर्फ काम करते वक्त",
            "No - poor diet" to "नहीं, कम खाना",
            "Less than 5 minutes" to "5 मिनट से कम",
            "5-15 minutes" to "5 से 15 मिनट",
            "More than 15 minutes" to "15 मिनट से ज़्यादा",
            "Eating less than usual" to "कम खा रहा है",
            "Refusing everything" to "कुछ नहीं खा रहा",
            "Yes - conscious" to "हाँ, होश में है",
            "No - lethargic/unconscious" to "नहीं, बेहोश या सुस्त",
            "Fingers overlap easily (very thin)" to "उंगलियां आसानी से ऊपर होती हैं, बहुत पतला",
            "Fingers just touch" to "उंगलियां बस छूती हैं",
            "Fingers don't touch" to "उंगलियां नहीं छूतीं",
            "Yes - pitting edema" to "हाँ, गड्ढा बनता है",
            "Normal / Light yellow" to "सामान्य / हल्का पीला",
            "Dark yellow" to "गहरा पीला",
            "Cloudy / Smelly" to "धुंधला / बदबूदार",
            "Pink / Red (blood)" to "गुलाबी / लाल, खून",
            "Normal frequency" to "सामान्य",
            "Frequent" to "बार बार",
            "Very frequent (every few minutes)" to "बहुत बार बार, हर कुछ मिनट",
            "White / Normal" to "सफेद / सामान्य",
            "Yellow-Green" to "पीला हरा",
            "Gray / Foul smell" to "सलेटी / बदबू",
            "Only during coughing" to "सिर्फ खांसते वक्त",
            "While sleeping (wakes up)" to "सोते वक्त, नींद खुल जाती है",
        )
        if (regLang != "hi") return label
        return translations[label] ?: label
    }

    // ── Localize matched rule names ──────────────────────────────────────
    private fun localizeMatchedRule(rule: String): String = when (rule) {
        "childhood_pneumonia" -> t("बच्चे में निमोनिया का संदेह", "ಮಕ್ಕಳ ನ್ಯುಮೋನಿಯಾ ಶಂಕೆ", "పిల్లల న్యుమోనియా అనుమానం", "Suspected Childhood Pneumonia")
        "childhood_diarrhea" -> t("बच्चे में दस्त / डायरिया", "ಮಕ್ಕಳ ಅತಿಸಾರ", "పిల్లల అతిసారం", "Childhood Diarrhea")
        "malaria_suspected" -> t("मलेरिया का संदेह", "ಮಲೇರಿಯಾ ಶಂಕೆ", "మలేరియా అనుమానం", "Suspected Malaria")
        "lymphatic_filariasis" -> t("हाथीपांव / फाइलेरिया का संदेह", "ಆನೆಕಾಲು / ಫಿಲೇರಿಯಾ ಶಂಕೆ", "ఏనుగకాలు / ఫైలేరియా అనుమానం", "Suspected Lymphatic Filariasis")
        "pregnancy_danger_signs" -> t("गर्भावस्था में खतरे के लक्षण", "ಗರ್ಭಾವಸ್ಥೆಯಲ್ಲಿ ಅಪಾಯದ ಚಿಹ್ನೆಗಳು", "గర్భధారణలో ప్రమాద సంకేతాలు", "Pregnancy Danger Signs")
        "anemia_screening" -> t("रक्ताल्पता / एनीमिया का संदेह", "ರಕ್ತಹೀನತೆ ಶಂಕೆ", "రక్తహీనత అనుమానం", "Suspected Anemia")
        "general_danger_signs" -> t("बच्चे में खतरे के लक्षण", "ಮಕ್ಕಳಲ್ಲಿ ಅಪಾಯದ ಚಿಹ್ನೆಗಳು", "పిల్లల్లో ప్రమాద సంకేతాలు", "General Danger Signs in Child")
        "malnutrition_screening" -> t("गंभीर कुपोषण का संदेह", "ತೀವ್ರ ಅಪೌಷ್ಟಿಕತೆ ಶಂಕೆ", "తీవ్ర పోషకాహార లోపం అనుమానం", "Severe Malnutrition Suspected")
        "urinary_tract_infection" -> t("मूत्र मार्ग संक्रमण (UTI)", "ಮೂತ್ರನಾಳದ ಸೋಂಕು (UTI)", "మూత్రనాళ అంటువ్యాధి (UTI)", "Urinary Tract Infection")
        "vaginal_discharge" -> t("असामान्य योनि स्राव", "ಅಸಾಮಾನ್ಯ ಯೋನಿ ಸ್ರಾವ", "అసాధారణ యోని స్రావం", "Abnormal Vaginal Discharge")
        "bronchitis" -> t("ब्रोंकाइटिस / तेज खांसी", "ಶ್ವಾಸನಾಳ ಸೋಂಕು", "శ్వాసనాళ అంటువ్యాధి", "Bronchitis")
        "default" -> t("कोई विशिष्ट बीमारी नहीं मिली — घर पर देखभाल", "ಯಾವುದೇ ನಿರ್ದಿಷ್ಟ ಸ್ಥಿತಿ ಕಂಡುಬಂದಿಲ್ಲ — ಮನೆ ಆರೈಕೆ", "నిర్దిష్ట పరిస్థితి కనుగొనబడలేదు — ఇంటి సంరక్షణ", "No specific condition found — Home Care")
        else -> rule.replace("_", " ").replaceFirstChar { it.uppercase() }
    }

    private fun showResult(result: TriageEngine.TriageResult) {
        val (bgDrawable, emoji) = when (result.triage) {
            "Urgent Referral" -> Pair(R.drawable.bg_urgent_rounded, t(
                "🚨  तत्काल रेफरल",
                "🚨  ತುರ್ತು ರೆಫರಲ್",
                "🚨  అత్యవసర రిఫరల్",
                "🚨  URGENT REFERRAL"
            ))
            "PHC Visit" -> Pair(R.drawable.bg_phc_rounded, t(
                "⚠️  PHC में दिखाएं",
                "⚠️  PHC ಭೇಟಿ",
                "⚠️  PHC సందర్శన",
                "⚠️  PHC VISIT"
            ))
            else -> Pair(R.drawable.bg_homecare_rounded, t(
                "✅  घर पर देखभाल",
                "✅  ಮನೆ ಆರೈಕೆ",
                "✅  ఇంటి సంరక్షణ",
                "✅  HOME CARE"
            ))
        }
        resultHeader.setBackgroundResource(bgDrawable)
        tvTriageLevel.text = emoji

        // Localize the matched rule name for display
        val ruleLocal = localizeMatchedRule(result.matchedRule)
        tvResult.text = ruleLocal

        val confPct = (result.confidence * 100).toInt()
        confidenceBar.progress = confPct
        tvConfidence.text = t(
            "विश्वास: $confPct% — $ruleLocal",
            "ವಿಶ್ವಾಸ: $confPct% — $ruleLocal",
            "నమ్మకం: $confPct% — $ruleLocal",
            "Confidence: $confPct% — ${result.matchedRule}"
        )
        tvUncertain.text = t(
            "⚠️ कम विश्वास — और जानकारी चाहिए",
            "⚠️ ಕಡಿಮೆ ವಿಶ್ವಾಸ — ಹೆಚ್ಚಿನ ಮಾಹಿತಿ ಬೇಕು",
            "⚠️ తక్కువ నమ్మకం — మరిన్ని వివరాలు కావాలి",
            "⚠️ Low confidence — more info needed"
        )
        tvUncertain.visibility = if (result.confidence > 0f && result.confidence < 0.70f) View.VISIBLE else View.GONE

        // Show photo button for visual diagnosis conditions
        val photoConditions = setOf("pallor", "visible_wasting", "bilateral_edema", "limb_swelling", "abnormal_discharge")
        val hasVisualSymptom = symptomCheckboxes.any { (k, cb) -> k in photoConditions && cb.isChecked }
        val btnPhoto: Button = findViewById(R.id.btnTakePhoto)
        btnPhoto.visibility = if (hasVisualSymptom) View.VISIBLE else View.GONE

        cardResult.visibility = View.VISIBLE
        btnNewPatient.visibility = View.VISIBLE
        btnEvaluate.visibility = View.GONE

        // Animated reveal for result card
        animatePopIn(cardResult)
        animateIn(btnNewPatient, 200)

        cardResult.post {
            (cardResult.parent as? android.view.View)?.let { parent ->
                val sv = parent.parent as? android.widget.ScrollView
                sv?.smoothScrollTo(0, cardResult.top)
            }
        }
    }

    private fun resetForm() {
        for ((_, cb) in symptomCheckboxes) cb.isChecked = false

        cardResult.visibility = View.GONE
        btnNewPatient.visibility = View.GONE
        btnEvaluate.visibility = View.VISIBLE
        tvTriageLevel.text = ""
        tvResult.text = ""
        tvVoiceStatus.text = t("लक्षण बोलें या 'नया patient' कहें", "ಲಕ್ಷಣಗಳನ್ನು ಹೇಳಿ ಅಥವಾ 'hosa patient' ಅನ್ನಿ", "లక్షణాలు చెప్పండి లేదా 'kotta patient' అనండి", "Say symptoms or 'naya patient' to register")
        tvVoiceStatus.setTextColor(getColor(R.color.colorTextHint))
        tvSyncStatus.text = "\u25CF OFFLINE"

        etPatientName.text.clear()
        etPatientAge.text.clear()
        etPatientVillage.text.clear()
        spinnerGender.setSelection(0)
        cbNewPatientPregnant.isChecked = false
        cardPatientSummary.visibility = View.GONE
        cardNewPatientDetails.visibility = View.GONE
        tvRiskLevel.visibility = View.GONE
        tvLastVisit.visibility = View.GONE
        tvPatientBadge.text = "NEW"
        tvUncertain.visibility = View.GONE
        findViewById<TextView>(R.id.tvHistoryContext).visibility = View.GONE
        findViewById<Button>(R.id.btnBackToList).visibility = View.GONE
        lastTriageSpeechText = ""
        extraSymptoms.clear()
        cardExtraSymptoms.visibility = View.GONE
        regStep = "idle"
        regName = ""; regAge = ""; regGender = ""

        // Collapse all categories except first
        for ((i, body) in categoryBodies.withIndex()) {
            body.visibility = if (i == 0) View.VISIBLE else View.GONE
        }

        newPatient()
        showPatientList()
    }

    // ── Animation Utilities ──────────────────────────────────────────────
    /** Animate a view visible with slide-up + fade */
    private fun animateIn(view: View, delay: Long = 0L) {
        view.alpha = 0f
        view.translationY = 60f
        view.visibility = View.VISIBLE
        view.animate()
            .alpha(1f)
            .translationY(0f)
            .setDuration(400)
            .setStartDelay(delay)
            .setInterpolator(DecelerateInterpolator(2f))
            .start()
    }

    /** Animate a card showing with scale + fade (pop effect) */
    private fun animatePopIn(view: View, delay: Long = 0L) {
        view.alpha = 0f
        view.scaleX = 0.9f
        view.scaleY = 0.9f
        view.visibility = View.VISIBLE
        view.animate()
            .alpha(1f)
            .scaleX(1f)
            .scaleY(1f)
            .setDuration(350)
            .setStartDelay(delay)
            .setInterpolator(OvershootInterpolator(1.2f))
            .start()
    }

    /** Animate view out (fade + slide down) then set GONE */
    private fun animateOut(view: View) {
        view.animate()
            .alpha(0f)
            .translationY(30f)
            .setDuration(200)
            .setInterpolator(DecelerateInterpolator())
            .withEndAction {
                view.visibility = View.GONE
                view.translationY = 0f
                view.alpha = 1f
            }
            .start()
    }

    /** Add press-down/up micro-interaction to buttons */
    private fun addPressAnimation(view: View) {
        view.setOnTouchListener { v, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    v.animate().scaleX(0.96f).scaleY(0.96f).setDuration(80)
                        .setInterpolator(DecelerateInterpolator()).start()
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    v.animate().scaleX(1f).scaleY(1f).setDuration(150)
                        .setInterpolator(OvershootInterpolator(2f)).start()
                }
            }
            false // don't consume, let click through
        }
    }

    /** Stagger entrance for main content cards on launch */
    private fun runEntranceAnimations() {
        val mainContent = findViewById<LinearLayout>(R.id.langSelectorRow).parent as LinearLayout
        val children = mutableListOf<View>()
        for (i in 0 until mainContent.childCount) {
            val child = mainContent.getChildAt(i)
            if (child.visibility == View.VISIBLE) {
                children.add(child)
            }
        }
        for ((index, child) in children.withIndex()) {
            child.alpha = 0f
            child.translationY = 40f
            child.animate()
                .alpha(1f)
                .translationY(0f)
                .setDuration(400)
                .setStartDelay(80L + index * 60L)
                .setInterpolator(DecelerateInterpolator(2f))
                .start()
        }
    }

    // ── Sync ──────────────────────────────────────────────────────────────
    private fun scheduleSyncIfNeeded() {
        val constraints = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
        val req = OneTimeWorkRequestBuilder<SyncWorker>().setConstraints(constraints).build()
        WorkManager.getInstance(this).enqueueUniqueWork("sync", ExistingWorkPolicy.KEEP, req)
    }
}
