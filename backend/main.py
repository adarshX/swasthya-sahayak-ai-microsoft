"""
Swasthya Sahayak AI - FastAPI Backend
======================================
Endpoints:
  GET  /            -> Supervisor Dashboard (HTML)
  GET  /health      -> Service status JSON
  POST /sync-record -> Store a triage visit from Android app
  GET  /records     -> Recent visit records (for dashboard table)
  GET  /cases-summary -> Aggregate stats + AI insight

AI insight — automatic fallback chain (set keys in .env):
  1. Azure OpenAI  (AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_KEY)
  2. Direct OpenAI (OPENAI_API_KEY)
  3. Google Gemini (GEMINI_API_KEY)  ← fallback when Azure unavailable
  4. None          → returns null, dashboard shows placeholder
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Auto-load .env from project root
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# RAG module for health document retrieval
try:
    from rag import rag_context_string, get_doc_stats
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    def rag_context_string(q, top_k=3): return ""
    def get_doc_stats(): return {"total_chunks": 0, "sklearn_available": False}

# ---------------------------------------------------------------------------
# Optional dependency detection
# ---------------------------------------------------------------------------
try:
    from azure.storage.blob import BlobServiceClient
    AZURE_BLOB_AVAILABLE = True
except ImportError:
    AZURE_BLOB_AVAILABLE = False

try:
    from openai import OpenAI, AzureOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from google import genai as google_genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_BLOB_CONTAINER            = os.getenv("AZURE_BLOB_CONTAINER", "visit-records")

# AI providers — fallback order: Groq → Azure OpenAI → direct OpenAI → Gemini
GROQ_API_KEY            = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL              = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
AZURE_OPENAI_ENDPOINT   = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY        = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
OPENAI_API_KEY          = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL            = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_API_KEY          = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL            = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

# MedGemma — Google's medical foundation model (via same genai SDK)
MEDGEMMA_ENABLED        = os.getenv("MEDGEMMA_ENABLED", "true").lower() in ("true", "1", "yes")
MEDGEMMA_MODEL          = os.getenv("MEDGEMMA_MODEL", "medgemma-27b-text-it")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Swasthya Sahayak AI Backend", version="1.0.0")

# Serve static files (photos for doctor review)
_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

_records: list[dict] = []   # in-memory fallback when Blob Storage not configured
_photo_queue: list[dict] = []  # photo review queue (in-memory)
_answer_cache: dict[str, dict] = {}  # Q&A answer cache {question_hash: {answer, provider, timestamp}}

# Seed demo data for dashboard demo
_now = datetime.now(timezone.utc)

# Photo review queue — visual conditions a doctor would review from photos
_photo_queue.extend([
    {
        "visit_id": "demo-photo-001",
        "patient_id": "demo-ravi-001",
        "symptoms_summary": "rash on torso and arms, fever",
        "triage": "PHC Visit",
        "status": "pending",
        "created_at": _now.isoformat(),
        "photo_note": "Red spotted rash covering torso — possible measles",
        "image_file": "measles.png",
    },
    {
        "visit_id": "demo-photo-002",
        "patient_id": "demo-mohan-003",
        "symptoms_summary": "yellowing skin and eyes",
        "triage": "Urgent Referral",
        "status": "pending",
        "created_at": _now.isoformat(),
        "photo_note": "Jaundiced skin + yellow sclera in newborn — neonatal jaundice",
        "image_file": "jaundice.png",
    },
    {
        "visit_id": "demo-photo-003",
        "patient_id": "demo-lakshmi-005",
        "symptoms_summary": "pale inner eyelid, pale nails",
        "triage": "PHC Visit",
        "status": "pending",
        "created_at": _now.isoformat(),
        "photo_note": "Conjunctival pallor — suspected severe anemia (Hb test needed)",
        "image_file": "anemia.png",
    },
    {
        "visit_id": "demo-photo-004",
        "patient_id": "demo-sunita-004",
        "symptoms_summary": "swollen feet (bilateral edema)",
        "triage": "Urgent Referral",
        "status": "pending",
        "created_at": _now.isoformat(),
        "photo_note": "Bilateral pitting edema on both feet — kwashiorkor / SAM suspected",
        "image_file": "edema.png",
    },
])

# Seed visit records for outbreak radar + dashboard charts + nurse queue
_seed_records = [
    # Nagpur Ward 4 outbreak cluster: 4 fever+breathing cases in 24h (triggers outbreak alert)
    {"record_id": "seed-001", "patient_id": "demo-ravi-001", "symptoms": {"age_under_5": True, "fever": True, "fast_breathing": True},
     "triage": "Urgent Referral", "confidence": 0.64, "matched_rule": "childhood_pneumonia",
     "village_code": "nagpur_ward4", "timestamp": (_now).isoformat(), "synced_at": _now.isoformat()},
    {"record_id": "seed-002", "patient_id": "child-ward4-002", "symptoms": {"age_under_5": True, "fever": True, "fast_breathing": True, "chest_indrawing": True},
     "triage": "Urgent Referral", "confidence": 1.0, "matched_rule": "childhood_pneumonia",
     "village_code": "nagpur_ward4", "timestamp": (_now).isoformat(), "synced_at": _now.isoformat()},
    {"record_id": "seed-003", "patient_id": "child-ward4-003", "symptoms": {"age_under_5": True, "fever": True, "fast_breathing": True},
     "triage": "Urgent Referral", "confidence": 0.64, "matched_rule": "childhood_pneumonia",
     "village_code": "nagpur_ward4", "timestamp": (_now).isoformat(), "synced_at": _now.isoformat()},
    {"record_id": "seed-004", "patient_id": "child-ward4-004", "symptoms": {"age_under_5": True, "fever": True, "diarrhea": True, "vomiting": True},
     "triage": "Urgent Referral", "confidence": 0.80, "matched_rule": "childhood_diarrhea",
     "village_code": "nagpur_ward4", "timestamp": (_now).isoformat(), "synced_at": _now.isoformat()},
    # Village B: anemia cluster
    {"record_id": "seed-005", "patient_id": "demo-lakshmi-005", "symptoms": {"pallor": True, "weakness": True},
     "triage": "PHC Visit", "confidence": 0.67, "matched_rule": "anemia_screening",
     "village_code": "village_b", "timestamp": (_now).isoformat(), "synced_at": _now.isoformat()},
    {"record_id": "seed-006", "patient_id": "anemia-vb-002", "symptoms": {"pallor": True, "weakness": True, "breathlessness": True},
     "triage": "Urgent Referral", "confidence": 1.0, "matched_rule": "anemia_screening",
     "village_code": "village_b", "timestamp": (_now).isoformat(), "synced_at": _now.isoformat()},
    {"record_id": "seed-007", "patient_id": "anemia-vb-003", "symptoms": {"pallor": True, "weakness": True},
     "triage": "PHC Visit", "confidence": 0.67, "matched_rule": "anemia_screening",
     "village_code": "village_b", "timestamp": (_now).isoformat(), "synced_at": _now.isoformat()},
    # Misc: pregnancy danger, malnutrition
    {"record_id": "seed-008", "patient_id": "demo-priya-002", "symptoms": {"pregnant": True, "severe_headache": True},
     "triage": "PHC Visit", "confidence": 0.20, "matched_rule": "pregnancy_danger_signs",
     "village_code": "village_a", "timestamp": (_now).isoformat(), "synced_at": _now.isoformat(), "stigma_safe_used": True},
    {"record_id": "seed-009", "patient_id": "demo-sunita-004", "symptoms": {"visible_wasting": True, "bilateral_edema": True},
     "triage": "Urgent Referral", "confidence": 0.72, "matched_rule": "malnutrition_screening",
     "village_code": "village_a", "timestamp": (_now).isoformat(), "synced_at": _now.isoformat()},
    {"record_id": "seed-010", "patient_id": "demo-mohan-003", "symptoms": {"age_under_5": True, "fever": True, "fast_breathing": False},
     "triage": "Home Care", "confidence": 0.44, "matched_rule": "malaria_suspected",
     "village_code": "nagpur_ward4", "timestamp": (_now).isoformat(), "synced_at": _now.isoformat()},
]
_records.extend(_seed_records)


# ---------------------------------------------------------------------------
# Knowledge Q&A prompt
# ---------------------------------------------------------------------------
_LANG_NAMES = {"hi": "Hindi", "kn": "Kannada", "te": "Telugu", "en": "English", "ta": "Tamil", "mr": "Marathi"}

_KNOWLEDGE_PROMPT_TEMPLATE = (
    "You are a medical knowledge assistant for ASHA/ANM health workers in rural India. "
    "IMPORTANT INSTRUCTIONS:\n"
    "1. First, understand the question (it may be in Hindi, Kannada, Telugu, or English).\n"
    "2. Think and reason about the answer using WHO-IMNCI, NHM guidelines, and standard Indian public health protocols.\n"
    "3. CRITICAL LANGUAGE RULE: Your ENTIRE response MUST be written in {lang_name} ONLY. "
    "Do NOT mix languages. Do NOT include English words or sentences if the language is not English. "
    "Every single word of your response must be in {lang_name}.\n"
    "4. Keep the answer concise (3-4 sentences max), accurate, and actionable.\n"
    "5. If the condition is serious, always recommend visiting PHC/doctor immediately.\n"
    "6. Never give dangerous or speculative medical advice.\n"
    "7. Use simple everyday language that a village health worker would understand.\n"
    "8. When reference documents are provided below, base your answer on them and cite the source."
)

def _ask_ai(question: str, language: str = "hi", context: str = "") -> tuple[Optional[str], Optional[str], str]:
    """Ask the AI a knowledge question with RAG + 24h caching. Returns (answer, provider, rag_sources)."""
    import hashlib, time
    cache_key = hashlib.md5(f"{question}:{language}".encode()).hexdigest()
    cached = _answer_cache.get(cache_key)
    if cached and (time.time() - cached.get("ts", 0)) < 86400:
        return cached["answer"], cached["provider"] + " (cached)", cached.get("rag_sources", "")

    # --- RAG: Retrieve relevant health document chunks ---
    rag_context = rag_context_string(question, top_k=3)
    rag_sources = ""
    if rag_context:
        # Extract source names for citation
        import re as _re
        rag_sources = ", ".join(sorted(set(_re.findall(r'\[Source: ([^\]]+)\]', rag_context))))

    # Build prompt with RAG context
    lang_name = _LANG_NAMES.get(language, "Hindi")
    knowledge_prompt = _KNOWLEDGE_PROMPT_TEMPLATE.replace("{lang_name}", lang_name)
    prompt = f"{knowledge_prompt}\n\nYou MUST respond ENTIRELY in {lang_name}. No other language.\n"
    if rag_context:
        prompt += f"\n--- REFERENCE DOCUMENTS (from NHM/WHO guidelines) ---\n{rag_context}\n--- END REFERENCE ---\n"
    if context:
        prompt += f"Patient context: {context}\n"
    prompt += f"\nQuestion: {question}"

    user_msg = question
    if rag_context:
        user_msg = f"Based on these reference documents:\n{rag_context}\n\nQuestion: {question}"

    def _cache_and_return(answer, provider):
        _answer_cache[cache_key] = {"answer": answer, "provider": provider, "ts": time.time(), "rag_sources": rag_sources}
        return answer, provider, rag_sources

    # Try MedGemma first for medical queries (specialized medical model)
    if MEDGEMMA_ENABLED and GEMINI_AVAILABLE and GEMINI_API_KEY:
        try:
            client = google_genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(model=MEDGEMMA_MODEL, contents=prompt)
            answer = response.text.strip()
            return _cache_and_return(answer, f"MedGemma ({MEDGEMMA_MODEL})")
        except Exception:
            pass  # Fall through to other providers

    # Try OpenAI chain (Groq → Azure → OpenAI)
    if OPENAI_AVAILABLE:
        clients = []
        if GROQ_API_KEY:
            clients.append((
                OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1"),
                GROQ_MODEL, "Swasthya AI (RAG)" if rag_context else "Swasthya AI",
            ))
        if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY:
            clients.append((
                AzureOpenAI(azure_endpoint=AZURE_OPENAI_ENDPOINT, api_key=AZURE_OPENAI_KEY, api_version="2024-02-01"),
                AZURE_OPENAI_DEPLOYMENT, "Azure OpenAI (RAG)" if rag_context else "Azure OpenAI"
            ))
        if OPENAI_API_KEY:
            clients.append((OpenAI(api_key=OPENAI_API_KEY), OPENAI_MODEL, "OpenAI (RAG)" if rag_context else "OpenAI"))
        for client, model, label in clients:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": _KNOWLEDGE_PROMPT},
                              {"role": "user", "content": user_msg}],
                    max_tokens=300,
                )
                answer = resp.choices[0].message.content.strip()
                return _cache_and_return(answer, label)
            except Exception:
                continue

    # Gemini fallback
    if GEMINI_AVAILABLE and GEMINI_API_KEY:
        try:
            client = google_genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            answer = response.text.strip()
            return _cache_and_return(answer, "Gemini (RAG)" if rag_context else "Gemini")
        except Exception:
            pass

    return None, None, rag_sources


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SyncRecordRequest(BaseModel):
    patient_id: str
    symptoms: dict
    triage: str
    timestamp: Optional[str] = None
    confidence: Optional[float] = None
    matched_rule: Optional[str] = None
    village_code: Optional[str] = None
    stigma_safe_used: Optional[bool] = False
    photo_base64: Optional[str] = None

class SyncRecordResponse(BaseModel):
    status: str
    record_id: str

class AskKnowledgeRequest(BaseModel):
    question: str
    language: Optional[str] = "hi"
    patient_context: Optional[str] = None

class AskKnowledgeResponse(BaseModel):
    answer: str
    source: Optional[str] = None
    confidence: Optional[float] = None
    provider: Optional[str] = None
    rag_sources: Optional[str] = None
    rag_chunks_used: Optional[int] = None

class PhotoDiagnosisRequest(BaseModel):
    visit_id: str
    diagnosed_condition: str
    severity: str
    action_note: str
    reviewed_by: str

class CasesSummaryResponse(BaseModel):
    total_cases: int
    urgent_referrals: int
    phc_visits: int
    home_care: int
    ai_insight: Optional[str] = None
    ai_provider: Optional[str] = None


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------
def _blob_client():
    if AZURE_BLOB_AVAILABLE and AZURE_STORAGE_CONNECTION_STRING:
        return BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    return None

def _store_record(record: dict) -> None:
    client = _blob_client()
    if client is None:
        _records.append(record)
        return
    container = client.get_container_client(AZURE_BLOB_CONTAINER)
    try:
        container.create_container()
    except Exception:
        pass
    container.upload_blob(f"{record['record_id']}.json", json.dumps(record), overwrite=True)

def _load_all_records() -> list[dict]:
    client = _blob_client()
    if client is None:
        return list(_records)
    container = client.get_container_client(AZURE_BLOB_CONTAINER)
    records = []
    try:
        for blob in container.list_blobs():
            data = container.download_blob(blob.name).readall()
            records.append(json.loads(data))
    except Exception:
        pass
    return records


# ---------------------------------------------------------------------------
# AI insight — fallback chain: Azure OpenAI → OpenAI → Gemini
# ---------------------------------------------------------------------------
_AI_PROMPT_SYSTEM = (
    "You are a public health surveillance analyst for India's rural health system. "
    "Analyze these triage records from ASHA field workers and generate a structured insight.\n\n"
    "FORMAT YOUR RESPONSE EXACTLY LIKE THIS:\n"
    "🔍 PATTERN: [One clear sentence about the disease pattern or cluster you detected]\n"
    "⚠️ RISK: [One sentence about the health risk or potential outbreak concern]\n"
    "📋 ACTION: [One specific, actionable recommendation for the PHC supervisor]\n\n"
    "Keep each line under 25 words. Use plain English. Be specific about numbers and conditions."
)

def _insight_via_openai(summary: str) -> tuple[Optional[str], Optional[str]]:
    """Try Groq first, then Azure OpenAI, then direct OpenAI. Returns (text, provider_label)."""
    if not OPENAI_AVAILABLE:
        return None, None

    clients_to_try = []
    if GROQ_API_KEY:
        clients_to_try.append((
            OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1"),
            GROQ_MODEL, "Swasthya AI",
        ))
    if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY:
        clients_to_try.append((
            AzureOpenAI(
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
                api_key=AZURE_OPENAI_KEY,
                api_version="2024-02-01",
            ),
            AZURE_OPENAI_DEPLOYMENT,
            "Azure OpenAI",
        ))
    if OPENAI_API_KEY:
        clients_to_try.append((OpenAI(api_key=OPENAI_API_KEY), OPENAI_MODEL, "OpenAI"))

    for client, model, label in clients_to_try:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _AI_PROMPT_SYSTEM},
                    {"role": "user", "content": summary},
                ],
                max_tokens=150,
            )
            return resp.choices[0].message.content.strip(), label
        except Exception:
            continue  # try next provider

    return None, None


def _insight_via_gemini(summary: str) -> tuple[Optional[str], Optional[str]]:
    """Gemini fallback — used when both Azure OpenAI and direct OpenAI fail."""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        return None, None
    try:
        client = google_genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"{_AI_PROMPT_SYSTEM}\n\nTriage records:\n{summary}"
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        return response.text.strip(), "Gemini"
    except Exception as e:
        return f"AI insight unavailable: {str(e)}", "Gemini (error)"


def _generate_ai_insight(records: list[dict]) -> tuple[Optional[str], Optional[str]]:
    """Returns (insight_text, provider_label). Provider is for /health only."""
    if not records:
        return None, None

    summary = json.dumps(
        [{"triage": r["triage"], "symptoms": r["symptoms"]} for r in records[-20:]],
        indent=2,
    )

    text, provider = _insight_via_openai(summary)
    if text:
        return text, provider

    text, provider = _insight_via_gemini(summary)
    return text, provider


def _active_ai_provider() -> str:
    """Returns which AI provider is currently configured."""
    if OPENAI_AVAILABLE:
        if GROQ_API_KEY:
            return f"Swasthya AI"
        if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY:
            return f"Azure OpenAI ({AZURE_OPENAI_DEPLOYMENT})"
        if OPENAI_API_KEY:
            return f"OpenAI ({OPENAI_MODEL})"
    if GEMINI_AVAILABLE and GEMINI_API_KEY:
        return f"Gemini ({GEMINI_MODEL}) [fallback]"
    return "not configured"


# ---------------------------------------------------------------------------
# Supervisor Dashboard HTML
# ---------------------------------------------------------------------------
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Swasthya Sahayak – Supervisor Dashboard</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, Arial, sans-serif; background: #EEF2FF; color: #212121; }

    header {
      background: linear-gradient(135deg, #1565C0, #0D47A1);
      color: white; padding: 24px 28px;
      display: flex; align-items: center; gap: 16px;
    }
    header .logo { font-size: 36px; }
    header h1 { font-size: 22px; font-weight: 700; }
    header p { font-size: 13px; opacity: 0.75; margin-top: 3px; }
    .badge {
      margin-left: auto; background: rgba(255,255,255,0.2);
      border-radius: 20px; padding: 6px 14px; font-size: 12px;
    }
    .badge span { display: inline-block; width: 8px; height: 8px;
      background: #69FF8A; border-radius: 50%; margin-right: 6px; }

    .container { padding: 24px 28px; max-width: 1100px; margin: 0 auto; }

    .stats { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
    .card {
      background: white; border-radius: 14px; padding: 20px 24px;
      flex: 1; min-width: 160px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    }
    .card .label { font-size: 11px; font-weight: 700; letter-spacing: 0.08em; color: #757575; }
    .card .value { font-size: 40px; font-weight: 800; margin-top: 6px; }
    .card.total  .value { color: #1565C0; }
    .card.urgent { border-left: 5px solid #C62828; }
    .card.urgent .value { color: #C62828; }
    .card.phc    { border-left: 5px solid #E65100; }
    .card.phc    .value { color: #E65100; }
    .card.home   { border-left: 5px solid #2E7D32; }
    .card.home   .value { color: #2E7D32; }

    .insight {
      background: #1565C0; color: white;
      border-radius: 14px; padding: 20px 24px; margin-bottom: 24px;
      box-shadow: 0 2px 8px rgba(21,101,192,0.25);
      min-height: 72px; display: flex; align-items: center; gap: 16px;
    }
    .insight .icon { font-size: 28px; flex-shrink: 0; }
    .insight .text { font-size: 15px; line-height: 1.6; }
    .insight .text strong { display: block; font-size: 11px; letter-spacing: 0.08em;
      opacity: 0.7; margin-bottom: 4px; }

    .table-wrap {
      background: white; border-radius: 14px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.07); overflow: hidden;
    }
    .table-header {
      padding: 16px 20px;
      display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid #E0E0E0;
    }
    .table-header h2 { font-size: 15px; font-weight: 700; }
    .table-header small { font-size: 12px; color: #9E9E9E; }
    table { width: 100%; border-collapse: collapse; }
    th { background: #F5F5F5; padding: 12px 16px; text-align: left;
         font-size: 11px; font-weight: 700; letter-spacing: 0.08em; color: #616161; }
    td { padding: 13px 16px; font-size: 14px; border-bottom: 1px solid #F0F0F0; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #F8F9FF; }

    .badge-urgent { background: #FFEBEE; color: #C62828; border-radius: 20px;
      padding: 3px 10px; font-size: 12px; font-weight: 700; }
    .badge-phc    { background: #FFF3E0; color: #E65100; border-radius: 20px;
      padding: 3px 10px; font-size: 12px; font-weight: 700; }
    .badge-home   { background: #E8F5E9; color: #2E7D32; border-radius: 20px;
      padding: 3px 10px; font-size: 12px; font-weight: 700; }

    .symptom-tag {
      display: inline-block; background: #EEF2FF; color: #1565C0;
      border-radius: 10px; padding: 2px 8px; font-size: 11px; margin: 1px;
    }
    .empty { text-align: center; padding: 40px; color: #9E9E9E; font-size: 14px; }
    .refresh-note { text-align: center; font-size: 11px; color: #BDBDBD; padding: 12px; }
  </style>
</head>
<body>

<header>
  <div class="logo">+</div>
  <div>
    <h1>Swasthya Sahayak — Supervisor Dashboard</h1>
    <p>Real-time field visit monitoring for PHC supervisors</p>
  </div>
  <div class="badge"><span></span>Live</div>
</header>

<div class="container">
  <div class="stats">
    <div class="card total"><div class="label">TOTAL VISITS</div><div class="value" id="total">—</div></div>
    <div class="card urgent"><div class="label">🚨 URGENT REFERRAL</div><div class="value" id="urgent">—</div></div>
    <div class="card phc"><div class="label">⚠️ PHC VISIT</div><div class="value" id="phc">—</div></div>
    <div class="card home"><div class="label">✅ HOME CARE</div><div class="value" id="home">—</div></div>
  </div>

  <div class="insight" id="insight-box" style="flex-direction:column;align-items:flex-start">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
      <span style="font-size:28px">🤖</span>
      <strong id="ai-provider-label" style="font-size:11px;letter-spacing:0.08em;opacity:0.7">SWASTHYA AI PATTERN INSIGHT</strong>
    </div>
    <div id="insight-text" style="font-size:14px;line-height:1.8;white-space:pre-line">Loading…</div>
  </div>

  <div class="table-wrap">
    <div class="table-header">
      <h2>Recent Field Visits</h2>
      <small id="last-updated">—</small>
    </div>
    <table>
      <thead>
        <tr>
          <th>TIME (IST)</th>
          <th>PATIENT ID</th>
          <th>VILLAGE</th>
          <th>TRIAGE DECISION</th>
          <th>CONFIDENCE</th>
          <th>SYMPTOMS REPORTED</th>
        </tr>
      </thead>
      <tbody id="records-body">
        <tr><td colspan="4" class="empty">Loading records…</td></tr>
      </tbody>
    </table>
  </div>
  <div id="pagination-controls" style="text-align:center;padding:12px"></div>
  <p class="refresh-note">Auto-refreshes every 20 seconds · 10 records per page</p>

  <!-- Outbreak Map -->
  <div class="table-wrap" style="margin-top:16px;overflow:visible">
    <div class="table-header">
      <h2>🗺️ Outbreak Radar Map</h2>
      <small id="map-status">Loading...</small>
    </div>
    <div id="outbreak-map" style="height:300px;border-radius:0 0 14px 14px"></div>
  </div>

  <!-- Triage Trends Chart (Phase 3.1) -->
  <div class="table-wrap" style="margin-top:16px">
    <div class="table-header">
      <h2>📊 Triage Trends (7 Days)</h2>
      <small>RED / ORANGE / GREEN distribution</small>
    </div>
    <div style="padding:16px"><canvas id="trendsChart" height="200"></canvas></div>
  </div>

  <!-- Nurse Review Queue (Phase 3.1) -->
  <div class="table-wrap" style="margin-top:16px">
    <div class="table-header" style="flex-wrap:wrap;gap:8px">
      <h2>👩‍⚕️ Nurse Review Queue — Low Confidence Cases</h2>
      <div style="display:flex;align-items:center;gap:8px">
        <label style="font-size:11px;color:#616161;font-weight:700">LANGUAGE:</label>
        <select id="nurse-lang" onchange="renderNursePage()" style="padding:4px 10px;border:1px solid #E0E0E0;border-radius:6px;font-size:12px;cursor:pointer">
          <option value="en">English</option>
          <option value="hi">हिन्दी (Hindi)</option>
          <option value="kn">ಕನ್ನಡ (Kannada)</option>
          <option value="te">తెలుగు (Telugu)</option>
        </select>
        <small id="nurse-count" style="margin-left:8px">Loading…</small>
      </div>
    </div>
    <div id="nurse-queue-container" style="padding:0"></div>
    <div id="nurse-pagination" style="text-align:center;padding:12px"></div>
  </div>

  <!-- Doctor Dashboard Toggle -->
  <div style="position:fixed;right:0;top:50%;transform:translateY(-50%);z-index:999">
    <button onclick="toggleDoctorPanel()" style="background:#7B1FA2;color:white;border:none;padding:12px 8px;border-radius:10px 0 0 10px;cursor:pointer;writing-mode:vertical-rl;font-size:13px;font-weight:700;box-shadow:-2px 2px 8px rgba(0,0,0,0.2)" id="doc-toggle-btn">🩺 Doctor</button>
  </div>

  <!-- Image Popup Overlay -->
  <div id="image-popup" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);z-index:1100;justify-content:center;align-items:center;cursor:pointer" onclick="this.style.display='none'">
    <div style="max-width:90%;max-height:90%;text-align:center">
      <img id="popup-img" style="max-width:100%;max-height:80vh;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,0.5)"/>
      <div id="popup-caption" style="color:white;font-size:14px;margin-top:12px;font-weight:600"></div>
    </div>
  </div>

  <!-- Resizable Doctor Panel -->
  <div id="doctor-panel" style="display:none;position:fixed;right:0;top:0;width:520px;height:100vh;background:white;box-shadow:-4px 0 20px rgba(0,0,0,0.15);z-index:998;overflow-y:auto;padding:24px;transition:width 0.1s">
    <!-- Drag handle for resizing -->
    <div id="panel-resize" style="position:absolute;left:0;top:0;width:6px;height:100%;cursor:ew-resize;background:linear-gradient(90deg,#E0E0E0,transparent)" onmousedown="startResize(event)"></div>

    <h2 style="font-size:18px;color:#7B1FA2;margin-bottom:4px">🩺 Doctor Review Dashboard</h2>
    <p style="font-size:12px;color:#9E9E9E;margin-bottom:16px">Review photos, outbreak alerts, and patient cases</p>

    <!-- Login -->
    <div id="doctor-login" style="background:#F5F5F5;border-radius:12px;padding:20px">
      <input id="doc-user" placeholder="Username" style="width:100%;padding:10px;margin-bottom:8px;border:1px solid #E0E0E0;border-radius:8px;font-size:14px" value="admin"/>
      <input id="doc-pass" type="password" placeholder="Password" style="width:100%;padding:10px;margin-bottom:8px;border:1px solid #E0E0E0;border-radius:8px;font-size:14px"/>
      <button onclick="doctorLogin()" style="width:100%;padding:10px;background:#7B1FA2;color:white;border:none;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer">Login</button>
      <div id="doc-error" style="color:#C62828;font-size:12px;margin-top:6px"></div>
    </div>

    <!-- Doctor Content (hidden until login) -->
    <div id="doctor-content" style="display:none">
      <!-- Photo Review Queue -->
      <div style="margin-top:20px">
        <h3 style="font-size:14px;color:#7B1FA2;margin-bottom:4px">📸 Photo Review Queue</h3>
        <div id="photo-stats" style="font-size:12px;color:#616161;margin-bottom:12px">Loading...</div>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="background:#F5F5F5">
            <th style="padding:8px;text-align:left;font-size:11px;color:#616161">PHOTO</th>
            <th style="padding:8px;text-align:left;font-size:11px;color:#616161">PATIENT</th>
            <th style="padding:8px;text-align:left;font-size:11px;color:#616161">VISUAL NOTE</th>
            <th style="padding:8px;text-align:left;font-size:11px;color:#616161">TRIAGE</th>
            <th style="padding:8px;text-align:left;font-size:11px;color:#616161">ACTION</th>
          </tr></thead>
          <tbody id="photo-queue-body"><tr><td colspan="4" style="text-align:center;color:#9E9E9E;padding:20px">Login to view</td></tr></tbody>
        </table>
      </div>

      <!-- Recent Cases for Doctor Review -->
      <div style="margin-top:20px">
        <h3 style="font-size:14px;color:#1565C0;margin-bottom:8px">📋 Recent Patient Cases</h3>
        <div id="doctor-cases">Loading...</div>
      </div>

      <!-- Outbreak Radar -->
      <div style="margin-top:24px">
        <h3 style="font-size:14px;color:#C62828;margin-bottom:8px">🚨 Outbreak Radar (72h)</h3>
        <div id="outbreak-alerts">Loading...</div>
      </div>

      <!-- Quick Stats -->
      <div style="margin-top:24px;padding:16px;background:#F5F5F5;border-radius:12px">
        <h3 style="font-size:14px;color:#616161;margin-bottom:8px">📊 Quick Actions</h3>
        <button onclick="loadDoctorCases()" style="margin:4px;padding:8px 14px;background:#1565C0;color:white;border:none;border-radius:8px;cursor:pointer;font-size:12px">↻ Refresh Cases</button>
        <button onclick="loadPhotoQueue()" style="margin:4px;padding:8px 14px;background:#7B1FA2;color:white;border:none;border-radius:8px;cursor:pointer;font-size:12px">↻ Refresh Queue</button>
        <button onclick="loadOutbreakRadar()" style="margin:4px;padding:8px 14px;background:#C62828;color:white;border:none;border-radius:8px;cursor:pointer;font-size:12px">↻ Refresh Radar</button>
      </div>

      <!-- New Protocol Creator -->
      <div style="margin-top:24px;border-top:2px solid #E0E0E0;padding-top:20px">
        <h3 style="font-size:14px;color:#2E7D32;margin-bottom:12px">➕ Create New Triage Protocol</h3>
        <p style="font-size:11px;color:#9E9E9E;margin-bottom:12px">Add a new condition to the triage engine. It will be available after app rebuild.</p>

        <label style="font-size:11px;color:#616161;font-weight:700">CONDITION NAME</label>
        <input id="proto-name" placeholder="e.g. dengue_fever, tb_screening" style="width:100%;padding:8px;margin:4px 0 10px;border:1px solid #E0E0E0;border-radius:6px;font-size:13px"/>

        <label style="font-size:11px;color:#616161;font-weight:700">SOURCE / GUIDELINE</label>
        <input id="proto-source" placeholder="e.g. WHO-2024, NHM Guidelines" value="Doctor-created" style="width:100%;padding:8px;margin:4px 0 10px;border:1px solid #E0E0E0;border-radius:6px;font-size:13px"/>

        <div style="display:flex;gap:8px;margin-bottom:10px">
          <div style="flex:1">
            <label style="font-size:11px;color:#616161;font-weight:700">AGE LIMIT (months, 0=any)</label>
            <input id="proto-age" type="number" value="0" style="width:100%;padding:8px;border:1px solid #E0E0E0;border-radius:6px;font-size:13px"/>
          </div>
          <div style="flex:1">
            <label style="font-size:11px;color:#616161;font-weight:700">PREGNANCY ONLY?</label>
            <select id="proto-pregnant" style="width:100%;padding:8px;border:1px solid #E0E0E0;border-radius:6px;font-size:13px">
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </div>
        </div>

        <label style="font-size:11px;color:#616161;font-weight:700">TRIGGERS (symptoms)</label>
        <div id="proto-triggers" style="margin-bottom:10px"></div>
        <button onclick="addTriggerRow()" style="padding:4px 12px;background:#EEF2FF;border:1px solid #1565C0;color:#1565C0;border-radius:6px;cursor:pointer;font-size:11px;margin-bottom:10px">+ Add Symptom Trigger</button>

        <div style="display:flex;gap:8px;margin-bottom:10px">
          <div style="flex:1">
            <label style="font-size:11px;color:#616161;font-weight:700">URGENT THRESHOLD</label>
            <input id="proto-urgent" type="number" step="0.5" value="4.5" style="width:100%;padding:8px;border:1px solid #E0E0E0;border-radius:6px;font-size:13px"/>
          </div>
          <div style="flex:1">
            <label style="font-size:11px;color:#616161;font-weight:700">PHC THRESHOLD</label>
            <input id="proto-phc" type="number" step="0.5" value="2.0" style="width:100%;padding:8px;border:1px solid #E0E0E0;border-radius:6px;font-size:13px"/>
          </div>
        </div>

        <label style="font-size:11px;color:#616161;font-weight:700">RATIONALE / EXPLANATION</label>
        <textarea id="proto-rationale" rows="2" placeholder="Clinical reasoning for this protocol..." style="width:100%;padding:8px;margin:4px 0 12px;border:1px solid #E0E0E0;border-radius:6px;font-size:13px;resize:vertical"></textarea>

        <button onclick="submitProtocol()" style="width:100%;padding:10px;background:#2E7D32;color:white;border:none;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer">✓ Create Protocol</button>
        <div id="proto-result" style="margin-top:8px;font-size:12px"></div>
      </div>
    </div>
  </div>
</div>

<script>
function badgeClass(triage) {
  if (triage === 'Urgent Referral') return 'badge-urgent';
  if (triage === 'PHC Visit') return 'badge-phc';
  return 'badge-home';
}
function symptomTags(symptoms) {
  const map = { age_under_5: '👶 Child <5', fever: '🌡️ Fever', fast_breathing: '💨 Fast Breath',
    chest_indrawing: '🫁 Chest Indrawing', diarrhea: '💧 Diarrhea', vomiting: '🤢 Vomiting',
    convulsions: '⚡ Convulsions', unable_to_feed: '🍼 Unable to Feed',
    pregnant: '🤰 Pregnant', vaginal_bleeding: '🩸 Bleeding', severe_headache: '🤕 Headache',
    limb_swelling: '🦵 Limb Swelling', abnormal_discharge: '🩹 Discharge',
    painful_urination: '🚽 Painful Urination', abdominal_pain: '🤢 Abdominal Pain',
    pallor: '😶 Pallor', weakness: '😰 Weakness', visible_wasting: '🦴 Wasting',
    bilateral_edema: '🫧 Edema' };
  return Object.entries(symptoms)
    .filter(([,v]) => v === true)
    .map(([k]) => `<span class="symptom-tag">${map[k] || k}</span>`)
    .join('') || '<span style="color:#BDBDBD">None checked</span>';
}
function formatTime(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata',
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true });
  } catch { return ts; }
}
const FETCH_HEADERS = { 'ngrok-skip-browser-warning': 'true' };
let recordsPage = 0;
const PAGE_SIZE = 10;
let allRecords = [];

async function refresh() {
  try {
    const [summary, records] = await Promise.all([
      fetch('/cases-summary', { headers: FETCH_HEADERS }).then(r => r.json()),
      fetch('/records?limit=200', { headers: FETCH_HEADERS }).then(r => r.json())
    ]);
    document.getElementById('total').textContent  = summary.total_cases;
    document.getElementById('urgent').textContent = summary.urgent_referrals;
    document.getElementById('phc').textContent    = summary.phc_visits;
    document.getElementById('home').textContent   = summary.home_care;

    const provider = summary.ai_provider || 'Swasthya AI';
    document.getElementById('ai-provider-label').textContent = `${provider.replace(/Groq.*|OpenAI.*|Gemini.*/i, 'SWASTHYA AI')} PATTERN INSIGHT`;
    const rawInsight = summary.ai_insight || 'No insight yet — sync more records or configure an AI key in .env';
    document.getElementById('insight-text').innerHTML = rawInsight
      .replace(/🔍 *PATTERN:/g, '<strong style="color:#E3F2FD">🔍 PATTERN:</strong>')
      .replace(/⚠️ *RISK:/g, '<strong style="color:#FFCDD2">⚠️ RISK:</strong>')
      .replace(/📋 *ACTION:/g, '<strong style="color:#C8E6C9">📋 ACTION:</strong>')
      .replace(/\\n/g, '<br>');

    allRecords = records.slice().reverse();
    renderRecordsPage();
  } catch(e) {
    document.getElementById('insight-text').textContent = 'Connection error: ' + e.message;
  }
}

function renderRecordsPage() {
  const start = recordsPage * PAGE_SIZE;
  const page = allRecords.slice(start, start + PAGE_SIZE);
  const totalPages = Math.ceil(allRecords.length / PAGE_SIZE);
  const tbody = document.getElementById('records-body');

  if (!allRecords.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty">No records yet.</td></tr>';
  } else {
    tbody.innerHTML = page.map(r => {
      const isDoctorReview = r.matched_rule === 'doctor_photo_review';
      const diagBadge = isDoctorReview ? `<br><span style="background:#7B1FA2;color:white;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700">🩺 Dr: ${r.doctor_diagnosis} (${r.doctor_severity})</span><br><span style="color:#616161;font-size:11px">${r.doctor_note||''}</span>` : '';
      return `<tr${isDoctorReview ? ' style="background:#F3E5F5"' : ''}>
        <td>${formatTime(r.timestamp)}</td>
        <td style="font-family:monospace;font-size:12px">${(r.patient_id||'').slice(0,8)}…</td>
        <td style="font-size:12px">📍 ${r.village_code || '—'}</td>
        <td><span class="${badgeClass(r.triage)}">${r.triage}</span>${diagBadge}</td>
        <td>${r.confidence != null ? (r.confidence > 1 ? Math.round(r.confidence) : Math.round(r.confidence * 100)) + '%' : '—'}</td>
        <td>${isDoctorReview ? '<span class="symptom-tag" style="background:#F3E5F5;color:#7B1FA2">📸 Photo Reviewed by Dr. '+(r.doctor_reviewed_by||'')+'</span>' : symptomTags(r.symptoms || {})}</td>
      </tr>`;
    }).join('');
  }

  document.getElementById('last-updated').textContent =
    `Page ${recordsPage+1}/${totalPages} · ${allRecords.length} records · Updated ${new Date().toLocaleTimeString('en-IN')}`;
  document.getElementById('pagination-controls').innerHTML = `
    <button onclick="recordsPage=Math.max(0,recordsPage-1);renderRecordsPage()" ${recordsPage===0?'disabled':''} style="padding:6px 14px;border:1px solid #E0E0E0;border-radius:8px;background:white;cursor:pointer;margin:2px">← Prev</button>
    <span style="padding:0 10px;font-size:13px;color:#616161">${recordsPage+1} / ${totalPages}</span>
    <button onclick="recordsPage=Math.min(${totalPages-1},recordsPage+1);renderRecordsPage()" ${recordsPage>=totalPages-1?'disabled':''} style="padding:6px 14px;border:1px solid #E0E0E0;border-radius:8px;background:white;cursor:pointer;margin:2px">Next →</button>`;
}

refresh();
setInterval(refresh, 20000);

// ── Outbreak Map (Leaflet) ──
const map = L.map('outbreak-map').setView([25.5, 82.0], 6); // UP/Bihar focus
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap', maxZoom: 18
}).addTo(map);

// Village coordinates — UP/Bihar + Central India belt
const villageCoords = {
  'nagpur_ward4': [26.45, 83.00], 'village_a': [25.95, 81.60], 'village_b': [25.30, 83.90],
  'rampur': [26.80, 81.03], 'sitapur': [27.57, 80.68], 'lucknow': [26.85, 80.95],
  'varanasi': [25.32, 82.99], 'patna': [25.61, 85.14], 'gorakhpur': [26.76, 83.37],
  'kanpur': [26.45, 80.35], 'prayagraj': [25.43, 81.85], 'gaya': [24.80, 85.01],
  'muzaffarpur': [26.12, 85.39], 'deoria': [26.50, 83.78], 'mirzapur': [25.15, 82.58],
  'jaunpur': [25.75, 82.68], 'azamgarh': [26.07, 83.19], 'bhopal': [23.26, 77.41],
};
function getCoord(code) {
  if (!code) return null;
  const key = code.toLowerCase().replace(/[^a-z0-9]/g, '');
  for (const [k,v] of Object.entries(villageCoords)) {
    if (key.includes(k) || k.includes(key)) return v;
  }
  return null;
}

// Patient heatmap layer
let heatMarkers = [];
async function loadPatientHeatmap() {
  try {
    const data = await fetch('/records', { headers: FETCH_HEADERS }).then(r=>r.json());
    const records = Array.isArray(data) ? data : [];
    // Clear old markers
    heatMarkers.forEach(m => map.removeLayer(m));
    heatMarkers = [];
    let placed = 0;
    const villageCounts = {};
    for (const r of records) {
      const vc = r.village_code || '';
      villageCounts[vc] = (villageCounts[vc] || 0) + 1;
    }
    for (const [vc, count] of Object.entries(villageCounts)) {
      const coord = getCoord(vc);
      if (!coord) continue;
      placed++;
      const color = count >= 3 ? '#C62828' : count >= 2 ? '#E65100' : '#1565C0';
      const m = L.circleMarker(coord, {
        radius: 10 + count * 4, color: color, fillColor: color, fillOpacity: 0.35, weight: 2
      }).addTo(map);
      m.bindPopup(`<b>📍 ${vc}</b><br>${count} patient(s)`);
      heatMarkers.push(m);
    }
    if (placed > 0) {
      const bounds = heatMarkers.map(m => m.getLatLng());
      if (bounds.length > 1) map.fitBounds(bounds.map(l=>[l.lat,l.lng]), {padding:[40,40]});
    }
    document.getElementById('map-status').textContent = placed + ' village(s), ' + records.length + ' patient(s) mapped';
  } catch(e) { console.error('Heatmap error:', e); }
}

async function loadOutbreakMap() {
  try {
    const data = await fetch('/outbreak-radar', { headers: FETCH_HEADERS }).then(r=>r.json());
    for (const a of data.alerts) {
      const coord = getCoord(a.village_code) || [20.59 + Math.random()*5, 75 + Math.random()*8];
      const color = a.urgency >= 3 ? '#C62828' : '#E65100';
      const circle = L.circleMarker(coord, {
        radius: 8 + a.case_count * 2, color: color, fillColor: color, fillOpacity: 0.6
      }).addTo(map);
      circle.bindPopup(`<b>${a.status.toUpperCase()}: ${a.condition}</b><br>${a.case_count} cases<br>${a.ai_summary}`);
    }
  } catch(e) { document.getElementById('map-status').textContent = 'Map error: ' + e.message; }
}
loadPatientHeatmap();
loadOutbreakMap();

// ── Triage Trends Chart (Chart.js) ──
async function loadTrendsChart() {
  try {
    const data = await fetch('/dashboard-trends', { headers: FETCH_HEADERS }).then(r=>r.json());
    const ctx = document.getElementById('trendsChart').getContext('2d');
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [
          { label: 'Urgent Referral', data: data.urgent, backgroundColor: '#C62828' },
          { label: 'PHC Visit', data: data.phc, backgroundColor: '#E65100' },
          { label: 'Home Care', data: data.home, backgroundColor: '#2E7D32' },
        ]
      },
      options: { responsive: true, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
        plugins: { legend: { position: 'bottom' } } }
    });
  } catch(e) { console.error('Chart error:', e); }
}
loadTrendsChart();

// ── Nurse Review Queue (clinical context) ──
let nurseData = [];
let nursePage = 0;
const NURSE_PAGE_SIZE = 5;

const conditionGuide = {
  'childhood_pneumonia': {
    en: {what:'WHO-IMNCI: Fast breathing + fever in under-5 suggests pneumonia', risk:'Can progress to severe pneumonia within hours', action:'Refer to PHC immediately if chest indrawing present'},
    hi: {what:'WHO-IMNCI: 5 साल से कम उम्र में तेज़ सांस + बुखार निमोनिया का संकेत', risk:'कुछ घंटों में गंभीर निमोनिया में बदल सकता है', action:'छाती धंसने पर तुरंत PHC भेजें'},
    kn: {what:'WHO-IMNCI: 5 ವರ್ಷಕ್ಕಿಂತ ಕಡಿಮೆ ವಯಸ್ಸಿನ ಮಕ್ಕಳಲ್ಲಿ ವೇಗದ ಉಸಿರಾಟ + ಜ್ವರ ನ್ಯುಮೋನಿಯಾ ಸೂಚಿಸುತ್ತದೆ', risk:'ಕೆಲವೇ ಗಂಟೆಗಳಲ್ಲಿ ತೀವ್ರ ನ್ಯುಮೋನಿಯಾ ಆಗಬಹುದು', action:'ಎದೆ ಒಳಗೆಳೆಯುತ್ತಿದ್ದರೆ ತಕ್ಷಣ PHC ಗೆ ಕಳುಹಿಸಿ'},
    te: {what:'WHO-IMNCI: 5 ఏళ్ల లోపు పిల్లల్లో వేగంగా శ్వాస + జ్వరం న్యుమోనియా సూచన', risk:'కొన్ని గంటల్లో తీవ్ర న్యుమోనియాగా మారవచ్చు', action:'ఛాతీ లోపలికి లాగితే వెంటనే PHC కి పంపండి'},
  },
  'childhood_diarrhea': {
    en: {what:'Diarrhea with vomiting in child — dehydration risk', risk:'Severe dehydration can be fatal in under-5', action:'Start ORS immediately, refer if not drinking'},
    hi: {what:'बच्चे में दस्त + उल्टी — निर्जलीकरण का खतरा', risk:'गंभीर निर्जलीकरण 5 साल से कम बच्चों में जानलेवा', action:'तुरंत ORS शुरू करें, न पी रहा हो तो रेफर करें'},
    kn: {what:'ಮಗುವಿನಲ್ಲಿ ಭೇದಿ + ವಾಂತಿ — ನಿರ್ಜಲೀಕರಣ ಅಪಾಯ', risk:'ತೀವ್ರ ನಿರ್ಜಲೀಕರಣ 5 ವರ್ಷದೊಳಗಿನ ಮಕ್ಕಳಿಗೆ ಮಾರಕ', action:'ತಕ್ಷಣ ORS ಪ್ರಾರಂಭಿಸಿ, ಕುಡಿಯದಿದ್ದರೆ ರೆಫರ್ ಮಾಡಿ'},
    te: {what:'పిల్లల్లో విరేచనాలు + వాంతులు — నిర్జలీకరణ ప్రమాదం', risk:'తీవ్ర నిర్జలీకరణ 5 ఏళ్ల లోపు పిల్లలకు ప్రాణాంతకం', action:'వెంటనే ORS ఇవ్వండి, తాగకపోతే రిఫర్ చేయండి'},
  },
  'general_danger_signs': {
    en: {what:'Convulsions or inability to feed — danger sign', risk:'Life-threatening — requires hospital care', action:'Urgent referral to district hospital'},
    hi: {what:'दौरे या दूध न पी पाना — खतरे का संकेत', risk:'जानलेवा — अस्पताल में भर्ती ज़रूरी', action:'तुरंत ज़िला अस्पताल भेजें'},
    kn: {what:'ಸೆಳೆತ ಅಥವಾ ಹಾಲು ಕುಡಿಯಲಾಗದಿರುವಿಕೆ — ಅಪಾಯ ಸಂಕೇತ', risk:'ಜೀವಕ್ಕೆ ಅಪಾಯ — ಆಸ್ಪತ್ರೆ ಆರೈಕೆ ಅಗತ್ಯ', action:'ತಕ್ಷಣ ಜಿಲ್ಲಾ ಆಸ್ಪತ್ರೆಗೆ ರೆಫರ್ ಮಾಡಿ'},
    te: {what:'మూర్ఛలు లేదా పాలు తాగలేకపోవడం — ప్రమాద సంకేతం', risk:'ప్రాణాంతకం — ఆసుపత్రి చికిత్స అవసరం', action:'వెంటనే జిల్లా ఆసుపత్రికి పంపండి'},
  },
  'malaria_suspected': {
    en: {what:'Fever pattern suggests possible malaria', risk:'Can progress to cerebral malaria', action:'Blood test (RDT) needed, start treatment if positive'},
    hi: {what:'बुखार का पैटर्न मलेरिया का संकेत', risk:'सेरेब्रल मलेरिया में बदल सकता है', action:'रक्त जांच (RDT) कराएं, पॉजिटिव हो तो इलाज शुरू करें'},
    kn: {what:'ಜ್ವರದ ಮಾದರಿ ಮಲೇರಿಯಾ ಸೂಚಿಸುತ್ತದೆ', risk:'ಮೆದುಳಿನ ಮಲೇರಿಯಾಗೆ ಹೋಗಬಹುದು', action:'ರಕ್ತ ಪರೀಕ್ಷೆ (RDT) ಅಗತ್ಯ, ಧನಾತ್ಮಕವಾಗಿದ್ದರೆ ಚಿಕಿತ್ಸೆ ಪ್ರಾರಂಭಿಸಿ'},
    te: {what:'జ్వరం విధానం మలేరియా సూచిస్తుంది', risk:'సెరిబ్రల్ మలేరియాగా మారవచ్చు', action:'రక్త పరీక్ష (RDT) అవసరం, పాజిటివ్ అయితే చికిత్స ప్రారంభించండి'},
  },
  'pregnancy_danger_signs': {
    en: {what:'Danger sign in pregnancy — bleeding/headache/convulsions', risk:'Pre-eclampsia or hemorrhage risk', action:'Immediate referral to hospital with OB facility'},
    hi: {what:'गर्भावस्था में खतरे का संकेत — रक्तस्राव/सिरदर्द/दौरे', risk:'प्री-एक्लेम्पसिया या रक्तस्राव का खतरा', action:'तुरंत OB सुविधा वाले अस्पताल भेजें'},
    kn: {what:'ಗರ್ಭಾವಸ್ಥೆಯಲ್ಲಿ ಅಪಾಯ ಸಂಕೇತ — ರಕ್ತಸ್ರಾವ/ತಲೆನೋವು/ಸೆಳೆತ', risk:'ಪ್ರಿ-ಎಕ್ಲಾಂಪ್ಸಿಯಾ ಅಥವಾ ರಕ್ತಸ್ರಾವ ಅಪಾಯ', action:'ತಕ್ಷಣ OB ಸೌಲಭ್ಯವಿರುವ ಆಸ್ಪತ್ರೆಗೆ ರೆಫರ್ ಮಾಡಿ'},
    te: {what:'గర్భధారణలో ప్రమాద సంకేతం — రక్తస్రావం/తలనొప్పి/మూర్ఛలు', risk:'ప్రీ-ఎక్లాంప్సియా లేదా రక్తస్రావ ప్రమాదం', action:'వెంటనే OB సౌకర్యం ఉన్న ఆసుపత్రికి పంపండి'},
  },
  'anemia_screening': {
    en: {what:'Pallor suggests low hemoglobin', risk:'Severe anemia affects oxygen delivery', action:'Hb test + iron supplementation, refer if Hb < 7'},
    hi: {what:'पीलापन कम हीमोग्लोबिन का संकेत', risk:'गंभीर एनीमिया ऑक्सीजन पहुंचाने में बाधक', action:'Hb जांच + आयरन सप्लीमेंट, Hb < 7 हो तो रेफर करें'},
    kn: {what:'ಬಿಳಿಚಿಕೆ ಕಡಿಮೆ ಹಿಮೋಗ್ಲೋಬಿನ್ ಸೂಚಿಸುತ್ತದೆ', risk:'ತೀವ್ರ ರಕ್ತಹೀನತೆ ಆಮ್ಲಜನಕ ಪೂರೈಕೆ ಮೇಲೆ ಪರಿಣಾಮ', action:'Hb ಪರೀಕ್ಷೆ + ಕಬ್ಬಿಣ ಪೂರಕ, Hb < 7 ಆಗಿದ್ದರೆ ರೆಫರ್ ಮಾಡಿ'},
    te: {what:'పాలిపోవడం తక్కువ హిమోగ్లోబిన్ సూచన', risk:'తీవ్ర రక్తహీనత ఆక్సిజన్ సరఫరాను ప్రభావితం చేస్తుంది', action:'Hb పరీక్ష + ఐరన్ సప్లిమెంట్, Hb < 7 అయితే రిఫర్ చేయండి'},
  },
  'malnutrition_screening': {
    en: {what:'Wasting or edema in under-5', risk:'SAM has 30-50% mortality without treatment', action:'CMAM enrollment + therapeutic feeding'},
    hi: {what:'5 साल से कम में दुबलापन या सूजन', risk:'SAM बिना इलाज 30-50% मृत्यु दर', action:'CMAM में नामांकन + चिकित्सकीय आहार'},
    kn: {what:'5 ವರ್ಷದೊಳಗಿನವರಲ್ಲಿ ಕ್ಷೀಣತೆ ಅಥವಾ ಎಡೆಮಾ', risk:'SAM ಚಿಕಿತ್ಸೆ ಇಲ್ಲದೆ 30-50% ಮರಣ ದರ', action:'CMAM ನೋಂದಣಿ + ಚಿಕಿತ್ಸಾ ಆಹಾರ'},
    te: {what:'5 ఏళ్ల లోపు పిల్లల్లో శుష్కత లేదా వాపు', risk:'SAM చికిత్స లేకుండా 30-50% మరణాల రేటు', action:'CMAM నమోదు + చికిత్సా ఆహారం'},
  },
  'lymphatic_filariasis': {
    en: {what:'Limb swelling — possible filariasis', risk:'Progressive disability if untreated', action:'Blood test at night, DEC treatment'},
    hi: {what:'अंग में सूजन — फाइलेरिया संभव', risk:'बिना इलाज विकलांगता बढ़ती रहेगी', action:'रात में रक्त जांच, DEC दवाई'},
    kn: {what:'ಅಂಗ ಊತ — ಫೈಲೇರಿಯಾ ಸಾಧ್ಯ', risk:'ಚಿಕಿತ್ಸೆ ಇಲ್ಲದೆ ಅಂಗವೈಕಲ್ಯ ಹೆಚ್ಚುತ್ತದೆ', action:'ರಾತ್ರಿ ರಕ್ತ ಪರೀಕ್ಷೆ, DEC ಚಿಕಿತ್ಸೆ'},
    te: {what:'అంగం వాపు — ఫైలేరియా సాధ్యం', risk:'చికిత్స లేకుండా అంగవైకల్యం పెరుగుతుంది', action:'రాత్రి రక్త పరీక్ష, DEC చికిత్స'},
  },
  'vaginal_discharge': {
    en: {what:'Abnormal discharge with pain/fever', risk:'Possible STI or pelvic infection', action:'Refer for examination + lab tests'},
    hi: {what:'असामान्य स्राव + दर्द/बुखार', risk:'STI या पेल्विक संक्रमण संभव', action:'जांच + लैब टेस्ट के लिए रेफर करें'},
    kn: {what:'ಅಸಹಜ ಡಿಸ್ಚಾರ್ಜ್ + ನೋವು/ಜ್ವರ', risk:'STI ಅಥವಾ ಶ್ರೋಣಿ ಸೋಂಕು ಸಾಧ್ಯ', action:'ಪರೀಕ್ಷೆ + ಲ್ಯಾಬ್ ಪರೀಕ್ಷೆಗಳಿಗೆ ರೆಫರ್ ಮಾಡಿ'},
    te: {what:'అసాధారణ స్రావం + నొప్పి/జ్వరం', risk:'STI లేదా పెల్విక్ ఇన్ఫెక్షన్ సాధ్యం', action:'పరీక్ష + ల్యాబ్ పరీక్షల కోసం రిఫర్ చేయండి'},
  },
  'urinary_tract_infection': {
    en: {what:'Painful urination with fever', risk:'Can progress to kidney infection', action:'Urine test + antibiotics needed'},
    hi: {what:'दर्दनाक पेशाब + बुखार', risk:'गुर्दे के संक्रमण में बदल सकता है', action:'यूरिन टेस्ट + एंटीबायोटिक ज़रूरी'},
    kn: {what:'ನೋವಿನ ಮೂತ್ರ ವಿಸರ್ಜನೆ + ಜ್ವರ', risk:'ಮೂತ್ರಪಿಂಡ ಸೋಂಕಿಗೆ ಹೋಗಬಹುದು', action:'ಮೂತ್ರ ಪರೀಕ್ಷೆ + ಪ್ರತಿಜೀವಕಗಳು ಅಗತ್ಯ'},
    te: {what:'నొప్పితో మూత్ర విసర్జన + జ్వరం', risk:'కిడ్నీ ఇన్ఫెక్షన్‌గా మారవచ్చు', action:'మూత్ర పరీక్ష + యాంటీబయాటిక్స్ అవసరం'},
  },
};

const nurseUI = {
  en: {protocol:'PROTOCOL GUIDANCE', risk:'RISK IF MISSED', action:'RECOMMENDED ACTION', confirm:'Confirm AI Triage', override:'Override Decision', review:'Review Details', noCase:'No low-confidence cases pending review'},
  hi: {protocol:'प्रोटोकॉल मार्गदर्शन', risk:'छूटने पर खतरा', action:'अनुशंसित कार्रवाई', confirm:'AI ट्राइएज की पुष्टि करें', override:'निर्णय बदलें', review:'विवरण देखें', noCase:'कोई कम-विश्वसनीय केस लंबित नहीं'},
  kn: {protocol:'ಪ್ರೋಟೋಕಾಲ್ ಮಾರ್ಗದರ್ಶನ', risk:'ತಪ್ಪಿದರೆ ಅಪಾಯ', action:'ಶಿಫಾರಸು ಕ್ರಮ', confirm:'AI ಟ್ರಯಾಜ್ ದೃಢೀಕರಿಸಿ', override:'ನಿರ್ಧಾರ ಬದಲಿಸಿ', review:'ವಿವರ ನೋಡಿ', noCase:'ಕಡಿಮೆ ವಿಶ್ವಾಸಾರ್ಹ ಪ್ರಕರಣಗಳು ಬಾಕಿ ಇಲ್ಲ'},
  te: {protocol:'ప్రోటోకాల్ మార్గదర్శకత్వం', risk:'మిస్ అయితే ప్రమాదం', action:'సిఫార్సు చేసిన చర్య', confirm:'AI ట్రయాజ్ నిర్ధారించండి', override:'నిర్ణయం మార్చండి', review:'వివరాలు చూడండి', noCase:'తక్కువ విశ్వసనీయ కేసులు పెండింగ్ లేవు'},
};

async function loadNurseQueue() {
  try {
    const data = await fetch('/nurse-review-queue', { headers: FETCH_HEADERS }).then(r=>r.json());
    nurseData = data.queue;
    document.getElementById('nurse-count').textContent = data.count + ' cases need clinical review (confidence < 70%)';
    renderNursePage();
  } catch(e) { console.error(e); }
}

function renderNursePage() {
  const lang = document.getElementById('nurse-lang').value;
  const ui = nurseUI[lang] || nurseUI.en;
  const container = document.getElementById('nurse-queue-container');
  const start = nursePage * NURSE_PAGE_SIZE;
  const page = nurseData.slice(start, start + NURSE_PAGE_SIZE);
  const totalPages = Math.ceil(nurseData.length / NURSE_PAGE_SIZE) || 1;

  if (!nurseData.length) {
    container.innerHTML = `<div style="text-align:center;padding:30px;color:#9E9E9E">${ui.noCase}</div>`;
    document.getElementById('nurse-pagination').innerHTML = '';
    return;
  }

  container.innerHTML = page.map((r, idx) => {
    const symptoms = Object.entries(r.symptoms||{}).filter(([k,v])=>v===true).map(([k])=>k);
    const sympTags = symptoms.map(s => `<span style="background:#EEF2FF;color:#1565C0;border-radius:10px;padding:2px 8px;font-size:11px;margin:1px;display:inline-block">${s.replace(/_/g,' ')}</span>`).join(' ');
    const guideAll = conditionGuide[r.matched_rule] || {};
    const guide = guideAll[lang] || guideAll.en || {what:'Unknown condition', risk:'Review carefully', action:'Use clinical judgment'};
    const confColor = (r.confidence||0) < 0.4 ? '#C62828' : (r.confidence||0) < 0.6 ? '#E65100' : '#F57F17';
    const confPct = Math.round((r.confidence||0)*100);
    const uid = start + idx;

    return `<div style="border-bottom:1px solid #F0F0F0;padding:16px 20px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <div>
          <span style="font-family:monospace;font-size:13px;color:#616161">${(r.patient_id||'').slice(0,12)}</span>
          <span class="${badgeClass(r.triage)}" style="margin-left:8px">${r.triage}</span>
          <span style="font-weight:700;color:${confColor};margin-left:8px;font-size:14px">${confPct}%</span>
        </div>
        <button onclick="document.getElementById('nurse-detail-${uid}').style.display=document.getElementById('nurse-detail-${uid}').style.display==='none'?'block':'none'" style="background:#EEF2FF;border:1px solid #1565C0;color:#1565C0;padding:4px 12px;border-radius:6px;cursor:pointer;font-size:12px">📋 ${ui.review}</button>
      </div>
      <div style="margin-bottom:6px">${sympTags}</div>
      <div id="nurse-detail-${uid}" style="display:none;margin-top:12px;background:#FAFAFA;border-radius:10px;padding:14px;border-left:4px solid #1565C0">
        <div style="margin-bottom:8px"><strong style="color:#1565C0;font-size:11px">📖 ${ui.protocol}</strong><br><span style="font-size:13px">${guide.what}</span></div>
        <div style="margin-bottom:8px"><strong style="color:#C62828;font-size:11px">⚠️ ${ui.risk}</strong><br><span style="font-size:13px">${guide.risk}</span></div>
        <div style="margin-bottom:12px"><strong style="color:#2E7D32;font-size:11px">📋 ${ui.action}</strong><br><span style="font-size:13px">${guide.action}</span></div>
        <div style="display:flex;gap:8px">
          <button onclick="confirmNurseReview('${r.record_id}')" style="flex:1;background:#2E7D32;color:white;border:none;padding:8px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:700">✓ ${ui.confirm}</button>
          <button onclick="overrideNurseReview('${r.record_id}')" style="flex:1;background:#E65100;color:white;border:none;padding:8px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:700">✎ ${ui.override}</button>
        </div>
      </div>
    </div>`;
  }).join('');

  document.getElementById('nurse-pagination').innerHTML = `
    <button onclick="nursePage=Math.max(0,nursePage-1);renderNursePage()" ${nursePage===0?'disabled':''} style="padding:6px 14px;border:1px solid #E0E0E0;border-radius:8px;background:white;cursor:pointer;margin:2px">\u2190 Prev</button>
    <span style="padding:0 10px;font-size:13px;color:#616161">${nursePage+1} / ${totalPages}</span>
    <button onclick="nursePage=Math.min(${totalPages-1},nursePage+1);renderNursePage()" ${nursePage>=totalPages-1?'disabled':''} style="padding:6px 14px;border:1px solid #E0E0E0;border-radius:8px;background:white;cursor:pointer;margin:2px">Next \u2192</button>`;
}

loadNurseQueue();

function confirmNurseReview(recordId) {
  fetch('/nurse-review-confirm?record_id='+recordId, {method:'POST', headers:FETCH_HEADERS})
    .then(r=>r.json()).then(()=>{alert('Confirmed');loadNurseQueue()}).catch(e=>alert(e));
}
function overrideNurseReview(recordId) {
  const t = prompt('Override triage to (Urgent Referral / PHC Visit / Home Care):');
  if (!t) return;
  fetch('/nurse-review-confirm?record_id='+recordId+'&override_triage='+encodeURIComponent(t), {method:'POST', headers:FETCH_HEADERS})
    .then(r=>r.json()).then(()=>{alert('Overridden to: '+t);loadNurseQueue()}).catch(e=>alert(e));
}

// ── Doctor Dashboard Panel ──
let doctorLoggedIn = false;
function toggleDoctorPanel() {
  const panel = document.getElementById('doctor-panel');
  const isOpen = panel.style.display !== 'none';
  panel.style.display = isOpen ? 'none' : 'block';
  document.getElementById('doc-toggle-btn').textContent = isOpen ? '🩺 Doctor' : '✕ Close';
}

// Resizable panel
function startResize(e) {
  e.preventDefault();
  const panel = document.getElementById('doctor-panel');
  const startX = e.clientX;
  const startW = panel.offsetWidth;
  function onMove(e) {
    const newW = Math.max(360, Math.min(window.innerWidth * 0.85, startW + (startX - e.clientX)));
    panel.style.width = newW + 'px';
  }
  function onUp() { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

// Image popup
function showImagePopup(src, caption) {
  const popup = document.getElementById('image-popup');
  document.getElementById('popup-img').src = src;
  document.getElementById('popup-caption').textContent = caption || '';
  popup.style.display = 'flex';
}
function doctorLogin() {
  const user = document.getElementById('doc-user').value;
  const pass = document.getElementById('doc-pass').value;
  if (user === 'admin' && pass === 'admin') {
    doctorLoggedIn = true;
    document.getElementById('doctor-login').style.display = 'none';
    document.getElementById('doctor-content').style.display = 'block';
    loadDoctorCases();
    loadPhotoQueue();
    loadOutbreakRadar();
  } else {
    document.getElementById('doc-error').textContent = 'Invalid credentials';
  }
}
async function loadPhotoQueue() {
  try {
    const data = await fetch('/photo-review-queue', { headers: FETCH_HEADERS }).then(r=>r.json());
    const stats = await fetch('/photo-review-stats', { headers: FETCH_HEADERS }).then(r=>r.json());
    document.getElementById('photo-stats').innerHTML = `
      <span style="color:#C62828;font-weight:700">${stats.pending} pending</span> · 
      ${stats.reviewed} reviewed · ${stats.total_photos} total photos`;
    const tbody = document.getElementById('photo-queue-body');
    if (!data.queue.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#9E9E9E;padding:20px">No pending photos</td></tr>';
    } else {
      tbody.innerHTML = data.queue.map(p => {
        const imgFile = p.image_file || '';
        const imgThumb = imgFile ? `<img src="/static/photos/${imgFile}" style="width:60px;height:60px;object-fit:cover;border-radius:8px;cursor:pointer;border:2px solid #E0E0E0" onclick="showImagePopup('/static/photos/${imgFile}','${(p.photo_note||'').replace(/'/g,'')}')" onerror="this.style.display='none';this.nextSibling.style.display='block'" /><span style="display:none;color:#9E9E9E;font-size:11px">📷 Awaiting<br>upload</span>` : '<span style="color:#9E9E9E;font-size:11px">📷 Awaiting<br>upload</span>';
        return `<tr>
          <td style="padding:8px">${imgThumb}</td>
          <td style="font-family:monospace;font-size:12px">${(p.patient_id||'').slice(0,12)}</td>
          <td style="font-size:12px"><strong>${p.symptoms_summary||''}</strong>${p.photo_note ? '<br><span style="color:#7B1FA2;font-size:11px">'+p.photo_note+'</span>' : ''}</td>
          <td><span class="${badgeClass(p.triage)}">${p.triage}</span></td>
          <td><button onclick="reviewPhoto('${p.visit_id}')" style="background:#7B1FA2;color:white;border:none;padding:6px 12px;border-radius:8px;cursor:pointer;font-size:12px">📋 Review</button></td>
        </tr>`;
      }).join('');
    }
  } catch(e) { console.error(e); }
}
async function loadOutbreakRadar() {
  try {
    const data = await fetch('/outbreak-radar', { headers: FETCH_HEADERS }).then(r=>r.json());
    const el = document.getElementById('outbreak-alerts');
    if (!data.alerts.length) {
      el.innerHTML = '<div style="color:#9E9E9E;padding:16px;text-align:center">No outbreak alerts in last 72 hours</div>';
    } else {
      el.innerHTML = data.alerts.map(a => `
        <div style="background:${a.urgency>=3?'#FFEBEE':'#FFF3E0'};border-radius:10px;padding:14px;margin-bottom:8px">
          <strong style="color:${a.urgency>=3?'#C62828':'#E65100'}">${a.status.toUpperCase()}: ${a.condition}</strong>
          <br><span style="font-size:13px">${a.case_count} cases in village "${a.village_code}"</span>
          <br><span style="font-size:13px;color:#616161">${a.ai_summary}</span>
        </div>`).join('');
    }
  } catch(e) { console.error(e); }
}
async function loadDoctorCases() {
  try {
    const data = await fetch('/records', { headers: FETCH_HEADERS }).then(r=>r.json());
    const records = Array.isArray(data) ? data : (data.records || []);
    const el = document.getElementById('doctor-cases');
    if (!records.length) {
      el.innerHTML = '<div style="color:#9E9E9E;padding:16px;text-align:center">No patient cases yet</div>';
      return;
    }
    el.innerHTML = records.slice(0,10).map(r => {
      const syms = r.symptoms ? Object.entries(r.symptoms).filter(([,v])=>v===true).map(([k])=>k.replace(/_/g,' ')).join(', ') : '—';
      const triageColor = r.triage === 'Urgent Referral' ? '#C62828' : r.triage === 'PHC Visit' ? '#E65100' : '#2E7D32';
      const time = r.timestamp ? new Date(r.timestamp).toLocaleString('en-IN',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}) : '—';
      return `<div style="background:#FAFAFA;border-left:4px solid ${triageColor};border-radius:8px;padding:12px;margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <strong style="font-size:13px">${r.patient_id || 'Unknown'}</strong>
          <span style="font-size:11px;color:white;background:${triageColor};padding:2px 8px;border-radius:10px">${r.triage || '—'}</span>
        </div>
        <div style="font-size:12px;color:#616161;margin-top:4px">Symptoms: ${syms}</div>
        <div style="font-size:12px;color:#616161;margin-top:4px">📍 ${r.village_code || 'Unknown village'}</div>
        <div style="font-size:11px;color:#9E9E9E;margin-top:2px">${time} · Confidence: ${r.confidence != null ? (r.confidence > 1 ? Math.round(r.confidence) : Math.round(r.confidence * 100)) : '—'}%</div>
      </div>`;
    }).join('');
  } catch(e) { console.error('Doctor cases error:', e); }
}
function reviewPhoto(visitId) {
  const condition = prompt('Diagnosis (e.g. Measles, Rash-Allergic, Pallor-Mild):');
  if (!condition) return;
  const severity = prompt('Severity (Mild / Moderate / Severe):') || 'Moderate';
  const note = prompt('Action note for ASHA worker:') || '';
  fetch('/photo-diagnosis', {
    method: 'POST', headers: {'Content-Type':'application/json', ...FETCH_HEADERS},
    body: JSON.stringify({visit_id:visitId, diagnosed_condition:condition, severity:severity, action_note:note, reviewed_by:document.getElementById('doc-user').value})
  }).then(r=>r.json()).then(()=>{alert('Diagnosis submitted');loadPhotoQueue()}).catch(e=>alert('Error: '+e));
}

// ── Protocol Creator ──
let triggerCount = 0;
function addTriggerRow() {
  triggerCount++;
  const container = document.getElementById('proto-triggers');
  const row = document.createElement('div');
  row.style.cssText = 'display:flex;gap:6px;margin-bottom:6px;align-items:center';
  row.innerHTML = `
    <input id="trig-sym-${triggerCount}" placeholder="symptom key (e.g. fever)" style="flex:2;padding:6px;border:1px solid #E0E0E0;border-radius:4px;font-size:12px"/>
    <input id="trig-wt-${triggerCount}" type="number" step="0.5" value="2.0" placeholder="weight" style="flex:1;padding:6px;border:1px solid #E0E0E0;border-radius:4px;font-size:12px"/>
    <label style="font-size:11px;white-space:nowrap"><input type="checkbox" id="trig-req-${triggerCount}"> Required</label>`;
  container.appendChild(row);
}
// Start with 2 trigger rows
addTriggerRow(); addTriggerRow();

function submitProtocol() {
  const name = document.getElementById('proto-name').value.trim();
  if (!name) { alert('Enter a condition name'); return; }

  const triggers = [];
  for (let i = 1; i <= triggerCount; i++) {
    const sym = document.getElementById('trig-sym-'+i);
    if (!sym || !sym.value.trim()) continue;
    triggers.push({
      symptom: sym.value.trim().toLowerCase().replace(/\\s+/g,'_'),
      weight: parseFloat(document.getElementById('trig-wt-'+i).value) || 1.0,
      required: document.getElementById('trig-req-'+i).checked,
    });
  }
  if (!triggers.length) { alert('Add at least one symptom trigger'); return; }

  const body = {
    condition_name: name,
    source: document.getElementById('proto-source').value,
    age_max_months: parseInt(document.getElementById('proto-age').value) || 0,
    requires_pregnant: document.getElementById('proto-pregnant').value === 'true',
    triggers: triggers,
    urgent_threshold: parseFloat(document.getElementById('proto-urgent').value) || 4.5,
    phc_threshold: parseFloat(document.getElementById('proto-phc').value) || 2.0,
    rationale: document.getElementById('proto-rationale').value,
  };

  document.getElementById('proto-result').innerHTML = '<span style="color:#1565C0">Creating protocol...</span>';
  fetch('/create-protocol', {
    method: 'POST', headers: {'Content-Type':'application/json', ...FETCH_HEADERS},
    body: JSON.stringify(body)
  }).then(r=>r.json()).then(data => {
    document.getElementById('proto-result').innerHTML = `<span style="color:#2E7D32">✓ ${data.message || 'Protocol created!'}</span>`;
    document.getElementById('proto-name').value = '';
    document.getElementById('proto-rationale').value = '';
  }).catch(e => {
    document.getElementById('proto-result').innerHTML = `<span style="color:#C62828">Error: ${e}</span>`;
  });
}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML


@app.get("/health")
def health():
    blob_ok = _blob_client() is not None
    rag = get_doc_stats()
    return {
        "status": "ok",
        "version": "1.1.0",
        "blob_storage": "azure-blob" if blob_ok else "in-memory",
        "ai_provider": _active_ai_provider(),
        "rag": f"{rag['total_docs']} docs, {rag['total_chunks']} chunks" if rag["total_chunks"] else "not loaded",
        "medgemma": f"{MEDGEMMA_MODEL} (enabled)" if MEDGEMMA_ENABLED else "disabled",
        "dashboard": "http://localhost:8080/",
    }


@app.post("/sync-record", response_model=SyncRecordResponse)
def sync_record(body: SyncRecordRequest):
    record = {
        "record_id": str(uuid.uuid4()),
        "patient_id": body.patient_id,
        "symptoms": body.symptoms,
        "triage": body.triage,
        "timestamp": body.timestamp or datetime.now(timezone.utc).isoformat(),
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "confidence": body.confidence,
        "matched_rule": body.matched_rule,
        "village_code": body.village_code,
        "stigma_safe_used": body.stigma_safe_used,
    }
    # Handle photo if present — only queue visual conditions for doctor review
    if body.photo_base64:
        record["has_photo"] = True
        record["photo_reviewed"] = False
        # Map symptom keys to descriptive visual notes
        visual_notes = {
            "pallor": "Pale skin/conjunctiva — suspected anemia",
            "visible_wasting": "Visible wasting — suspected malnutrition (SAM)",
            "bilateral_edema": "Bilateral pitting edema on feet — kwashiorkor suspected",
            "limb_swelling": "Limb swelling — possible filariasis / elephantiasis",
            "abnormal_discharge": "Abnormal discharge — infection suspected",
        }
        active = [k for k, v in body.symptoms.items() if v is True]
        note = next((visual_notes[k] for k in active if k in visual_notes), f"Visual symptom photo: {', '.join(active)}")
        _photo_queue.append({
            "visit_id": record["record_id"],
            "patient_id": body.patient_id,
            "symptoms_summary": ", ".join(active),
            "triage": body.triage,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "photo_note": note,
        })
    try:
        _store_record(record)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return SyncRecordResponse(status="stored", record_id=record["record_id"])


@app.get("/records")
def records(limit: int = 50):
    """Returns recent visit records sorted by timestamp. Used by the dashboard."""
    all_records = _load_all_records()
    sorted_records = sorted(all_records, key=lambda r: r.get("timestamp", ""))
    return sorted_records[-limit:]


@app.get("/cases-summary", response_model=CasesSummaryResponse)
def cases_summary():
    all_records = _load_all_records()
    urgent = sum(1 for r in all_records if r.get("triage") == "Urgent Referral")
    phc    = sum(1 for r in all_records if r.get("triage") == "PHC Visit")
    home   = sum(1 for r in all_records if r.get("triage") == "Home Care")
    insight, provider = _generate_ai_insight(all_records)
    return CasesSummaryResponse(
        total_cases=len(all_records),
        urgent_referrals=urgent,
        phc_visits=phc,
        home_care=home,
        ai_insight=insight,
        ai_provider=provider,
    )


# ---------------------------------------------------------------------------
# Phase 2 Endpoints
# ---------------------------------------------------------------------------

# 2.1 — ASHABot Knowledge Q&A (with RAG over health docs + MedGemma)
@app.post("/ask-knowledge", response_model=AskKnowledgeResponse)
def ask_knowledge(body: AskKnowledgeRequest):
    answer, provider, rag_sources = _ask_ai(body.question, body.language or "hi", body.patient_context or "")
    if not answer:
        return AskKnowledgeResponse(
            answer="AI service not configured. Please set GEMINI_API_KEY, OPENAI_API_KEY, or Azure OpenAI keys in .env",
            provider="none",
        )
    rag_chunks = len(rag_sources.split(", ")) if rag_sources else 0
    return AskKnowledgeResponse(
        answer=answer,
        provider=provider,
        confidence=0.85 if rag_sources else 0.7,
        rag_sources=rag_sources or None,
        rag_chunks_used=rag_chunks or None,
    )


# 2.1b — RAG stats endpoint
@app.get("/rag-stats")
def rag_stats():
    """Health document corpus stats for debugging/monitoring."""
    stats = get_doc_stats()
    stats["rag_available"] = RAG_AVAILABLE
    return stats


# 2.2 — Outbreak Radar
@app.get("/outbreak-radar")
def outbreak_radar():
    """Detect potential disease outbreaks by clustering records by village + condition in last 72h."""
    all_records = _load_all_records()
    cutoff = datetime.now(timezone.utc).timestamp() - (72 * 3600)

    # Group by village_code + matched_rule
    clusters: dict[str, list] = {}
    for r in all_records:
        ts = r.get("timestamp", "")
        # Parse timestamp — handle both ISO format and human-readable
        try:
            if "T" in str(ts):
                record_ts = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
            else:
                record_ts = 0
        except Exception:
            record_ts = 0

        if record_ts < cutoff:
            continue

        village = r.get("village_code") or "unknown"
        condition = r.get("matched_rule") or "unknown"
        key = f"{village}|{condition}"
        clusters.setdefault(key, []).append(r)

    alerts = []
    for key, recs in clusters.items():
        if len(recs) < 3:
            continue
        village, condition = key.split("|", 1)
        urgency = 3 if len(recs) >= 5 else 2
        status = "confirmed" if len(recs) >= 5 else "potential"

        # Generate AI summary if available
        summary_text = f"{len(recs)} cases of {condition} in village {village} within 72 hours."
        ai_summary, _, _ = _ask_ai(
            f"Given {len(recs)} cases of {condition} in {village} over 72h, "
            "generate a 1-sentence alert for a PHC supervisor and 1 recommended action.",
            "en"
        )

        alerts.append({
            "village_code": village,
            "condition": condition,
            "case_count": len(recs),
            "status": status,
            "urgency": urgency,
            "ai_summary": ai_summary or summary_text,
            "records": [{"patient_id": r.get("patient_id"), "triage": r.get("triage")} for r in recs],
        })

    return {"alerts": alerts, "total_clusters": len(alerts)}


# 2.5 — Photo Review Queue
@app.get("/photo-review-queue")
def photo_review_queue():
    pending = [p for p in _photo_queue if p.get("status") == "pending"]
    return {"queue": pending, "pending_count": len(pending)}


@app.post("/photo-diagnosis")
def photo_diagnosis(body: PhotoDiagnosisRequest):
    for item in _photo_queue:
        if item.get("visit_id") == body.visit_id:
            item["status"] = "reviewed"
            item["diagnosed_condition"] = body.diagnosed_condition
            item["severity"] = body.severity
            item["action_note"] = body.action_note
            item["reviewed_by"] = body.reviewed_by
            item["reviewed_at"] = datetime.now(timezone.utc).isoformat()
            # Add reviewed record to main records so it shows in Recent Patient Cases
            _records.append({
                "record_id": body.visit_id + "-review",
                "patient_id": item.get("patient_id", ""),
                "symptoms": {"photo_diagnosis": True},
                "triage": item.get("triage", "PHC Visit"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "confidence": 1.0,
                "matched_rule": "doctor_photo_review",
                "doctor_diagnosis": body.diagnosed_condition,
                "doctor_severity": body.severity,
                "doctor_note": body.action_note,
                "doctor_reviewed_by": body.reviewed_by,
            })
            return {"status": "reviewed", "visit_id": body.visit_id}
    raise HTTPException(status_code=404, detail="Visit not found in review queue")


@app.get("/photo-review-stats")
def photo_review_stats():
    total = len(_photo_queue)
    reviewed = sum(1 for p in _photo_queue if p.get("status") == "reviewed")
    pending = total - reviewed
    conditions = {}
    for p in _photo_queue:
        if p.get("diagnosed_condition"):
            c = p["diagnosed_condition"]
            conditions[c] = conditions.get(c, 0) + 1
    return {
        "total_photos": total,
        "pending": pending,
        "reviewed": reviewed,
        "conditions": conditions,
    }


# Stigma-safe rate per ASHA worker
@app.get("/stigma-stats")
def stigma_stats():
    all_records = _load_all_records()
    total = len(all_records)
    stigma_used = sum(1 for r in all_records if r.get("stigma_safe_used"))
    rate = round(stigma_used / total * 100, 1) if total > 0 else 0
    return {
        "total_visits": total,
        "stigma_safe_visits": stigma_used,
        "stigma_safe_rate": rate,
    }


# Diagnosis push-back for Android polling
@app.get("/patient/{patient_id}/photo-updates")
def patient_photo_updates(patient_id: str):
    updates = [
        p for p in _photo_queue
        if p.get("patient_id") == patient_id and p.get("status") == "reviewed"
    ]
    return {"updates": updates}


# ---------------------------------------------------------------------------
# Phase 3 Endpoints
# ---------------------------------------------------------------------------

# 3.2 — AI Pre-Visit Brief
_brief_cache: dict[str, dict] = {}

@app.get("/patient/{patient_id}/brief")
def patient_brief(patient_id: str):
    import time, hashlib
    cache_key = hashlib.md5(patient_id.encode()).hexdigest()
    cached = _brief_cache.get(cache_key)
    if cached and (time.time() - cached.get("ts", 0)) < 86400:
        return {**cached["data"], "cached": True}

    # Build patient context from records
    all_records = _load_all_records()
    patient_records = [r for r in all_records if r.get("patient_id") == patient_id]
    patient_records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)

    if not patient_records:
        return {
            "brief_hindi": "कोई पिछला रिकॉर्ड नहीं मिला। यह नया patient हो सकता है।",
            "brief_english": "No previous records found. This may be a new patient.",
            "risk_level": "LOW",
            "urgent_flags": [],
            "cached": False,
        }

    # Build context for AI
    last = patient_records[0]
    visits_summary = "; ".join([
        f"{r.get('triage','?')} ({r.get('matched_rule','?')}, conf:{r.get('confidence','?')})"
        for r in patient_records[:5]
    ])
    context = (
        f"Patient ID: {patient_id}. "
        f"Total visits: {len(patient_records)}. "
        f"Last triage: {last.get('triage')} on {last.get('timestamp','')}. "
        f"Last symptoms: {json.dumps(last.get('symptoms', {}))}. "
        f"Recent history: {visits_summary}."
    )

    # Get AI brief
    question = (
        f"Generate a 3-line pre-visit brief for an ASHA worker in simple Hindi.\n"
        f"Line 1: Last visit + verdict (max 20 words). Format: '[date] ko [verdict]'\n"
        f"Line 2: Top health concern (max 20 words). Format: 'Samasya: [concern]'\n"
        f"Line 3: Action needed today (max 20 words). Format: 'Aaj: [action]'\n"
        f"Patient data: {context}"
    )
    answer_hi, _ = _ask_ai(question, "hi", context)

    question_en = (
        f"Generate a 3-line pre-visit brief for a health worker.\n"
        f"Line 1: Last visit + verdict. Line 2: Top concern. Line 3: Action today.\n"
        f"Max 20 words per line. Data: {context}"
    )
    answer_en, _ = _ask_ai(question_en, "en", context)

    # Determine risk level
    urgent_count = sum(1 for r in patient_records if r.get("triage") == "Urgent Referral")
    risk = "HIGH" if urgent_count >= 2 else ("MEDIUM" if urgent_count >= 1 else "LOW")

    flags = []
    if last.get("triage") == "Urgent Referral":
        flags.append("recent_urgent_referral")
    if last.get("confidence") and last["confidence"] < 0.7:
        flags.append("low_confidence_triage")

    result = {
        "brief_hindi": answer_hi or "AI brief उपलब्ध नहीं है।",
        "brief_english": answer_en or "AI brief not available.",
        "risk_level": risk,
        "urgent_flags": flags,
        "cached": False,
    }

    _brief_cache[cache_key] = {"data": result, "ts": time.time()}
    return result


# 3.1 — Dashboard data endpoints

@app.get("/dashboard-trends")
def dashboard_trends():
    """7-day triage distribution for Chart.js bar chart."""
    all_records = _load_all_records()
    from collections import defaultdict
    days = defaultdict(lambda: {"urgent": 0, "phc": 0, "home": 0})

    for r in all_records:
        ts = r.get("timestamp", "")
        try:
            if "T" in str(ts):
                day = str(ts)[:10]
            else:
                day = "unknown"
        except Exception:
            day = "unknown"

        triage = r.get("triage", "")
        if triage == "Urgent Referral":
            days[day]["urgent"] += 1
        elif triage == "PHC Visit":
            days[day]["phc"] += 1
        else:
            days[day]["home"] += 1

    # Sort by date, return last 7
    sorted_days = sorted(days.items())[-7:]
    return {
        "labels": [d[0] for d in sorted_days],
        "urgent": [d[1]["urgent"] for d in sorted_days],
        "phc": [d[1]["phc"] for d in sorted_days],
        "home": [d[1]["home"] for d in sorted_days],
    }


@app.get("/nurse-review-queue")
def nurse_review_queue():
    """Visits with confidence < 0.70 that need nurse review."""
    all_records = _load_all_records()
    low_conf = [
        {
            "record_id": r.get("record_id"),
            "patient_id": r.get("patient_id"),
            "symptoms": r.get("symptoms", {}),
            "triage": r.get("triage"),
            "confidence": r.get("confidence"),
            "matched_rule": r.get("matched_rule"),
            "timestamp": r.get("timestamp"),
        }
        for r in all_records
        if r.get("confidence") is not None and r.get("confidence", 1.0) < 0.70
    ]
    return {"queue": low_conf, "count": len(low_conf)}


@app.post("/nurse-review-confirm")
def nurse_review_confirm(record_id: str, override_triage: Optional[str] = None):
    """Nurse confirms or overrides a triage decision."""
    all_records = _load_all_records()
    for r in all_records:
        if r.get("record_id") == record_id:
            r["nurse_reviewed"] = True
            if override_triage:
                r["nurse_override_triage"] = override_triage
            return {"status": "reviewed", "record_id": record_id}
    raise HTTPException(status_code=404, detail="Record not found")


# ---------------------------------------------------------------------------
# Doctor Protocol Creator — add new triage protocols via dashboard form
# ---------------------------------------------------------------------------
class NewProtocolRequest(BaseModel):
    condition_name: str
    source: str = "Doctor-created"
    age_max_months: int = 0
    requires_pregnant: bool = False
    triggers: list  # [{symptom, required, weight}]
    urgent_threshold: float = 4.5
    phc_threshold: float = 2.0
    rationale: str = ""

@app.post("/create-protocol")
def create_protocol(body: NewProtocolRequest):
    """Doctor creates a new triage protocol via the dashboard form."""
    import re
    # Sanitize condition name
    safe_name = re.sub(r'[^a-z0-9_]', '_', body.condition_name.lower().strip())
    if not safe_name or len(safe_name) < 3:
        raise HTTPException(status_code=400, detail="Condition name too short")

    # Build YAML content
    yaml_lines = [
        f"# Doctor-created protocol: {body.condition_name}",
        f"# Source: {body.source}",
        f"condition: {safe_name}",
        f"version: doctor-{datetime.now().strftime('%Y%m%d')}",
        f"patient_age_max_months: {body.age_max_months}",
    ]
    if body.requires_pregnant:
        yaml_lines.append("requires_pregnant: true")
    yaml_lines.append("triggers:")
    for t in body.triggers:
        yaml_lines.append(f"  - symptom: {t.get('symptom', 'unknown')}")
        yaml_lines.append(f"    required: {'true' if t.get('required') else 'false'}")
        yaml_lines.append(f"    weight: {t.get('weight', 1.0)}")
    yaml_lines.append("risk_modifiers: []")
    yaml_lines.append("thresholds:")
    yaml_lines.append(f"  urgent_referral: {body.urgent_threshold}")
    yaml_lines.append(f"  phc_visit: {body.phc_threshold}")
    yaml_lines.append(f"  home_care: 0.0")
    yaml_lines.append(f'rationale: "{body.rationale}"')

    yaml_content = "\n".join(yaml_lines) + "\n"

    # Write YAML file
    protocols_dir = Path(__file__).parent.parent / "protocol-engine" / "protocols"
    yaml_path = protocols_dir / f"{safe_name}.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")

    # Auto-compile protocols.json
    try:
        import subprocess, sys
        compiler = Path(__file__).parent.parent / "protocol-engine" / "compile_protocols.py"
        subprocess.run([sys.executable, str(compiler)], capture_output=True, timeout=10)
    except Exception as e:
        return {"status": "saved_yaml_only", "file": str(yaml_path), "compile_error": str(e)}

    return {
        "status": "created",
        "condition": safe_name,
        "file": str(yaml_path),
        "message": f"Protocol '{body.condition_name}' added. Rebuild Android app to include it.",
    }

@app.get("/list-protocols")
def list_protocols():
    """List all available triage protocols."""
    protocols_dir = Path(__file__).parent.parent / "protocol-engine" / "protocols"
    protos = []
    for f in sorted(protocols_dir.glob("*.yaml")):
        protos.append({"name": f.stem, "file": f.name})
    return {"protocols": protos, "count": len(protos)}
