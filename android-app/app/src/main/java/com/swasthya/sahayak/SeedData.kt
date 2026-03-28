package com.swasthya.sahayak

import android.content.Context

/**
 * Seeds demo patient data on first launch for testing and hackathon demo.
 * Matches the demo patients described in the project plan.
 */
object SeedData {
    private const val PREFS_KEY = "swasthya_seed_v3_done"

    suspend fun seedIfNeeded(context: Context) {
        val prefs = context.getSharedPreferences("swasthya", Context.MODE_PRIVATE)
        if (prefs.getBoolean(PREFS_KEY, false)) return

        val db = VisitDatabase.get(context)
        val patientDao = db.patientDao()
        val visitDao = db.visitDao()

        // Demo patient 1: Ravi Kumar — returning child, last triage 12 days ago ORANGE
        val ravi = Patient(
            id = "demo-ravi-001",
            name = "Ravi Kumar",
            gender = "Male",
            village = "Rampur",
            dobMillis = System.currentTimeMillis() - (3L * 365 * 24 * 60 * 60 * 1000),
            riskScore = 0.6f,
            lastVisitMillis = System.currentTimeMillis() - (12L * 24 * 60 * 60 * 1000)
        )
        patientDao.insertPatient(ravi)
        visitDao.insert(VisitRecord(
            patientId = ravi.id,
            symptomsJson = """{"age_under_5":true,"fever":true,"fast_breathing":false}""",
            triage = "PHC Visit",
            confidence = 0.64f,
            matchedRule = "childhood_pneumonia",
            timestamp = ravi.lastVisitMillis ?: 0L,
            synced = true
        ))
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-ravi-mr1",
            patientId = ravi.id,
            vaccineName = "Measles-Rubella (MR-1)",
            isDue = true
        ))
        // Completed vaccinations for Ravi
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-ravi-bcg", patientId = ravi.id, vaccineName = "BCG",
            administeredAtMillis = ravi.dobMillis ?: 0L
        ))
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-ravi-opv0", patientId = ravi.id, vaccineName = "OPV-0",
            administeredAtMillis = ravi.dobMillis ?: 0L
        ))
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-ravi-hepb", patientId = ravi.id, vaccineName = "HepB Birth Dose",
            administeredAtMillis = ravi.dobMillis ?: 0L
        ))
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-ravi-penta1", patientId = ravi.id, vaccineName = "Pentavalent-1",
            administeredAtMillis = (ravi.dobMillis ?: 0L) + (42L * 24 * 60 * 60 * 1000)
        ))
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-ravi-opv1", patientId = ravi.id, vaccineName = "OPV-1",
            administeredAtMillis = (ravi.dobMillis ?: 0L) + (42L * 24 * 60 * 60 * 1000)
        ))

        // Demo patient 2: Priya Devi — pregnant, 32 weeks, high-risk
        val priya = Patient(
            id = "demo-priya-002",
            name = "Priya Devi",
            gender = "Female",
            village = "Sitapur",
            dobMillis = System.currentTimeMillis() - (28L * 365 * 24 * 60 * 60 * 1000),
            riskScore = 0.3f
        )
        patientDao.insertPatient(priya)
        patientDao.insertPregnancy(Pregnancy(
            id = "demo-preg-001",
            patientId = priya.id,
            week = 32,
            highRisk = true,
            riskFactors = "Previous miscarriage, borderline BP"
        ))

        // Demo patient 3: Mohan Singh — child, 1yr, 2 vaccinations overdue
        val mohan = Patient(
            id = "demo-mohan-003",
            name = "Mohan Singh",
            gender = "Male",
            village = "Rampur",
            dobMillis = System.currentTimeMillis() - (1L * 365 * 24 * 60 * 60 * 1000),
            riskScore = 0.1f
        )
        patientDao.insertPatient(mohan)
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-mohan-mr1",
            patientId = mohan.id,
            vaccineName = "Measles-Rubella (MR-1)",
            isDue = true
        ))
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-mohan-dpt",
            patientId = mohan.id,
            vaccineName = "DPT Booster-1",
            isOverdue = true
        ))
        // Completed vaccinations for Mohan
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-mohan-bcg", patientId = mohan.id, vaccineName = "BCG",
            administeredAtMillis = mohan.dobMillis ?: 0L
        ))
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-mohan-opv0", patientId = mohan.id, vaccineName = "OPV-0",
            administeredAtMillis = mohan.dobMillis ?: 0L
        ))
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-mohan-hepb", patientId = mohan.id, vaccineName = "HepB Birth Dose",
            administeredAtMillis = mohan.dobMillis ?: 0L
        ))
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-mohan-penta1", patientId = mohan.id, vaccineName = "Pentavalent-1",
            administeredAtMillis = (mohan.dobMillis ?: 0L) + (42L * 24 * 60 * 60 * 1000)
        ))
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-mohan-penta2", patientId = mohan.id, vaccineName = "Pentavalent-2",
            administeredAtMillis = (mohan.dobMillis ?: 0L) + (70L * 24 * 60 * 60 * 1000)
        ))
        patientDao.insertVaccination(Vaccination(
            id = "demo-vax-mohan-penta3", patientId = mohan.id, vaccineName = "Pentavalent-3",
            administeredAtMillis = (mohan.dobMillis ?: 0L) + (98L * 24 * 60 * 60 * 1000)
        ))

        // Demo patient 4: Sunita Bai — 6yr, recent RED triage
        val sunita = Patient(
            id = "demo-sunita-004",
            name = "Sunita Bai",
            gender = "Female",
            village = "Lucknow",
            dobMillis = System.currentTimeMillis() - (6L * 365 * 24 * 60 * 60 * 1000),
            riskScore = 0.8f,
            lastVisitMillis = System.currentTimeMillis() - (2L * 24 * 60 * 60 * 1000)
        )
        patientDao.insertPatient(sunita)
        visitDao.insert(VisitRecord(
            patientId = sunita.id,
            symptomsJson = """{"age_under_5":false,"fever":true,"fast_breathing":true,"chest_indrawing":true}""",
            triage = "Urgent Referral",
            confidence = 1.0f,
            matchedRule = "childhood_pneumonia",
            timestamp = sunita.lastVisitMillis ?: 0L,
            synced = true
        ))

        // Demo patient 5: Lakshmi Devi — anemia case
        val lakshmi = Patient(
            id = "demo-lakshmi-005",
            name = "Lakshmi Devi",
            gender = "Female",
            village = "Varanasi",
            dobMillis = System.currentTimeMillis() - (35L * 365 * 24 * 60 * 60 * 1000),
            riskScore = 0.4f,
            lastVisitMillis = System.currentTimeMillis() - (5L * 24 * 60 * 60 * 1000)
        )
        patientDao.insertPatient(lakshmi)
        visitDao.insert(VisitRecord(
            patientId = lakshmi.id,
            symptomsJson = """{"pallor":true,"weakness":true}""",
            triage = "PHC Visit",
            confidence = 0.67f,
            matchedRule = "anemia_screening",
            timestamp = lakshmi.lastVisitMillis ?: 0L,
            synced = true
        ))
        patientDao.insertRiskFlag(RiskFlag(
            id = "demo-flag-lakshmi-anemia",
            patientId = lakshmi.id,
            flagType = "anemia_suspected",
            severity = "moderate",
            active = true
        ))

        prefs.edit().putBoolean(PREFS_KEY, true).apply()
    }
}
