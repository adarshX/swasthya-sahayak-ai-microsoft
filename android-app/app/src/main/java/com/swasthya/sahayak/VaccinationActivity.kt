package com.swasthya.sahayak

import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.View
import android.view.animation.DecelerateInterpolator
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import java.util.UUID

/**
 * Vaccination Tracker — India National Immunisation Schedule (RCH 2024).
 * Shows per-patient vaccination status: done / due / overdue / not yet.
 */
class VaccinationActivity : AppCompatActivity() {

    // India NIS schedule: (vaccine name, age description, due_at_months)
    private val SCHEDULE = listOf(
        Triple("BCG", "Birth", 0),
        Triple("OPV-0", "Birth", 0),
        Triple("HepB Birth Dose", "Birth", 0),
        Triple("OPV-1", "6 Weeks", 1),
        Triple("Pentavalent-1", "6 Weeks", 1),
        Triple("PCV-1", "6 Weeks", 1),
        Triple("RVV-1", "6 Weeks", 1),
        Triple("OPV-2", "10 Weeks", 2),
        Triple("Pentavalent-2", "10 Weeks", 2),
        Triple("PCV-2", "10 Weeks", 2),
        Triple("RVV-2", "10 Weeks", 2),
        Triple("OPV-3", "14 Weeks", 3),
        Triple("Pentavalent-3", "14 Weeks", 3),
        Triple("PCV-3", "14 Weeks", 3),
        Triple("IPV", "14 Weeks", 3),
        Triple("MR-1", "9-12 Months", 9),
        Triple("JE-1", "9-12 Months", 9),
        Triple("Vitamin A (1st)", "9 Months", 9),
        Triple("DPT Booster-1", "16-24 Months", 16),
        Triple("OPV Booster", "16-24 Months", 16),
        Triple("MR-2", "16-24 Months", 16),
        Triple("JE-2", "16-24 Months", 16),
        Triple("Vitamin A (2nd)", "16 Months", 16),
        Triple("DPT Booster-2", "5-6 Years", 60),
    )

    private var currentPatientId: String = ""
    private var currentPatientName: String = ""
    private var patientAgeMonths: Int = 0
    private var lang: String = "en"

    private fun t(hi: String, kn: String, te: String, en: String): String = when (lang) {
        "hi" -> hi; "kn" -> kn; "te" -> te; else -> en
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        currentPatientId = intent.getStringExtra("patient_id") ?: ""
        currentPatientName = intent.getStringExtra("patient_name") ?: "Unknown"
        patientAgeMonths = intent.getIntExtra("age_months", 0)
        lang = intent.getStringExtra("lang") ?: "en"

        val dp = resources.displayMetrics.density

        val scroll = ScrollView(this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#F0F4FF"))
        }

        // Header with gradient
        val headerView = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val headerGradient = GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                intArrayOf(Color.parseColor("#0A3672"), Color.parseColor("#0D47A1"), Color.parseColor("#1565C0"))
            )
            background = headerGradient
            val padH = (20 * dp).toInt()
            setPadding(padH, (40 * dp).toInt(), padH, (22 * dp).toInt())

            // Back arrow + title row
            addView(LinearLayout(this@VaccinationActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = android.view.Gravity.CENTER_VERTICAL
                addView(TextView(this@VaccinationActivity).apply {
                    text = "←"
                    textSize = 22f
                    setTextColor(Color.WHITE)
                    setPadding(0, 0, (16 * dp).toInt(), 0)
                    setOnClickListener { finish() }
                })
                addView(TextView(this@VaccinationActivity).apply {
                    text = t("💉  टीकाकरण ट्रैकर", "💉  ಲಸಿಕೆ ಟ್ರ್ಯಾಕರ್", "💉  టీకా ట్రాకర్", "💉  Vaccination Tracker")
                    textSize = 21f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(Color.WHITE)
                })
            })
            addView(TextView(this@VaccinationActivity).apply {
                text = "$currentPatientName  ·  $patientAgeMonths months old"
                textSize = 13f
                setTextColor(Color.parseColor("#A8C8FF"))
                setPadding(0, (6 * dp).toInt(), 0, 0)
            })
        }
        root.addView(headerView)

        // Legend bar
        root.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            val padH = (16 * dp).toInt()
            val padV = (12 * dp).toInt()
            setPadding(padH, padV, padH, padV)
            gravity = android.view.Gravity.CENTER
            setBackgroundColor(Color.WHITE)
            addView(makeChip(t("✅ हो गया", "✅ ಮಾಡಲಾಗಿದೆ", "✅ చేయబడింది", "✅ Done"), "#2E7D32"))
            addView(makeChip(t("🟠 बाकी है", "🟠 ಬಾಕಿ", "🟠 పెండింగ్", "🟠 Due"), "#E65100"))
            addView(makeChip(t("🔴 देर हो गई", "🔴 ತಡವಾಗಿದೆ", "🔴 ఆలస్యం", "🔴 Overdue"), "#C62828"))
            addView(makeChip(t("— अभी नहीं", "— ಇನ್ನೂ ಇಲ್ಲ", "— ఇంకా కాదు", "— Not yet"), "#9EA4B8"))
        })

        // Vaccination list container with padding
        val listOuter = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (12 * dp).toInt()
            setPadding(pad, pad, pad, pad)
        }
        val listContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        listOuter.addView(listContainer)
        root.addView(listOuter)

        scroll.addView(root)
        setContentView(scroll)

        // Load vaccine status
        lifecycleScope.launch {
            val dao = VisitDatabase.get(this@VaccinationActivity).patientDao()
            val allVax = dao.getAllVaccinations(currentPatientId)
            val doneNames = allVax.filter { it.administeredAtMillis != null }.map { it.vaccineName }.toSet()

            for ((name, ageLabel, dueMonth) in SCHEDULE) {
                val isDone = doneNames.contains(name)
                val isDue = !isDone && patientAgeMonths >= dueMonth && patientAgeMonths < dueMonth + 3
                val isOverdue = !isDone && patientAgeMonths >= dueMonth + 3
                val notYet = !isDone && patientAgeMonths < dueMonth

                val status = when {
                    isDone -> "✅"
                    isOverdue -> "🔴"
                    isDue -> "🟠"
                    else -> "—"
                }
                val statusColor = when {
                    isDone -> "#2E7D32"
                    isOverdue -> "#C62828"
                    isDue -> "#E65100"
                    else -> "#9EA4B8"
                }
                val statusText = when {
                    isDone -> t("हो गया", "ಮಾಡಲಾಗಿದೆ", "చేయబడింది", "Done")
                    isOverdue -> t("देर हुई", "ತಡವಾಗಿದೆ", "ఆలస్యం", "OVERDUE")
                    isDue -> t("अभी दें", "ಈಗ ಕೊಡಿ", "ఇప్పుడు ఇవ్వండి", "DUE NOW")
                    else -> t("अभी नहीं", "ಇನ್ನೂ ಇಲ್ಲ", "ఇంకా కాదు", "Not yet")
                }

                val row = LinearLayout(this@VaccinationActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = android.view.Gravity.CENTER_VERTICAL
                    val padH = (16 * resources.displayMetrics.density).toInt()
                    val padV = (14 * resources.displayMetrics.density).toInt()
                    setPadding(padH, padV, padH, padV)
                    val params = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    )
                    params.bottomMargin = (4 * resources.displayMetrics.density).toInt()
                    layoutParams = params

                    // Rounded card background
                    val rowBg = GradientDrawable().apply {
                        cornerRadius = 12 * resources.displayMetrics.density
                        setColor(when {
                            isOverdue -> Color.parseColor("#FFF5F5")
                            isDue -> Color.parseColor("#FFF8E1")
                            isDone -> Color.parseColor("#F5FFF5")
                            else -> Color.WHITE
                        })
                    }
                    background = rowBg
                    elevation = 1 * resources.displayMetrics.density

                    // If due/overdue → tappable to mark as done
                    if (isDue || isOverdue) {
                        setOnClickListener { markAsDone(name, listContainer) }
                    }
                }

                row.addView(TextView(this@VaccinationActivity).apply {
                    text = status
                    textSize = 18f
                    setPadding(0, 0, (12 * resources.displayMetrics.density).toInt(), 0)
                })

                val textCol = LinearLayout(this@VaccinationActivity).apply {
                    orientation = LinearLayout.VERTICAL
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                }
                textCol.addView(TextView(this@VaccinationActivity).apply {
                    text = name
                    textSize = 15f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(Color.parseColor("#1A1F36"))
                })
                textCol.addView(TextView(this@VaccinationActivity).apply {
                    text = ageLabel
                    textSize = 12f
                    setTextColor(Color.parseColor("#5A6178"))
                })
                row.addView(textCol)

                row.addView(TextView(this@VaccinationActivity).apply {
                    text = statusText
                    textSize = 12f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(Color.parseColor(statusColor))
                })

                listContainer.addView(row)

                // Staggered entrance animation
                row.alpha = 0f
                row.translationY = 30f
                row.animate()
                    .alpha(1f)
                    .translationY(0f)
                    .setDuration(350)
                    .setStartDelay(50L * listContainer.childCount)
                    .setInterpolator(DecelerateInterpolator(2f))
                    .start()
            }
        }
    }

    private fun makeChip(text: String, color: String): TextView {
        return TextView(this).apply {
            this.text = text
            textSize = 11f
            setTextColor(Color.parseColor(color))
            setPadding(
                (8 * resources.displayMetrics.density).toInt(),
                (4 * resources.displayMetrics.density).toInt(),
                (8 * resources.displayMetrics.density).toInt(),
                (4 * resources.displayMetrics.density).toInt()
            )
        }
    }

    private fun markAsDone(vaccineName: String, container: LinearLayout) {
        val builder = android.app.AlertDialog.Builder(this)
        builder.setTitle(t("$vaccineName दे दिया?", "$vaccineName ಕೊಟ್ಟಿದ್ದೀರಾ?", "$vaccineName ఇచ్చారా?", "Mark $vaccineName as administered?"))
        builder.setMessage(t("आज का टीका दर्ज हो जाएगा।", "ಇಂದು ಲಸಿಕೆ ದಾಖಲಾಗುತ್ತದೆ।", "ఈరోజు టీకా నమోదవుతుంది.", "This will record the vaccine as given today."))
        builder.setPositiveButton(t("✓ दर्ज करें", "✓ ದಾಖಲಿಸಿ", "✓ నమోదు చేయండి", "✓ Mark Done")) { _, _ ->
            lifecycleScope.launch {
                val dao = VisitDatabase.get(this@VaccinationActivity).patientDao()
                dao.insertVaccination(Vaccination(
                    id = UUID.randomUUID().toString(),
                    patientId = currentPatientId,
                    vaccineName = vaccineName,
                    administeredAtMillis = System.currentTimeMillis(),
                    isDue = false,
                    isOverdue = false
                ))
                Toast.makeText(this@VaccinationActivity, t("$vaccineName दर्ज हो गया", "$vaccineName ದಾಖಲಾಗಿದೆ", "$vaccineName నమోదైంది", "$vaccineName marked as done"), Toast.LENGTH_SHORT).show()
                intent.putExtra("lang", lang)
                recreate()
            }
        }
        builder.setNegativeButton(t("रद्द करें", "ರದ್ದು", "రద్దు", "Cancel"), null)
        builder.show()
    }
}
