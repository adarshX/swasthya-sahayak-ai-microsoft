package com.swasthya.sahayak

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "triage_results")
data class TriageResultEntity(
    @PrimaryKey val id: String,
    val visitId: Int = 0,
    val verdict: String = "",
    val confidence: Float = 0f,
    val protocolVersion: String = "",
    val matchedRule: String = "",
    val nurseReviewed: Boolean = false,
    val aiAssisted: Boolean = false
)
