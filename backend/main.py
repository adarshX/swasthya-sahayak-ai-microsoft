"""
Swasthya Sahayak AI - FastAPI Backend
Endpoints: GET /health, POST /sync-record, GET /cases-summary
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Azure SDK imports (optional at startup; fail gracefully if not configured)
try:
    from azure.storage.blob import BlobServiceClient
    AZURE_BLOB_AVAILABLE = True
except ImportError:
    AZURE_BLOB_AVAILABLE = False

try:
    from openai import AzureOpenAI
    AZURE_OPENAI_AVAILABLE = True
except ImportError:
    AZURE_OPENAI_AVAILABLE = False

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_BLOB_CONTAINER = os.getenv("AZURE_BLOB_CONTAINER", "visit-records")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Swasthya Sahayak AI Backend", version="1.0.0")

# In-memory store used when Azure is not configured (demo fallback)
_records: list[dict] = []


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
# Helpers
# ---------------------------------------------------------------------------
def _blob_client() -> Optional["BlobServiceClient"]:
    if AZURE_BLOB_AVAILABLE and AZURE_STORAGE_CONNECTION_STRING:
        return BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    return None


def _store_record_blob(record: dict) -> None:
    client = _blob_client()
    if client is None:
        _records.append(record)
        return
    container = client.get_container_client(AZURE_BLOB_CONTAINER)
    try:
        container.create_container()
    except Exception:
        pass  # already exists
    blob_name = f"{record['record_id']}.json"
    container.upload_blob(blob_name, json.dumps(record), overwrite=True)


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


def _generate_ai_insight(records: list[dict]) -> Optional[str]:
    if not (AZURE_OPENAI_AVAILABLE and AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY):
        return None
    try:
        client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            api_version="2024-02-01",
        )
        summary_text = json.dumps(
            [{"triage": r["triage"], "symptoms": r["symptoms"]} for r in records[-20:]],
            indent=2,
        )
        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a public health analyst. "
                        "Analyze these triage records for a rural India PHC and give a 2-sentence insight "
                        "about disease patterns. Be concise and actionable."
                    ),
                },
                {"role": "user", "content": summary_text},
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
    return {"status": "ok"}


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
        _store_record_blob(record)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return SyncRecordResponse(status="stored", record_id=record["record_id"])


@app.get("/cases-summary", response_model=CasesSummaryResponse)
def cases_summary():
    records = _load_all_records()
    urgent = sum(1 for r in records if r.get("triage") == "Urgent Referral")
    phc = sum(1 for r in records if r.get("triage") == "PHC Visit")
    home = sum(1 for r in records if r.get("triage") == "Home Care")
    insight = _generate_ai_insight(records) if records else None
    return CasesSummaryResponse(
        total_cases=len(records),
        urgent_referrals=urgent,
        phc_visits=phc,
        home_care=home,
        ai_insight=insight,
    )
