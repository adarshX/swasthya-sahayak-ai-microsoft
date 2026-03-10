"""
Swasthya Sahayak AI - FastAPI Backend
======================================
Endpoints:
  GET  /            -> Supervisor Dashboard (HTML)
  GET  /health      -> Service status JSON
  POST /sync-record -> Store a triage visit from Android app
  GET  /records     -> Recent visit records (for dashboard table)
  GET  /cases-summary -> Aggregate stats + AI insight

AI insight supports two modes (set one in .env):
  - Direct OpenAI API:  set OPENAI_API_KEY
  - Azure OpenAI:       set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_KEY
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Auto-load .env from parent directory (works whether run via uvicorn or start_backend scripts)
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass  # python-dotenv not installed, rely on env vars set externally

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
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
# Config from environment (loaded above via dotenv)
# ---------------------------------------------------------------------------
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_BLOB_CONTAINER            = os.getenv("AZURE_BLOB_CONTAINER", "visit-records")

OPENAI_API_KEY          = os.getenv("OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT   = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY        = os.getenv("AZURE_OPENAI_KEY", "")
OPENAI_MODEL            = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
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
# AI insight helper
# ---------------------------------------------------------------------------
def _make_openai_client():
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
                        "You are a public health analyst supporting ASHA/ANM field workers in rural India. "
                        "Analyze these triage records and provide a 2-sentence insight about disease patterns "
                        "or alert trends. Be concise and actionable for a PHC supervisor."
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
# Supervisor Dashboard HTML
# ---------------------------------------------------------------------------
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Swasthya Sahayak – Supervisor Dashboard</title>
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

    /* Stat cards */
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

    /* AI Insight box */
    .insight {
      background: #1565C0; color: white;
      border-radius: 14px; padding: 20px 24px; margin-bottom: 24px;
      box-shadow: 0 2px 8px rgba(21,101,192,0.25);
      min-height: 72px; display: flex; align-items: center; gap: 16px;
    }
    .insight .icon { font-size: 28px; flex-shrink: 0; }
    .insight .text { font-size: 15px; line-height: 1.6; }
    .insight .text strong { display: block; font-size: 11px; letter-spacing: 0.08em; opacity: 0.7; margin-bottom: 4px; }

    /* Records table */
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

    .badge-urgent { background: #FFEBEE; color: #C62828; border-radius: 20px; padding: 3px 10px; font-size: 12px; font-weight: 700; }
    .badge-phc    { background: #FFF3E0; color: #E65100; border-radius: 20px; padding: 3px 10px; font-size: 12px; font-weight: 700; }
    .badge-home   { background: #E8F5E9; color: #2E7D32; border-radius: 20px; padding: 3px 10px; font-size: 12px; font-weight: 700; }

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
  <div class="stats" id="stats">
    <div class="card total"><div class="label">TOTAL VISITS</div><div class="value" id="total">—</div></div>
    <div class="card urgent"><div class="label">🚨 URGENT REFERRAL</div><div class="value" id="urgent">—</div></div>
    <div class="card phc"><div class="label">⚠️ PHC VISIT</div><div class="value" id="phc">—</div></div>
    <div class="card home"><div class="label">✅ HOME CARE</div><div class="value" id="home">—</div></div>
  </div>

  <div class="insight" id="insight-box">
    <div class="icon">🤖</div>
    <div class="text"><strong>AI PATTERN INSIGHT (Azure OpenAI)</strong><span id="insight-text">Loading…</span></div>
  </div>

  <div class="table-wrap">
    <div class="table-header">
      <h2>Recent Field Visits</h2>
      <small id="last-updated">—</small>
    </div>
    <table>
      <thead>
        <tr>
          <th>TIME</th>
          <th>PATIENT ID</th>
          <th>TRIAGE DECISION</th>
          <th>SYMPTOMS REPORTED</th>
        </tr>
      </thead>
      <tbody id="records-body">
        <tr><td colspan="4" class="empty">Loading records…</td></tr>
      </tbody>
    </table>
  </div>
  <p class="refresh-note">Auto-refreshes every 20 seconds</p>
</div>

<script>
function badgeClass(triage) {
  if (triage === 'Urgent Referral') return 'badge-urgent';
  if (triage === 'PHC Visit') return 'badge-phc';
  return 'badge-home';
}

function symptomTags(symptoms) {
  const map = {
    age_under_5: '👶 Child <5yrs',
    fever: '🌡️ Fever',
    fast_breathing: '💨 Fast Breathing'
  };
  return Object.entries(symptoms)
    .filter(([,v]) => v === true)
    .map(([k]) => `<span class="symptom-tag">${map[k] || k}</span>`)
    .join('') || '<span style="color:#BDBDBD">No symptoms</span>';
}

function formatTime(ts) {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    return d.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true,
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return ts; }
}

async function refresh() {
  try {
    const [summary, records] = await Promise.all([
      fetch('/cases-summary').then(r => r.json()),
      fetch('/records?limit=20').then(r => r.json())
    ]);

    document.getElementById('total').textContent  = summary.total_cases;
    document.getElementById('urgent').textContent = summary.urgent_referrals;
    document.getElementById('phc').textContent    = summary.phc_visits;
    document.getElementById('home').textContent   = summary.home_care;

    const insight = summary.ai_insight;
    document.getElementById('insight-text').textContent =
      insight || 'No AI insight yet — add more records and configure Azure OpenAI.';

    const tbody = document.getElementById('records-body');
    if (!records.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty">No records yet. Open the Android app and run a triage to see data here.</td></tr>';
    } else {
      tbody.innerHTML = records.slice().reverse().map(r => `
        <tr>
          <td>${formatTime(r.timestamp)}</td>
          <td style="font-family:monospace;font-size:12px">${(r.patient_id||'').slice(0,8)}…</td>
          <td><span class="${badgeClass(r.triage)}">${r.triage}</span></td>
          <td>${symptomTags(r.symptoms || {})}</td>
        </tr>`).join('');
    }

    document.getElementById('last-updated').textContent =
      'Last updated: ' + new Date().toLocaleTimeString('en-IN');
  } catch(e) {
    document.getElementById('insight-text').textContent = 'Connection error: ' + e.message;
  }
}

refresh();
setInterval(refresh, 20000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Supervisor dashboard — open in browser to see real-time case monitoring."""
    return DASHBOARD_HTML


@app.get("/health")
def health():
    blob_ok = _blob_client() is not None
    _, model = _make_openai_client()
    return {
        "status": "ok",
        "version": "1.0.0",
        "blob_storage": "azure-blob" if blob_ok else "in-memory",
        "ai_model": model or "not configured",
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
    }
    try:
        _store_record(record)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return SyncRecordResponse(status="stored", record_id=record["record_id"])


@app.get("/records")
def records(limit: int = 50):
    """Returns recent visit records (newest last). Used by the supervisor dashboard."""
    all_records = _load_all_records()
    # Sort by timestamp descending, return last `limit`
    sorted_records = sorted(
        all_records,
        key=lambda r: r.get("timestamp", ""),
    )
    return sorted_records[-limit:]


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
