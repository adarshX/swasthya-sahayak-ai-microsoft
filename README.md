# Swasthya Sahayak AI

Offline-first clinical decision-support system for India's frontline health workers.
Built for Microsoft AI Unlocked hackathon (https://microsoft.acehacker.com/aiunlocked/)

---

## Repo structure

```
android-app/          Kotlin Android app (offline triage + SQLite + sync)
backend/              FastAPI backend (sync endpoint + case intelligence)
protocol-engine/      Python rule evaluator (also embedded in Android as JSON)
deployment/           Docker Compose + Azure Bicep
docs/                 Architecture, API spec, triage rules
.env.example          Credential template
```

---

## Quick start

### 1. Backend (local)

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env        # fill in your Azure credentials
source ../.env                    # or: set -a; source ../.env; set +a
uvicorn main:app --reload
```

Test it:
```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/sync-record \
  -H "Content-Type: application/json" \
  -d '{"patient_id":"p1","symptoms":{"age_under_5":true,"fever":true,"fast_breathing":true},"triage":"Urgent Referral"}'
curl http://localhost:8000/cases-summary
```

### 2. Protocol engine (standalone test)

```bash
cd protocol-engine
python evaluator.py
```

### 3. Android app

1. Open `android-app/` in Android Studio.
2. In `local.properties` add:
   ```
   backendUrl=http://10.0.2.2:8000
   ```
   (Use your machine's IP if running on a physical device.)
3. Build and run on emulator / device (API 26+).

---

## Azure credentials — where to get them

| Credential | Where in Azure Portal |
|---|---|
| `AZURE_STORAGE_CONNECTION_STRING` | Storage Account → Security + networking → Access keys → Connection string |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource → Resource Management → Keys and Endpoint |
| `AZURE_OPENAI_KEY` | Same page, Key 1 or Key 2 |
| `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI Studio → Deployments → your deployment name |
| Speech key (Android) | Azure AI Speech resource → Keys and Endpoint |

Copy `.env.example` to `.env` and fill in the values. **Never commit `.env`.**

---

## Azure deployment

```bash
# Build and push image
docker build -t <your-acr>.azurecr.io/swasthya-backend:latest backend/
docker push <your-acr>.azurecr.io/swasthya-backend:latest

# Deploy infrastructure
az deployment group create \
  --resource-group swasthya-rg \
  --template-file deployment/main.bicep \
  --parameters storageAccountName=swasthyastorage backendImageName=<your-acr>.azurecr.io/swasthya-backend:latest
```

---

## System workflow

```
Worker → Android App
  └─ Voice/manual symptom capture
  └─ Protocol Engine (offline, JSON rules) → Triage decision
  └─ SQLite record saved locally
  └─ [When online] WorkManager sync → POST /sync-record → Azure Blob Storage
                                    → GET /cases-summary → Azure OpenAI insight
```

## Triage outputs

| Decision | Condition |
|---|---|
| Urgent Referral | Child <5, fever + fast breathing |
| PHC Visit | Child <5, fever, normal breathing |
| Home Care | Adult, mild fever |
