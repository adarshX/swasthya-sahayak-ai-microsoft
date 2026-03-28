package com.swasthya.sahayak

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.Date

/**
 * WorkManager worker — runs when connectivity is available.
 * Pushes unsynced records to the FastAPI backend.
 */
class SyncWorker(appContext: Context, params: WorkerParameters) :
    CoroutineWorker(appContext, params) {

    private val client = OkHttpClient()
    private val baseUrl = BuildConfig.BACKEND_URL  // set in build.gradle

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val db = VisitDatabase.get(applicationContext)
        val dao = db.visitDao()
        val unsynced = dao.getUnsynced()
        // Get village code from shared prefs (set during ASHA registration)
        val prefs = applicationContext.getSharedPreferences("swasthya", android.content.Context.MODE_PRIVATE)
        val villageCode = prefs.getString("village_code", "rampur") ?: "rampur"

        for (record in unsynced) {
            val body = JSONObject().apply {
                put("patient_id", record.patientId)
                put("symptoms", JSONObject(record.symptomsJson))
                put("triage", record.triage)
                put("timestamp", Date(record.timestamp).toString())
                put("confidence", record.confidence)
                put("matched_rule", record.matchedRule)
                put("village_code", villageCode)
            }.toString()

            val request = Request.Builder()
                .url("$baseUrl/sync-record")
                .post(body.toRequestBody("application/json".toMediaType()))
                .build()

            try {
                val response = client.newCall(request).execute()
                if (response.isSuccessful) {
                    dao.markSynced(record.id)
                }
                response.close()
            } catch (e: Exception) {
                return@withContext Result.retry()
            }
        }
        Result.success()
    }
}
