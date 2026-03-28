package com.swasthya.sahayak

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "asha_workers")
data class AshaWorker(
    @PrimaryKey val workerId: String,
    val name: String = "",
    val phone: String = "",
    val blockCode: String = "",
    val languagePref: String = "hi"
)

@Entity(tableName = "pregnancies")
data class Pregnancy(
    @PrimaryKey val id: String,
    val patientId: String,
    val week: Int = 0,
    val highRisk: Boolean = false,
    val eddMillis: Long? = null,
    val riskFactors: String? = null
)

@Entity(tableName = "vaccinations")
data class Vaccination(
    @PrimaryKey val id: String,
    val patientId: String,
    val vaccineName: String = "",
    val administeredAtMillis: Long? = null,
    val isDue: Boolean = false,
    val isOverdue: Boolean = false
)

@Entity(tableName = "risk_flags")
data class RiskFlag(
    @PrimaryKey val id: String,
    val patientId: String,
    val flagType: String = "",
    val severity: String = "",
    val detectedAtMillis: Long = System.currentTimeMillis(),
    val active: Boolean = true
)
