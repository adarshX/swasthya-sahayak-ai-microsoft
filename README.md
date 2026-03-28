# Swasthya Sahayak AI

Offline-first clinical decision support for India's frontline ASHA health workers.

Built for the [Microsoft AI Unlocked Hackathon](https://microsoft.acehacker.com/aiunlocked/) at IIM Bangalore.

---

## The Problem

India's ASHA workers cover 600M+ rural patients with no AI tools, no reliable internet, and no persistent patient records. Every visit starts from zero. Critical cases get missed. Outbreaks go undetected until they've spread.

## Architecture

Three layers, each independently useful:

| Layer | Runs where | Responsibility |
|-------|-----------|----------------|
| On-device rule engine | Android, offline | WHO-IMNCI protocol triage, <50ms, no network |
| Cloud AI backend | FastAPI + MedGemma | Medical Q&A, RAG over health docs, sync endpoint |
| Supervisor dashboard | Web (embedded in backend) | Outbreak detection, field visit review, photo queue |

---

## Android App

**Language:** Kotlin. **Min SDK:** 26. **Storage:** Room SQLite. **Sync:** WorkManager.

When language is selected (Hindi / Kannada / Telugu / English), the entire app switches — TTS locale, voice recognizer locale, all UI labels, symptom category headers, triage result text, follow-up questions, gender spinner values, button text, hints. There is no cross-language mixing.

Features:

- Voice-first patient registration — speak name, age, gender, village; form auto-fills using on-device STT
- 23-symptom checklist across 7 categories, all translated in 4 languages
- Devanagari voice matching — "बच्चे को बुखार और तेज सांस" auto-checks fever, fast breathing, child under 5
- Offline triage — evaluates WHO-IMNCI protocols against checked symptoms, returns RED/ORANGE/GREEN with confidence %
- Returning patient lookup — last triage, pregnancy status, overdue vaccines, village shown on re-visit
- ASHABot — voice or text medical Q&A answered by MedGemma + RAG in the selected language
- Vaccination tracker — India NIS 2024 schedule (24 vaccines, birth to 5 years); shows done/due/overdue/not-yet per patient age; tap to mark as administered
- Private mode — sensitive symptoms show a patient-facing screen instead of clinical labels
- Photo capture — rashes, pallor, swelling; photos queue for doctor review after sync
- Background sync — WorkManager pushes cached records to backend when connectivity returns

---

## Backend

**Language:** Python 3.12. **Framework:** FastAPI + uvicorn.

AI provider chain (falls back left to right): MedGemma (Gemma-3-27b-it) → Groq → Azure OpenAI → OpenAI → Gemini.

RAG uses TF-IDF (scikit-learn) over 15 NHM/WHO health documents, 132 chunks. No FAISS, no vector DB — runs on the smallest VM. Requires `scikit-learn` installed; without it the stub returns empty context.

API endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Supervisor dashboard HTML |
| `/health` | GET | Service status, RAG info, model in use |
| `/sync-record` | POST | Receive visit record from Android app |
| `/records` | GET | All synced visit records |
| `/cases-summary` | GET | Aggregated stats + AI-generated trend insight |
| `/ask-knowledge` | POST | RAG + MedGemma Q&A |
| `/rag-stats` | GET | Corpus statistics |
| `/outbreak-radar` | GET | 72-hour case clustering by village + condition |
| `/photo-review-queue` | GET | Photos pending doctor review |
| `/photo-diagnosis` | POST | Doctor submits diagnosis for a photo |

---

## Protocol Engine

11 WHO-IMNCI protocols in YAML (pneumonia, diarrhea, malaria, anemia, malnutrition, pregnancy danger signs, UTI, etc.). Each symptom carries a weight; weights sum to a confidence score; score maps to a triage band.

Compile protocols to JSON and copy to Android assets:

```bash
cd protocol-engine
python compile_protocols.py
```

Every rule is traceable back to a WHO-IMNCI or NHM source document.

---

## Repo Structure

```
android-app/
  app/src/main/java/com/swasthya/sahayak/
    MainActivity.kt           voice registration, symptom checklist, triage display, ASHABot
    TriageEngine.kt           offline protocol evaluator
    VaccinationActivity.kt    India NIS schedule tracker, multilingual
    SyncWorker.kt             WorkManager background sync
    VisitRecord.kt            Room entity for visit records
    Patient.kt / PatientDao   Room entity + DAO for patient demographics
    SeedData.kt               5 pre-populated demo patients
  app/src/main/assets/
    protocols.json            compiled triage rules (output of compile_protocols.py)
  local.properties            SDK path + backendUrl (not committed)

backend/
  main.py                     all API routes + embedded dashboard HTML
  rag.py                      TF-IDF retrieval
  health_docs/                15 NHM/WHO markdown source documents

protocol-engine/
  protocols/                  11 YAML protocol files
  compile_protocols.py        compiles YAML → JSON, copies to Android assets
  evaluator.py                Python-side rule evaluator

tests/
  test_rag.py                 RAG + MedGemma unit and integration tests
  test_e2e.py                 end-to-end API tests

deployment/                   Docker Compose + Azure Bicep IaC
.env.example                  environment variable template
.vscode/settings.json         JDK 17 path for VSCode Java extension
```

---

## Setup

### Prerequisites

- Python 3.10+
- Android Studio with bundled JDK 17 (at `Android Studio/jbr`)
- ADB — ships with Android Studio SDK, typically at `%LOCALAPPDATA%\Android\Sdk\platform-tools\`
- Android device (API 26+) or emulator

### 1. Clone

```bash
git clone https://github.com/your-org/swasthya-sahayak-ai.git
cd swasthya-sahayak-ai
```

### 2. Configure environment

```bash
cp .env.example .env
```

Minimum required:

```env
GEMINI_API_KEY=your-google-ai-studio-key
MEDGEMMA_ENABLED=true
MEDGEMMA_MODEL=gemma-3-27b-it
GEMINI_MODEL=gemini-2.5-flash-lite
```

Free Gemini API key: https://aistudio.google.com/app/apikey

Optional, for full Azure stack:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=...
AZURE_STORAGE_CONNECTION_STRING=...
GROQ_API_KEY=...
```

### 3. Start backend

```bash
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

Windows:

```powershell
pip install -r backend\requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

Verify at http://localhost:8080 — supervisor dashboard should load.

### 4. Configure Android app

Edit `android-app/local.properties`:

```properties
sdk.dir=C\:\\Users\\<you>\\AppData\\Local\\Android\\Sdk

# emulator
backendUrl=http\://10.0.2.2\:8080

# physical device via adb reverse (recommended)
backendUrl=http\://127.0.0.1\:8080
```

### 5. Build APK

Android Studio: Build > Build APK(s).

Or from terminal:

```bash
# Linux/Mac
cd android-app && ./gradlew assembleDebug
```

```powershell
# Windows — JAVA_HOME must point to Android Studio's JDK
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
cd android-app
.\gradlew assembleDebug
```

APK output: `android-app/app/build/outputs/apk/debug/app-debug.apk`

### 6. Install on device

Enable Developer Options > USB Debugging on the phone.

```bash
# Linux/Mac
adb install -r android-app/app/build/outputs/apk/debug/app-debug.apk
adb reverse tcp:8080 tcp:8080
```

```powershell
# Windows — if adb is not in PATH
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $adb devices
& $adb install -r android-app\app\build\outputs\apk\debug\app-debug.apk
& $adb reverse tcp:8080 tcp:8080
```

`adb reverse` tunnels port 8080 over USB. The phone hits `http://127.0.0.1:8080` without needing to share a Wi-Fi network with your machine.

### 7. VSCode Java extension

`.vscode/settings.json` is already committed with the correct path. If VSCode still shows a JDK error, run **Reload Window** from the command palette.

### 8. Run tests

```bash
# unit tests, no backend needed
python tests/test_rag.py

# integration tests, backend must be running
python tests/test_rag.py --integration

# full suite
python tests/run_all_tests.py
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Android app | Kotlin, Room SQLite, WorkManager, CameraX |
| Voice I/O | Android SpeechRecognizer (on-device STT), TextToSpeech |
| Triage engine | Custom YAML-based rule engine compiled to JSON, evaluated on-device |
| Backend | FastAPI, Python 3.12, uvicorn |
| Medical AI | MedGemma (Gemma-3-27b-it) via Google GenAI SDK |
| RAG | TF-IDF, scikit-learn, 15 NHM/WHO health documents |
| Dashboard | HTML/JS embedded in FastAPI response, Leaflet.js |
| Storage | In-memory dict (demo) / Azure Blob Storage (production) |
| Sync | Android WorkManager, OkHttp |
| Deployment | Docker, Azure Container Apps, Bicep IaC |

---

## Azure Credentials

| Variable | Where to find it |
|----------|-----------------|
| `AZURE_STORAGE_CONNECTION_STRING` | Storage Account > Access keys |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI > Keys and Endpoint |
| `AZURE_OPENAI_KEY` | Same page, Key 1 |
| `AZURE_SPEECH_KEY` | AI Speech > Keys and Endpoint |

---

## Roadmap

**Done**
- India NIS 2024 vaccination tracker — per-patient status, tap to mark administered
- Full 4-language separation (hi/kn/te/en) — voice input, TTS, all UI elements, no mixing

**Planned**
- MedGemma 4B INT4 on-device via llama.cpp JNI — fully offline medical Q&A
- ABDM / ABHA ID integration for national patient records
- Embedding-based RAG (FAISS or pgvector) replacing TF-IDF
- Fine-tuned MedGemma on Indian public health protocols
- On-device photo classification for skin conditions
- Multi-state rollout (Karnataka, UP, Bihar pilot)
- NHM supply chain integration (ORS, antibiotic stock)
- WhatsApp bridge for ASHAs without smartphones

---

## Team

Product Geeks — Microsoft AI Unlocked Hackathon, IIM Bangalore

---

## License

Built for the Microsoft AI Unlocked Hackathon. See LICENSE for details.
