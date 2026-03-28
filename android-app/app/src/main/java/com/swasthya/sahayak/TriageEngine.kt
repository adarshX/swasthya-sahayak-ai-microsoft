package com.swasthya.sahayak

import android.content.Context
import org.json.JSONObject
import java.io.BufferedReader

/**
 * Offline protocol engine — weighted scoring with confidence.
 * Reads protocols.json (compiled from WHO-IMNCI YAML) from assets.
 * No network call. No ML model. Deterministic rule evaluation.
 *
 * Algorithm:
 *   1. Filter conditions by patient age and pregnancy status
 *   2. For each condition: calculate weighted score from matching triggers
 *   3. Apply risk modifiers from patient history flags
 *   4. Compare score against thresholds → triage tier
 *   5. confidence = rawScore / maxPossibleScore
 *   6. Return the most severe matching result
 */
object TriageEngine {

    data class FollowUpOption(
        val label: String,
        val weightBoost: Float,
        val triggersCamera: Boolean = false
    )

    data class FollowUpQuestion(
        val id: String,
        val triggerSymptom: String,
        val type: String,
        val questionEn: String,
        val questionHi: String,
        val options: List<FollowUpOption>
    )

    data class TriageResult(
        val triage: String,
        val matchedRule: String,
        val description: String,
        val confidence: Float = 0f,
        val rationale: String = "",
        val score: Float = 0f,
        val maxScore: Float = 0f,
        val followUpQuestions: List<FollowUpQuestion> = emptyList()
    )

    fun evaluate(context: Context, symptoms: Map<String, Boolean>): TriageResult {
        // Try enhanced protocols first, fall back to simple rules
        return try {
            evaluateWeighted(context, symptoms)
        } catch (_: Exception) {
            evaluateSimple(context, symptoms)
        }
    }

    private fun evaluateWeighted(context: Context, symptoms: Map<String, Boolean>): TriageResult {
        val json = context.assets.open("protocols.json")
            .bufferedReader()
            .use(BufferedReader::readText)

        val root = JSONObject(json)
        val conditions = root.getJSONArray("conditions")

        var bestResult: TriageResult? = null
        var bestSeverity = -1

        for (i in 0 until conditions.length()) {
            val cond = conditions.getJSONObject(i)

            // Age filter: patient_age_max_months > 0 means child-only condition
            val ageMax = cond.optInt("patient_age_max_months", 0)
            if (ageMax > 0 && symptoms["age_under_5"] != true) continue

            // Pregnancy filter
            if (cond.optBoolean("requires_pregnant", false) && symptoms["pregnant"] != true) continue

            // Calculate weighted score from matching triggers
            val triggers = cond.getJSONArray("triggers")
            var rawScore = 0.0
            var maxPossible = 0.0
            var hasAllRequired = true

            for (j in 0 until triggers.length()) {
                val trigger = triggers.getJSONObject(j)
                val symptom = trigger.getString("symptom")
                val weight = trigger.getDouble("weight")
                val required = trigger.optBoolean("required", false)

                maxPossible += weight

                if (symptoms[symptom] == true) {
                    rawScore += weight
                } else if (required) {
                    hasAllRequired = false
                }
            }

            // Skip if required symptom is missing or no symptoms matched
            if (!hasAllRequired || rawScore == 0.0) continue

            // Apply risk modifiers (from patient history flags passed as symptoms)
            var adjustedScore = rawScore
            val modifiers = cond.optJSONArray("risk_modifiers")
            if (modifiers != null) {
                for (j in 0 until modifiers.length()) {
                    val mod = modifiers.getJSONObject(j)
                    val flag = mod.getString("flag")
                    val multiplier = mod.getDouble("multiplier")
                    if (symptoms[flag] == true) {
                        adjustedScore *= multiplier
                    }
                }
            }

            // Determine triage level from thresholds
            val thresholds = cond.getJSONObject("thresholds")
            val urgentThreshold = thresholds.getDouble("urgent_referral")
            val phcThreshold = thresholds.getDouble("phc_visit")

            val triage = when {
                adjustedScore >= urgentThreshold -> "Urgent Referral"
                adjustedScore >= phcThreshold -> "PHC Visit"
                else -> "Home Care"
            }

            val severity = when (triage) {
                "Urgent Referral" -> 2
                "PHC Visit" -> 1
                else -> 0
            }

            val confidence = if (maxPossible > 0) (rawScore / maxPossible).toFloat().coerceIn(0f, 1f) else 0f

            // Pick the most severe result; break ties by confidence
            if (severity > bestSeverity ||
                (severity == bestSeverity && confidence > (bestResult?.confidence ?: 0f))) {
                bestSeverity = severity

                // Parse follow-up questions for this condition
                val followUps = mutableListOf<FollowUpQuestion>()
                val fuArray = cond.optJSONArray("follow_up_questions")
                if (fuArray != null) {
                    for (k in 0 until fuArray.length()) {
                        val fuObj = fuArray.getJSONObject(k)
                        val triggerSym = fuObj.optString("trigger_symptom", "")
                        // Only include questions whose trigger symptom is active (or no trigger)
                        if (triggerSym.isNotEmpty() && symptoms[triggerSym] != true) continue

                        val opts = mutableListOf<FollowUpOption>()
                        val optsArray = fuObj.optJSONArray("options")
                        if (optsArray != null) {
                            for (m in 0 until optsArray.length()) {
                                val optObj = optsArray.getJSONObject(m)
                                opts.add(FollowUpOption(
                                    label = optObj.getString("label"),
                                    weightBoost = optObj.optDouble("weight_boost", 0.0).toFloat(),
                                    triggersCamera = optObj.optBoolean("triggers_camera", false)
                                ))
                            }
                        }
                        followUps.add(FollowUpQuestion(
                            id = fuObj.getString("id"),
                            triggerSymptom = triggerSym,
                            type = fuObj.optString("type", ""),
                            questionEn = fuObj.optString("question_en", ""),
                            questionHi = fuObj.optString("question_hi", ""),
                            options = opts
                        ))
                    }
                }

                bestResult = TriageResult(
                    triage = triage,
                    matchedRule = cond.getString("id"),
                    description = cond.optString("rationale", ""),
                    confidence = confidence,
                    rationale = cond.optString("rationale", ""),
                    score = adjustedScore.toFloat(),
                    maxScore = maxPossible.toFloat(),
                    followUpQuestions = if (confidence < 0.70f) followUps else emptyList()
                )
            }
        }

        return bestResult ?: TriageResult(
            triage = "Home Care",
            matchedRule = "default",
            description = "No specific protocol matched. Default to Home Care.",
            confidence = 0f,
            rationale = "No matching condition found for the reported symptoms."
        )
    }

    /**
     * Re-evaluate after follow-up answers.
     * Takes original result + total weight boost from follow-up answers.
     * Recalculates triage tier and confidence.
     */
    fun reEvaluateWithBoost(context: Context, symptoms: Map<String, Boolean>, followUpBoost: Float): TriageResult {
        val original = evaluate(context, symptoms)
        if (followUpBoost <= 0f) return original

        val boostedScore = original.score + followUpBoost
        val boostedMax = original.maxScore + followUpBoost // boost expands known info

        // Recalculate confidence with boosted info
        val newConfidence = if (boostedMax > 0f) (boostedScore / boostedMax).coerceIn(0f, 1f) else original.confidence

        // Reload thresholds for the matched condition to re-check triage tier
        try {
            val json = context.assets.open("protocols.json")
                .bufferedReader().use(BufferedReader::readText)
            val conditions = JSONObject(json).getJSONArray("conditions")
            for (i in 0 until conditions.length()) {
                val cond = conditions.getJSONObject(i)
                if (cond.getString("id") == original.matchedRule) {
                    val thresholds = cond.getJSONObject("thresholds")
                    val urgentT = thresholds.getDouble("urgent_referral").toFloat()
                    val phcT = thresholds.getDouble("phc_visit").toFloat()

                    val newTriage = when {
                        boostedScore >= urgentT -> "Urgent Referral"
                        boostedScore >= phcT -> "PHC Visit"
                        else -> "Home Care"
                    }

                    return original.copy(
                        triage = newTriage,
                        confidence = newConfidence,
                        score = boostedScore,
                        maxScore = boostedMax,
                        followUpQuestions = emptyList() // no more follow-ups needed
                    )
                }
            }
        } catch (_: Exception) { }

        // Fallback: just boost confidence
        return original.copy(
            confidence = newConfidence,
            score = boostedScore,
            maxScore = boostedMax,
            followUpQuestions = emptyList()
        )
    }

    /** Backward-compatible simple boolean matching using rules.json */
    private fun evaluateSimple(context: Context, symptoms: Map<String, Boolean>): TriageResult {
        val rulesJson = context.assets.open("rules.json")
            .bufferedReader()
            .use(BufferedReader::readText)

        val conditions = JSONObject(rulesJson).getJSONArray("conditions")

        for (i in 0 until conditions.length()) {
            val condition = conditions.getJSONObject(i)
            val rules = condition.getJSONObject("rules")
            val keys = rules.keys()
            var allMatch = true
            while (keys.hasNext()) {
                val key = keys.next()
                val expected = rules.getBoolean(key)
                val actual = symptoms[key] ?: false
                if (actual != expected) {
                    allMatch = false
                    break
                }
            }
            if (allMatch) {
                return TriageResult(
                    triage = condition.getString("triage"),
                    matchedRule = condition.getString("id"),
                    description = condition.getString("description"),
                    confidence = 1f
                )
            }
        }

        return TriageResult(
            triage = "Home Care",
            matchedRule = "default",
            description = "No matching condition. Default to Home Care.",
            confidence = 0f
        )
    }
}
