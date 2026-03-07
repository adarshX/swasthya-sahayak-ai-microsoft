# Azure Architecture

Services Used

Azure Container Apps

Hosts backend API and intelligence service.

Azure Blob Storage

Stores visit records.

Azure AI Speech

Handles voice recognition.

Azure OpenAI

Used by Case Intelligence Service.

Generates explanations and analyzes aggregated cases.

Azure Monitor

Captures logs and performance metrics.

Service Architecture

Android App
|
| POST /sync-record
|
Backend API (Container Apps)
|
|---- Blob Storage (record persistence)
|
|---- Case Intelligence Service
|      Uses Azure OpenAI
|
|---- Supervisor Summary API

Example endpoint

GET /cases-summary

Returns aggregated statistics for monitoring.