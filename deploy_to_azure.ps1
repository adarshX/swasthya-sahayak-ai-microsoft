# ============================================================
#  Swasthya Sahayak AI - Azure Deployment (PowerShell)
#  Deploys backend to Azure App Service (Python, no Docker needed)
#
#  Prerequisites:
#    1. Azure CLI installed and working (az --version)
#    2. Logged in: az login
#    3. .env file filled in with your Azure credentials
#
#  Run from project root:
#    .\deploy_to_azure.ps1
# ============================================================

$ErrorActionPreference = "Continue"

# ---- CONFIGURATION ----
$RESOURCE_GROUP = "swasthya-rg"
$RG_LOCATION    = "eastus"     # resource group is in eastus (confirmed by Azure)
$APP_LOCATION   = "eastus"     # App Service must be in a policy-allowed region
$APP_NAME       = "swasthya-backend-api"
$APP_PLAN       = "swasthya-plan"

# ---- Load .env file ----
$envFile = Join-Path $PSScriptRoot ".env"
$envVars = @{}
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line -match "^([^=]+)=(.*)$") {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
            $envVars[$key] = $val
        }
    }
    Write-Host "  Loaded .env" -ForegroundColor Green
} else {
    Write-Host "  WARNING: .env file not found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Swasthya Sahayak AI - Azure App Service Deployment"
Write-Host "  App Region: $APP_LOCATION  |  App: $APP_NAME"
Write-Host "============================================================"
Write-Host ""

# Step 1: Ensure resource group exists
Write-Host "[1/4] Ensuring resource group exists..."
az group create --name $RESOURCE_GROUP --location $RG_LOCATION --output none 2>$null
Write-Host "      OK: $RESOURCE_GROUP ($RG_LOCATION)" -ForegroundColor Green

# Step 2: Create App Service Plan (B1 = cheapest paid tier, supports Python)
Write-Host "[2/4] Creating App Service plan (B1)..."
az appservice plan create `
  --name $APP_PLAN `
  --resource-group $RESOURCE_GROUP `
  --location $APP_LOCATION `
  --sku B1 `
  --is-linux `
  --output none 2>$null
Write-Host "      OK: $APP_PLAN" -ForegroundColor Green

# Step 3: Deploy Python app directly from source (no Docker needed)
Write-Host "[3/4] Deploying Python backend to App Service..."
Write-Host "      (This may take 2-3 minutes on first deploy)"
Push-Location "$PSScriptRoot\backend"
az webapp up `
  --name $APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --plan $APP_PLAN `
  --location $APP_LOCATION `
  --runtime "PYTHON:3.12" `
  --os-type linux `
  --output none
Pop-Location
Write-Host "      OK: deployed" -ForegroundColor Green

# Step 4: Set environment variables from .env
Write-Host "[4/4] Configuring environment variables..."
$settings = @()
$requiredKeys = @(
    "AZURE_STORAGE_CONNECTION_STRING",
    "AZURE_BLOB_CONTAINER",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY"
)
foreach ($key in $requiredKeys) {
    $val = $envVars[$key]
    if ($val) {
        $settings += "$key=$val"
    }
}
# Always set startup command
$settings += "SCM_DO_BUILD_DURING_DEPLOYMENT=true"

if ($settings.Count -gt 0) {
    az webapp config appsettings set `
      --name $APP_NAME `
      --resource-group $RESOURCE_GROUP `
      --settings @settings `
      --output none
}

# Set startup command for uvicorn
az webapp config set `
  --name $APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --startup-file "uvicorn main:app --host 0.0.0.0 --port 8000" `
  --output none

Write-Host "      OK: env vars set" -ForegroundColor Green

# Get the URL
$FQDN    = az webapp show --name $APP_NAME --resource-group $RESOURCE_GROUP --query "defaultHostName" -o tsv
$APP_URL = "https://$FQDN"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host ""
Write-Host "  Backend URL:  $APP_URL"
Write-Host "  Dashboard:    $APP_URL/"
Write-Host "  Health check: $APP_URL/health"
Write-Host ""
Write-Host "  NEXT STEP - Update your Android app:"
Write-Host "  Open android-app\local.properties and set:"
Write-Host "    backendUrl=$APP_URL"
Write-Host ""
Write-Host "  Then rebuild the app and install on your phone."
Write-Host "============================================================"
Write-Host ""
