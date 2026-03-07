package com.swasthya.sahayak

import android.content.Context
import org.json.JSONObject
import java.io.BufferedReader

/**
 * Offline protocol engine — reads rules.json from assets and evaluates symptoms locally.
 * No network call. No ML model. Pure rule matching.
 */
object TriageEngine {

    data class TriageResult(
        val triage: String,
        val matchedRule: String,
        val description: String
    )

    fun evaluate(context: Context, symptoms: Map<String, Boolean>): TriageResult {
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
                    description = condition.getString("description")
                )
            }
        }

        return TriageResult(
            triage = "Home Care",
            matchedRule = "default",
            description = "No matching condition. Default to Home Care."
        )
    }
}
