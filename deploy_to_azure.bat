@echo off
REM ============================================================
REM  Swasthya Sahayak AI - One-Click Azure Deployment
REM  Deploys backend to Azure Container Apps (eastasia region)
REM
REM  Prerequisites:
REM    1. Azure CLI installed: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
REM    2. Docker Desktop running
REM    3. Logged in: az login
REM    4. .env file filled in with your Azure credentials
REM
REM  Run this from the project root directory.
REM ============================================================

setlocal enabledelayedexpansion

REM ---- CONFIGURATION — edit these if needed ----
set RESOURCE_GROUP=swasthya-rg
set LOCATION=eastasia
set ACR_NAME=swasthyaacr
set ACA_ENV=swasthya-env
set APP_NAME=swasthya-backend

REM Load .env values
call "%~dp0load_env.bat"

echo.
echo ============================================================
echo  Swasthya Sahayak AI - Azure Deployment
echo  Region: %LOCATION%
echo ============================================================
echo.

REM Step 1: Create Resource Group
echo [1/6] Creating resource group...
az group create --name %RESOURCE_GROUP% --location %LOCATION% --output none
echo       OK: %RESOURCE_GROUP%

REM Step 2: Create Azure Container Registry
echo [2/6] Creating container registry...
az acr create --resource-group %RESOURCE_GROUP% --name %ACR_NAME% --sku Basic --location %LOCATION% --admin-enabled true --output none 2>nul
if errorlevel 1 echo       (already exists, continuing)
echo       OK: %ACR_NAME%.azurecr.io

REM Step 3: Build and push Docker image using ACR Tasks (no local Docker needed)
echo [3/6] Building and pushing Docker image via ACR Tasks...
az acr build --registry %ACR_NAME% --image swasthya-backend:latest ./backend
echo       OK: image pushed

REM Step 4: Create Container Apps Environment
echo [4/6] Creating Container Apps environment...
az containerapp env create --name %ACA_ENV% --resource-group %RESOURCE_GROUP% --location %LOCATION% --output none 2>nul
if errorlevel 1 echo       (already exists, continuing)
echo       OK: %ACA_ENV%

REM Step 5: Get ACR credentials
for /f %%i in ('az acr credential show --name %ACR_NAME% --query passwords[0].value -o tsv') do set ACR_PASSWORD=%%i
set ACR_SERVER=%ACR_NAME%.azurecr.io

REM Step 6: Deploy Container App
echo [5/6] Deploying Container App...
az containerapp create ^
  --name %APP_NAME% ^
  --resource-group %RESOURCE_GROUP% ^
  --environment %ACA_ENV% ^
  --image %ACR_SERVER%/swasthya-backend:latest ^
  --registry-server %ACR_SERVER% ^
  --registry-username %ACR_NAME% ^
  --registry-password %ACR_PASSWORD% ^
  --target-port 8000 ^
  --ingress external ^
  --min-replicas 1 ^
  --max-replicas 3 ^
  --env-vars ^
    AZURE_STORAGE_CONNECTION_STRING="%AZURE_STORAGE_CONNECTION_STRING%" ^
    AZURE_BLOB_CONTAINER="%AZURE_BLOB_CONTAINER%" ^
    AZURE_OPENAI_ENDPOINT="%AZURE_OPENAI_ENDPOINT%" ^
    AZURE_OPENAI_KEY="%AZURE_OPENAI_KEY%" ^
    AZURE_OPENAI_DEPLOYMENT="%AZURE_OPENAI_DEPLOYMENT%" ^
    GEMINI_API_KEY="%GEMINI_API_KEY%" ^
  --output none 2>nul

REM If app already exists, update it
if errorlevel 1 (
    echo       (updating existing app...)
    az containerapp update ^
      --name %APP_NAME% ^
      --resource-group %RESOURCE_GROUP% ^
      --image %ACR_SERVER%/swasthya-backend:latest ^
      --output none
)

REM Step 6: Get the public URL
echo [6/6] Getting deployment URL...
for /f %%i in ('az containerapp show --name %APP_NAME% --resource-group %RESOURCE_GROUP% --query properties.configuration.ingress.fqdn -o tsv') do set APP_URL=https://%%i

echo.
echo ============================================================
echo  DEPLOYMENT COMPLETE!
echo.
echo  Backend URL:  %APP_URL%
echo  Dashboard:    %APP_URL%/
echo  Health check: %APP_URL%/health
echo.
echo  NEXT STEP — Update your Android app:
echo  Open android-app\local.properties and set:
echo    backendUrl=%APP_URL%
echo.
echo  Then rebuild the app and install on your phone.
echo ============================================================
echo.

endlocal
