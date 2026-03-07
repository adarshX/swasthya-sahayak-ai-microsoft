// Swasthya Sahayak AI — Azure deployment (minimal MVP)
// Deploy with: az deployment group create --resource-group <rg> --template-file main.bicep --parameters @parameters.json

param location string = 'eastus'
param storageAccountName string
param containerAppEnvName string = 'swasthya-env'
param backendImageName string  // e.g. <registry>.azurecr.io/swasthya-backend:latest

// ------------------------------------------------------------------
// Storage Account + Blob Container
// ------------------------------------------------------------------
resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storage
  name: 'default'
}

resource visitContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'visit-records'
}

// ------------------------------------------------------------------
// Container Apps Environment
// ------------------------------------------------------------------
resource caEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: containerAppEnvName
  location: location
  properties: {}
}

// ------------------------------------------------------------------
// Backend Container App
// ------------------------------------------------------------------
resource backendApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'swasthya-backend'
  location: location
  properties: {
    managedEnvironmentId: caEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
      }
      secrets: [
        {
          name: 'storage-connection-string'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=core.windows.net'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImageName
          resources: { cpu: '0.5', memory: '1.0Gi' }
          env: [
            { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'storage-connection-string' }
            { name: 'AZURE_BLOB_CONTAINER', value: 'visit-records' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: '' }  // fill in parameters
            { name: 'AZURE_OPENAI_KEY', value: '' }       // fill in parameters
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: 'gpt-4o' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

output backendUrl string = 'https://${backendApp.properties.configuration.ingress.fqdn}'
