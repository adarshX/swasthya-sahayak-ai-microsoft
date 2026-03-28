package com.swasthya.sahayak

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "visit_records")
data class VisitRecord(
    @PrimaryKey(autoGenerate = true) val id: Int = 0,
    val patientId: String,
    val symptomsJson: String,   // serialised Map<String,Boolean>
    val triage: String,
    val confidence: Float = 0f,
    val matchedRule: String = "",
    val timestamp: Long = System.currentTimeMillis(),
    val synced: Boolean = false
)
