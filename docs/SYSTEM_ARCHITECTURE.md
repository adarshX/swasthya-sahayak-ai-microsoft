# System Architecture

Architecture Type

Hybrid Edge + Cloud

Edge Layer

Android Device

Components

Voice capture
Symptom structuring
Protocol triage engine
Local record storage
Sync queue

All clinical triage decisions run locally on device.

This ensures the system works even without internet connectivity.

Cloud Layer

Azure Backend

Components

Backend API service
Record storage
Case intelligence service
Supervisor summary endpoint

Data Flow

Offline Mode

Worker enters symptoms
Protocol engine evaluates locally
Triage recommendation generated
Record saved locally

Online Mode

Records queued for synchronization
Backend API receives records
Records stored in Azure Blob Storage

Case Intelligence Service

Aggregated cases are analyzed using Azure OpenAI.

Purpose

Improve explanation clarity
Identify patterns across cases
Generate guidance insights

Supervisor Summary

Backend exposes endpoint:

GET /cases-summary

Returns:

total cases
urgent referrals
phc visits
home care

This enables public health monitoring dashboards.

Azure Services

Azure Container Apps
Backend hosting

Azure Blob Storage
Record storage

Azure AI Speech
Voice recognition

Azure OpenAI
Explanation generation and case analysis

Azure Monitor
Application logs