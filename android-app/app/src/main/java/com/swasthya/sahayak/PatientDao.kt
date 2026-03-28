package com.swasthya.sahayak

import androidx.room.*

@Dao
interface PatientDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertPatient(patient: Patient)

    @Query("SELECT * FROM patients ORDER BY lastVisitMillis DESC LIMIT 20")
    suspend fun getAllRecent(): List<Patient>

    @Query("SELECT * FROM patients WHERE name LIKE '%' || :query || '%' LIMIT 10")
    suspend fun searchByName(query: String): List<Patient>

    @Query("SELECT * FROM patients WHERE id = :id")
    suspend fun getById(id: String): Patient?

    @Query("SELECT * FROM visit_records WHERE patientId = :patientId ORDER BY timestamp DESC LIMIT :limit")
    suspend fun getVisitsForPatient(patientId: String, limit: Int = 10): List<VisitRecord>

    @Query("SELECT * FROM visit_records WHERE patientId = :patientId AND timestamp > :since ORDER BY timestamp DESC")
    suspend fun getRecentVisits(patientId: String, since: Long): List<VisitRecord>

    @Query("SELECT * FROM pregnancies WHERE patientId = :patientId LIMIT 1")
    suspend fun getActivePregnancy(patientId: String): Pregnancy?

    @Query("SELECT * FROM vaccinations WHERE patientId = :patientId AND (isDue = 1 OR isOverdue = 1)")
    suspend fun getDueVaccinations(patientId: String): List<Vaccination>

    @Query("SELECT * FROM vaccinations WHERE patientId = :patientId")
    suspend fun getAllVaccinations(patientId: String): List<Vaccination>

    @Query("SELECT * FROM risk_flags WHERE patientId = :patientId AND active = 1")
    suspend fun getActiveRiskFlags(patientId: String): List<RiskFlag>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertPregnancy(pregnancy: Pregnancy)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertVaccination(vaccination: Vaccination)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertRiskFlag(riskFlag: RiskFlag)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTriageResult(result: TriageResultEntity)

    @Query("UPDATE patients SET lastVisitMillis = :timestamp, riskScore = :riskScore WHERE id = :patientId")
    suspend fun updatePatientAfterVisit(patientId: String, timestamp: Long, riskScore: Float)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertHousehold(household: Household)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAshaWorker(worker: AshaWorker)
}
