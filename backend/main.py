"""
Swasthya Sahayak AI - FastAPI Backend
Endpoints: GET /health, POST /sync-record, GET /cases-summary

AI insight supports two modes (set one in .env):
  - Direct OpenAI API:  set OPENAI_API_KEY              (no Azure approval needed)
  - Azure OpenAI:       set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_KEY
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_BLOB_CONTAINER            = os.getenv("AZURE_BLOB_CONTAINER", "visit-records")

# AI — pick whichever is set; direct OpenAI takes priority if both are set
OPENAI_API_KEY          = os.getenv("OPENAI_API_KEY", "")           # direct openai.com
AZURE_OPENAI_ENDPOINT   = os.getenv("AZURE_OPENAI_ENDPOINT", "")    # Azure OpenAI
AZURE_OPENAI_KEY        = os.getenv("AZURE_OPENAI_KEY", "")
OPENAI_MODEL            = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # used for direct API
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Swasthya Sahayak AI Backend", version="1.0.0")

_records: list[dict] = []   # in-memory fallback when Blob Storage not configured


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SyncRecordRequest(BaseModel):
    patient_id: str
    symptoms: dict
    triage: str
    timestamp: Optional[str] = None

class SyncRecordResponse(BaseModel):
    status: str
    record_id: str

class CasesSummaryResponse(BaseModel):
    total_cases: int
    urgent_referrals: int
    phc_visits: int
    home_care: int
    ai_insight: Optional[str] = None


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
# AI insight helper — supports direct OpenAI or Azure OpenAI
# ---------------------------------------------------------------------------
def _make_openai_client():
    """Returns an OpenAI-compatible client, or None if not configured."""
    if not OPENAI_AVAILABLE:
        return None, None
    if OPENAI_API_KEY:
        return OpenAI(api_key=OPENAI_API_KEY), OPENAI_MODEL
    if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY:
        return AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            api_version="2024-02-01",
        ), AZURE_OPENAI_DEPLOYMENT
    return None, None

def _generate_ai_insight(records: list[dict]) -> Optional[str]:
    client, model = _make_openai_client()
    if client is None:
        return None
    try:
        summary = json.dumps(
            [{"triage": r["triage"], "symptoms": r["symptoms"]} for r in records[-20:]],
            indent=2,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a public health analyst. Analyze these triage records from a "
                        "rural India PHC and give a 2-sentence insight about disease patterns. "
                        "Be concise and actionable for a field supervisor."
                    ),
                },
                {"role": "user", "content": summary},
            ],
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"AI insight unavailable: {str(e)}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    blob_ok = _blob_client() is not None
    _, model = _make_openai_client()
    return {
        "status": "ok",
        "blob_storage": "connected" if blob_ok else "in-memory fallback",
        "ai": model or "not configured",
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
    }
    try:
        _store_record(record)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return SyncRecordResponse(status="stored", record_id=record["record_id"])

@app.get("/cases-summary", response_model=CasesSummaryResponse)
def cases_summary():
    records = _load_all_records()
    urgent = sum(1 for r in records if r.get("triage") == "Urgent Referral")
    phc    = sum(1 for r in records if r.get("triage") == "PHC Visit")
    home   = sum(1 for r in records if r.get("triage") == "Home Care")
    return CasesSummaryResponse(
        total_cases=len(records),
        urgent_referrals=urgent,
        phc_visits=phc,
        home_care=home,
        ai_insight=_generate_ai_insight(records) if records else None,
    )