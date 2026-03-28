# Phase 1 & 2 — Test Cases & Validation Report

> Swasthya Sahayak AI · Phase 1 Core + Phase 2 X-Factors  
> Date: 2026-03-23

---

## Build Status

| Component | Status | Output |
|---|---|---|
| YAML Protocol Compiler | **PASS** | 5 protocols → `protocols.json` |
| Python Evaluator (10 test cases) | **PASS** | All triage decisions correct |
| Android APK (assembleDebug) | **PASS** | `app-debug.apk` — 6.6 MB |
| Backend (FastAPI) | **PASS** | All endpoints responding |

---

## 1. Enhanced Rule Engine (Phase 1.1)

### 1.1.1 Protocol YAML Compilation

| Test | Input | Expected | Status |
|---|---|---|---|
| Compile 5 YAML protocols | `python compile_protocols.py` | `protocols.json` with 5 conditions | **PASS** |
| Compiler output includes all fields | Check JSON structure | Each condition has id, triggers, thresholds, risk_modifiers, rationale | **PASS** |
| JSON copied to Android assets | Check `android-app/app/src/main/assets/protocols.json` | File exists and matches protocol-engine/protocols.json | **PASS** |

**Protocols compiled:**
1. `childhood_pneumonia` (WHO-IMNCI-2023) — triggers: fast_breathing, fever, chest_indrawing
2. `childhood_diarrhea` (WHO-IMNCI-2023) — triggers: diarrhea, vomiting, fever
3. `general_danger_signs` (WHO-IMNCI-2023) — triggers: convulsions, unable_to_feed, vomiting
4. `malaria_suspected` (NVBDCP-2023) — triggers: fever, severe_headache, vomiting
5. `pregnancy_danger_signs` (NHM-2023) — triggers: vaginal_bleeding, severe_headache, convulsions, fever

### 1.1.2 Weighted Scoring Engine (Python — `evaluator.py`)

| # | Symptoms | Expected Triage | Expected Confidence | Result |
|---|---|---|---|---|
| 1 | child + fever + fast_breathing | Urgent Referral (pneumonia) | 64% | **PASS** |
| 2 | child + fever + fast_breathing + chest_indrawing | Urgent Referral (pneumonia) | 100% | **PASS** |
| 3 | child + diarrhea + vomiting | Urgent Referral (diarrhea) | 80% | **PASS** |
| 4 | child + convulsions | Urgent Referral (danger signs) | 44% UNCERTAIN | **PASS** |
| 5 | child + fever (no fast breathing) | Home Care (malaria, below PHC threshold) | 44% UNCERTAIN | **PASS** |
| 6 | adult + fever + headache + vomiting | Urgent Referral (malaria) | 100% | **PASS** |
| 7 | pregnant + vaginal_bleeding | Urgent Referral (pregnancy danger) | 32% UNCERTAIN | **PASS** |
| 8 | pregnant + severe_headache | PHC Visit (pregnancy danger) | 20% UNCERTAIN | **PASS** |
| 9 | fever only (adult) | Home Care (malaria, below threshold) | 44% UNCERTAIN | **PASS** |
| 10 | no symptoms | Home Care (default) | 0% | **PASS** |

### 1.1.3 Confidence Threshold Logic

| Test | Condition | Expected |
|---|---|---|
| Confidence ≥ 70% | Show normal result | No "Uncertain" banner |
| Confidence < 70% | Show "Uncertain — Nurse will review" | Yellow warning banner visible |
| Confidence = 0% (no match) | Default Home Care, no confidence bar filled | Confidence bar at 0% |

### 1.1.4 Weighted Scoring Correctness

| Condition | Trigger Weights | Max Possible | Urgent Threshold | PHC Threshold |
|---|---|---|---|---|
| childhood_pneumonia | fast_breathing:3.0, fever:1.5, chest_indrawing:2.5 | 7.0 | 4.5 | 2.0 |
| childhood_diarrhea | diarrhea:2.5, vomiting:1.5, fever:1.0 | 5.0 | 4.0 | 2.0 |
| general_danger_signs | convulsions:4.0, unable_to_feed:3.5, vomiting:1.5 | 9.0 | 3.0 | 1.5 |
| malaria_suspected | fever:2.0, severe_headache:1.5, vomiting:1.0 | 4.5 | 4.0 | 3.0 |
| pregnancy_danger_signs | vaginal_bleeding:4.0, severe_headache:2.5, convulsions:4.0, fever:2.0 | 12.5 | 3.0 | 2.0 |

### 1.1.5 Risk Modifier Tests (Functional)

| Test | Risk Flag | Multiplier | Effect |
|---|---|---|---|
| severe_malnutrition on pneumonia child | `severe_malnutrition: true` | ×1.5 | Score boosted, may push PHC → Urgent |
| severe_malnutrition on diarrhea child | `severe_malnutrition: true` | ×1.5 | Score boosted |
| No risk flags | All false | ×1.0 | No change to score |

### 1.1.6 Age & Pregnancy Filters

| Test | Symptoms | Expected Behavior |
|---|---|---|
| Child conditions with age_under_5=false | adult + fast_breathing | Childhood pneumonia SKIPPED, falls to malaria or default |
| Pregnancy conditions with pregnant=false | vaginal_bleeding only | Pregnancy danger SKIPPED, default Home Care |
| Pregnancy conditions with pregnant=true | pregnant + vaginal_bleeding | Pregnancy danger MATCHED, Urgent Referral |
| Malaria (any age) | adult + fever + headache + vomiting | malaria_suspected MATCHED |

### 1.1.7 Backward Compatibility (Simple Rules Fallback)

| Test | Condition | Expected |
|---|---|---|
| If protocols.json missing | TriageEngine falls back to rules.json | Simple boolean matching works |
| Old 3-condition rules still present | rules.json untouched | Original behavior preserved |

---

## 2. Patient Health Records (Phase 1.2)

### 2.1 Room Database Entities

| Entity | Table Name | Fields | Primary Key | Status |
|---|---|---|---|---|
| VisitRecord | visit_records | id, patientId, symptomsJson, triage, confidence, matchedRule, timestamp, synced | id (auto) | **BUILT** |
| Patient | patients | id, householdId, name, abdmHealthId, dobMillis, gender, riskScore, lastVisitMillis, chronicFlags | id | **BUILT** |
| Household | households | id, workerId, villageCode, gpsLat, gpsLng, memberCount | id | **BUILT** |
| AshaWorker | asha_workers | workerId, name, phone, blockCode, languagePref | workerId | **BUILT** |
| Pregnancy | pregnancies | id, patientId, week, highRisk, eddMillis, riskFactors | id | **BUILT** |
| Vaccination | vaccinations | id, patientId, vaccineName, administeredAtMillis, isDue, isOverdue | id | **BUILT** |
| RiskFlag | risk_flags | id, patientId, flagType, severity, detectedAtMillis, active | id | **BUILT** |
| TriageResultEntity | triage_results | id, visitId, verdict, confidence, protocolVersion, matchedRule, nurseReviewed, aiAssisted | id | **BUILT** |

### 2.2 DAO Operations

**VisitDao:**

| Operation | Query | Status |
|---|---|---|
| Insert visit record | `INSERT` | **BUILT** |
| Get unsynced records | `WHERE synced = 0` | **BUILT** |
| Mark record as synced | `UPDATE SET synced = 1` | **BUILT** |

**PatientDao:**

| Operation | Query | Status |
|---|---|---|
| Insert/upsert patient | `INSERT OR REPLACE` | **BUILT** |
| Search by name | `WHERE name LIKE '%query%'` | **BUILT** |
| Get patient by ID | `WHERE id = :id` | **BUILT** |
| Get visits for patient | `WHERE patientId = :id ORDER BY timestamp DESC` | **BUILT** |
| Get recent visits (14-day window) | `WHERE patientId = :id AND timestamp > :since` | **BUILT** |
| Get active pregnancy | `WHERE patientId = :id LIMIT 1` | **BUILT** |
| Get due vaccinations | `WHERE isDue = 1 OR isOverdue = 1` | **BUILT** |
| Get active risk flags | `WHERE active = 1` | **BUILT** |
| Update patient after visit | `UPDATE riskScore, lastVisitMillis` | **BUILT** |
| Insert pregnancy/vaccination/risk flag | `INSERT OR REPLACE` | **BUILT** |

### 2.3 Database Migration

| Test | Expected | Status |
|---|---|---|
| Version bump 1 → 2 | `fallbackToDestructiveMigration()` handles cleanly | **BUILT** |
| All 8 entities in @Database annotation | Room compiles schema | **PASS** (APK builds) |

### 2.4 Seed Data (Demo Patients)

| Patient | Details | Seed Data |
|---|---|---|
| Ravi Kumar | 3yr male, last visit 12d ago (PHC Visit), MR-1 due | Patient + VisitRecord + Vaccination |
| Priya Devi | 28yr female, 32wk pregnant, high-risk | Patient + Pregnancy |
| Mohan Singh | 1yr male, MR-1 due + DPT overdue | Patient + 2× Vaccination |

---

## 3. Pre-Visit Patient Summary Card (Phase 1.3)

### 3.1 Summary Card UI

| Test | Input | Expected |
|---|---|---|
| Search existing patient "Ravi" | Type "Ravi" → tap 🔍 | Card shows: "Ravi Kumar · Male", "Last visit: 12 days ago — PHC Visit", "Risk: MEDIUM" |
| Search existing patient "Priya" | Type "Priya" → tap 🔍 | Card shows: "Priya Devi · Female", "🤰 Pregnant: Week 32 (HIGH RISK)" |
| Search new patient | Type "Unknown Name" → tap 🔍 | No summary card, badge shows "NEW", patient created in DB |
| Empty search | Tap 🔍 with empty field | Toast: "Enter a patient name" |

### 3.2 Patient Badge

| Scenario | Badge Text |
|---|---|
| New patient (auto-generated) | "NEW" |
| Returning patient found | "RETURNING" |
| After reset | "NEW" |

### 3.3 Risk Level Display

| Risk Score | Display | Color |
|---|---|---|
| ≥ 0.7 | "Risk: HIGH" | Red (#C62828) |
| 0.4–0.69 | "Risk: MEDIUM" | Orange (#E65100) |
| < 0.4 | "Risk: LOW" | Green (#2E7D32) |

---

## 4. Enhanced Voice Triage Flow (Phase 1.4)

### 4.1 New Symptom Checkboxes (11 total)

| Checkbox | Symptom Key | Hindi Voice Keywords | English Voice Keywords |
|---|---|---|---|
| 👶 Child under 5 | age_under_5 | bachcha, shishu | child, baby, infant |
| 🌡️ Fever | fever | bukhar, tapman | fever, hot, temperature |
| 💨 Fast breathing | fast_breathing | saans | breath, breathing, laboured |
| 🫁 Chest indrawing | chest_indrawing | seena, dhansna | chest, indrawing |
| 💧 Diarrhea | diarrhea | dast, potty | diarrhea, loose, watery |
| 🤢 Vomiting | vomiting | ulti | vomit, vomiting |
| ⚡ Convulsions | convulsions | mirgi | convulsion, seizure, fit |
| 🍼 Unable to feed | unable_to_feed | dudh nahi, kha nahi | not eating, feed, drink |
| 🤰 Pregnant | pregnant | garbhvati, hamal | pregnant |
| 🩸 Vaginal bleeding | vaginal_bleeding | khoon | bleeding, blood |
| 🤕 Severe headache | severe_headache | sir dard, sar dard | headache |

### 4.2 Recurrence Boost Logic

| Test | Scenario | Expected |
|---|---|---|
| First visit, no history | New patient, any symptoms | Normal triage, no boost |
| Return visit within 14 days, ≥50% symptom overlap | Ravi: fever + fast_breathing again | Triage boosted one level (e.g., PHC → Urgent) |
| Return visit within 14 days, <50% overlap | Different symptoms | No boost applied |
| Return visit older than 14 days | Old visit exists but outside window | No boost applied |
| Urgent stays Urgent | Already Urgent + recurring | No change (already max) |

### 4.3 Confidence Display in Result Card

| Test | Confidence Value | Expected UI |
|---|---|---|
| 100% confidence | All triggers match | Blue progress bar full, "Confidence: 100%", no warning |
| 64% confidence | Partial match | Bar at 64%, "⚠️ Uncertain — A nurse will review" visible |
| 32% confidence | Single danger sign | Bar at 32%, uncertain banner visible |
| 0% confidence | No match (default) | Bar at 0%, no uncertain banner (default Home Care) |

### 4.4 End-to-End Triage Flow

| Step | Action | Expected Result |
|---|---|---|
| 1 | Enter "Ravi Kumar", tap 🔍 | Summary card appears with history |
| 2 | Tap 🎙, say "bachche ko bukhaar hai aur saans tez hai" | age_under_5 + fever + fast_breathing auto-checked |
| 3 | Tap "GET TRIAGE DECISION" | Urgent Referral (pneumonia), confidence 64%, uncertain banner |
| 4 | Result card scrolls into view | Red header, confidence bar, description shown |
| 5 | Record saved to Room DB | VisitRecord with confidence=0.64, matchedRule=childhood_pneumonia |
| 6 | Sync scheduled | WorkManager enqueues SyncWorker |

---

## 5. Integration Tests

### 5.1 Android ↔ Rule Engine

| Test | Verification |
|---|---|
| TriageEngine reads protocols.json from assets | APK includes protocols.json, engine parses correctly |
| TriageEngine returns TriageResult with confidence | All fields populated (triage, matchedRule, confidence, rationale) |
| TriageEngine fallback to rules.json | If protocols.json removed, old boolean matching works |

### 5.2 Android ↔ Room Database

| Test | Verification |
|---|---|
| VisitRecord stores confidence + matchedRule | New fields written and readable |
| PatientDao queries work across tables | getVisitsForPatient returns VisitRecords for a Patient ID |
| Seed data loaded on first launch | 3 demo patients + visits + vaccinations + pregnancy present |
| Database version 2 migration | Destructive migration recreates DB cleanly |

### 5.3 Android ↔ Backend Sync

| Test | Verification |
|---|---|
| SyncWorker sends confidence + matched_rule | JSON payload includes new fields |
| Backend accepts new optional fields | POST /sync-record succeeds with confidence and matched_rule |
| Backend stores new fields | GET /records returns confidence and matched_rule |
| Dashboard shows confidence column | Table has "CONFIDENCE" column with percentage |

### 5.4 Backend Endpoints

| Endpoint | Test | Expected |
|---|---|---|
| `GET /health` | Hit endpoint | `{"status":"ok","version":"1.0.0",...}` |
| `POST /sync-record` | Send record with confidence | `{"status":"stored","record_id":"..."}` |
| `GET /records` | After sync | Returns records with confidence field |
| `GET /cases-summary` | After records exist | Returns counts + optional AI insight |
| `GET /` | Open in browser | Dashboard renders with confidence column |

### 5.5 Python Protocol Engine

| Test | Verification |
|---|---|
| evaluator.py reads protocols.json | `evaluate()` returns weighted scoring results |
| evaluator.py fallback to rules.json | `evaluate_simple()` works when protocols.json missing |
| Consistent results with Android engine | Same symptoms produce same triage + confidence in both engines |

---

## 6. What Was NOT Built in Phase 1 (Deferred)

| Feature | Plan Section | Reason | Phase |
|---|---|---|---|
| On-device MedGemma 4B INT4 | Layer 2 | llama.cpp JNI setup complexity | Phase 2+ |
| ASHABot Knowledge Q&A | Phase 2.1 | Requires RAG + Azure OpenAI | Phase 2 |
| Outbreak Radar | Phase 2.2 | Requires backend geo-clustering | Phase 2 |
| Stigma-Safe Mode | Phase 2.3 | UI mode switch | Phase 2 |
| Photo → Doctor → Record | Phase 2.5 | CameraX + Blob + review queue | Phase 2 |
| Vaccination Tracker Screen | Phase 3.3 | Separate screen with schedule calculator | Phase 3 |
| ABDM Integration | Roadmap | Government approval process | Future |
| Dialect Fine-tuning | Roadmap | Needs audio corpus | Future |

---

## Files Created / Modified

### New Files (13)
| File | Purpose |
|---|---|
| `protocol-engine/protocols/pneumonia_child.yaml` | WHO-IMNCI childhood pneumonia protocol |
| `protocol-engine/protocols/diarrhea_child.yaml` | WHO-IMNCI childhood diarrhea protocol |
| `protocol-engine/protocols/danger_signs_child.yaml` | WHO-IMNCI general danger signs |
| `protocol-engine/protocols/malaria_fever.yaml` | NVBDCP malaria/fever protocol |
| `protocol-engine/protocols/pregnancy_danger.yaml` | NHM pregnancy danger signs |
| `protocol-engine/compile_protocols.py` | YAML → JSON protocol compiler |
| `android-app/app/src/main/assets/protocols.json` | Compiled protocols for Android |
| `android-app/.../sahayak/Patient.kt` | Room entity: Patient |
| `android-app/.../sahayak/Household.kt` | Room entity: Household |
| `android-app/.../sahayak/HealthEntities.kt` | Room entities: AshaWorker, Pregnancy, Vaccination, RiskFlag |
| `android-app/.../sahayak/TriageResultEntity.kt` | Room entity: TriageResult |
| `android-app/.../sahayak/PatientDao.kt` | DAO for patient + health queries |
| `android-app/.../sahayak/SeedData.kt` | Demo patient seeder (3 patients) |

### Modified Files (7)
| File | Changes |
|---|---|
| `android-app/.../sahayak/TriageEngine.kt` | Rewritten: weighted scoring, confidence, risk modifiers, fallback |
| `android-app/.../sahayak/VisitRecord.kt` | Added: confidence (Float), matchedRule (String) |
| `android-app/.../sahayak/VisitDatabase.kt` | Added: 8 entities, PatientDao, version 2, destructive migration |
| `android-app/.../sahayak/MainActivity.kt` | Added: patient search, 8 new checkboxes, confidence UI, recurrence boost |
| `android-app/.../res/layout/activity_main.xml` | Added: patient name input, summary card, 8 checkboxes, confidence bar |
| `android-app/.../sahayak/SyncWorker.kt` | Added: confidence + matched_rule in sync payload |
| `backend/main.py` | Added: optional confidence/matched_rule in model + storage + dashboard |
| `protocol-engine/evaluator.py` | Rewritten: weighted scoring, confidence, dual-mode evaluation |

---

# Phase 2 — X-Factor Features

## Build Status (Phase 2)

| Component | Status | Output |
|---|---|---|
| Backend (5 new endpoints) | **PASS** | `/ask-knowledge`, `/outbreak-radar`, `/photo-review-queue`, `/photo-diagnosis`, `/photo-review-stats` |
| Stigma-Safe Mode (Android) | **PASS** | Private mode dialog with 5 sensitive questions |
| Photo Capture (Android) | **PASS** | Camera intent + FileProvider |
| Demo Seed Data (5 patients) | **PASS** | Ravi, Priya, Mohan, Sunita, Lakshmi |
| Android APK | **PASS** | BUILD SUCCESSFUL |

---

## 7. ASHABot Knowledge Q&A (Phase 2.1)

### 7.1 Backend Endpoint

| Test | Input | Expected |
|---|---|---|
| POST `/ask-knowledge` with AI key | `{"question": "pregnancy mein blood pressure badhne par kya karein?", "language": "hi"}` | Hindi answer from AI with confidence |
| POST `/ask-knowledge` without AI key | Same | Error: "AI service not configured" message |
| POST with patient context | `{"question": "...", "patient_context": "32 week pregnant, high risk"}` | Context-aware answer |
| Language support | `{"language": "kn"}` | Response in Kannada |
| Language support | `{"language": "te"}` | Response in Telugu |

### 7.2 AI Fallback Chain

| Priority | Provider | Condition |
|---|---|---|
| 1 | Azure OpenAI | AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_KEY set |
| 2 | Direct OpenAI | OPENAI_API_KEY set |
| 3 | Google Gemini | GEMINI_API_KEY set |
| 4 | None | Returns "not configured" message |

---

## 8. Outbreak Radar (Phase 2.2)

### 8.1 Backend Endpoint

| Test | Condition | Expected |
|---|---|---|
| GET `/outbreak-radar` with no data | Empty records | `{"alerts":[], "total_clusters":0}` |
| 3+ same condition in same village in 72h | Sync 3 records with same village_code + matched_rule | Alert with status "potential", urgency 2 |
| 5+ records | 5 matching records | Alert with status "confirmed", urgency 3 |
| AI summary | AI key configured | `ai_summary` contains generated alert text |
| No AI key | Fallback | `ai_summary` contains raw count text |

### 8.2 Clustering Logic

| Field | Grouping | Window |
|---|---|---|
| village_code | Records grouped by village | Last 72 hours |
| matched_rule | Sub-grouped by condition | Same window |
| Threshold | ≥3 = potential, ≥5 = confirmed | Per cluster |

---

## 9. Stigma-Safe Mode (Phase 2.3)

### 9.1 Trigger Conditions

| Symptom Checked | Private Mode Button |
|---|---|
| 🤰 Pregnant | **VISIBLE** |
| 🩸 Vaginal bleeding | **VISIBLE** |
| 🩹 Abnormal discharge | **VISIBLE** |
| 🚽 Painful urination | **VISIBLE** |
| Any other symptom only | **HIDDEN** |

### 9.2 Private Mode Dialog

| Test | Expected |
|---|---|
| Tap "🔒 PRIVATE MODE" | Full-screen dialog opens with large text |
| 5 sensitive questions shown | Missed period, Contraception, Domestic violence, Mental health, Sexual health |
| Questions bilingual | Hindi + English shown together |
| Check boxes large (20sp) | Patient can tap directly on screen |
| Tap "DONE" | Dialog closes, selections saved as extra symptoms with 🔒 prefix |
| Toast shown | "Private answers recorded securely" |

### 9.3 Data Recording

| Data | Storage |
|---|---|
| Selected stigma items | `extraSymptoms` list with "🔒 key" prefix |
| Visit record | `_extra_reported` field in symptomsJson |
| Stigma-safe flag | `stigma_safe_used` field in sync payload |

---

## 10. Photo → Doctor → Record (Phase 2.5)

### 10.1 Photo Button Visibility

| Symptoms Checked | Photo Button |
|---|---|
| Pallor | **VISIBLE** |
| Visible wasting | **VISIBLE** |
| Bilateral edema | **VISIBLE** |
| Limb swelling | **VISIBLE** |
| Abnormal discharge | **VISIBLE** |
| Fever only | **HIDDEN** |

### 10.2 Photo Capture

| Test | Expected |
|---|---|
| Tap "📸 Photo for Doctor Review" | Camera opens |
| Take photo | Photo saved to `filesDir/visit_photos/` |
| After capture | Toast: "Photo saved. Doctor will review soon." |
| Extra symptoms updated | "📸 Photo captured for doctor review" added |

### 10.3 Backend Photo Review

| Endpoint | Method | Test |
|---|---|---|
| `/photo-review-queue` | GET | Returns pending photos list |
| `/photo-diagnosis` | POST | Accepts diagnosis, marks as reviewed |
| `/photo-review-stats` | GET | Returns total/pending/reviewed/conditions |

---

## 11. Zero-Internet Demo Mode (Phase 2.6)

### 11.1 Seed Data (5 Demo Patients)

| Patient | Details | Seed Data |
|---|---|---|
| Ravi Kumar | 3yr male, PHC Visit 12d ago, MR-1 due | Patient + Visit + Vaccination |
| Priya Devi | 28yr female, 32wk pregnant, high-risk | Patient + Pregnancy |
| Mohan Singh | 1yr male, MR-1 due + DPT overdue | Patient + 2× Vaccination |
| Sunita Bai | 6yr female, RED triage 2d ago | Patient + Visit (Urgent Referral) |
| Lakshmi Devi | 35yr female, anemia suspected | Patient + Visit + RiskFlag |

### 11.2 Offline Functionality

| Feature | Works Offline? |
|---|---|
| Voice triage + symptom matching | ✅ Yes |
| Patient search + summary | ✅ Yes (Room DB) |
| Confidence scoring | ✅ Yes |
| Stigma-safe mode | ✅ Yes |
| Photo capture | ✅ Yes (saved locally) |
| ASHABot Q&A | ❌ No (needs AI API) |
| Outbreak radar | ❌ No (needs backend) |
| Sync to backend | ❌ No (queued for later) |

---

## Phase 2 — Files Created / Modified

### New Files
| File | Purpose |
|---|---|
| `android-app/.../res/xml/file_paths.xml` | FileProvider paths for photo capture |

### Modified Files
| File | Changes |
|---|---|
| `backend/main.py` | Added: 5 new endpoints (ask-knowledge, outbreak-radar, photo-review-queue, photo-diagnosis, photo-review-stats), _photo_queue, _ask_ai helper, knowledge prompt, new schemas |
| `android-app/.../AndroidManifest.xml` | Added: CAMERA permission, FileProvider |
| `android-app/.../MainActivity.kt` | Added: stigma-safe mode (enterStigmaSafeMode), photo capture (capturePhoto), photo button visibility logic |
| `android-app/.../res/layout/activity_main.xml` | Added: btnStigmaSafe (purple), btnTakePhoto in result card |
| `android-app/.../SeedData.kt` | Added: 2 more demo patients (Sunita Bai, Lakshmi Devi) |
