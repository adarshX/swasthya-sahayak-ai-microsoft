package com.swasthya.sahayak

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "patients")
data class Patient(
    @PrimaryKey val id: String,
    val householdId: String = "",
    val name: String = "",
    val abdmHealthId: String? = null,
    val dobMillis: Long? = null,
    val gender: String = "",
    val village: String = "",
    val riskScore: Float = 0f,
    val lastVisitMillis: Long? = null,
    val chronicFlags: String? = null
)
