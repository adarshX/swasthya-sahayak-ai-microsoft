# API Specification

Base path

/api/v1

Endpoints

GET /health

Response

status ok

---

POST /sync-record

Request

patient_id
symptoms
triage
timestamp

Response

status stored

---

GET /cases-summary

Response

{
total_cases: number,
urgent_referrals: number,
phc_visits: number,
home_care: number
}