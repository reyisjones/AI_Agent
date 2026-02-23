/*
  AI Agent — Azure Container Apps deployment
  ──────────────────────────────────────────
  Resources created:
    - Container Registry (ACR)
    - Container Apps Environment (with Log Analytics)
    - Azure Cache for Redis
    - Azure Database for PostgreSQL Flexible Server
    - Azure Key Vault (stores secrets; managed identity access)
    - Container App (the agent)
    - Managed Identity (for Key Vault + ACR pull)

  Deploy:
    az deployment group create \
      --resource-group rg-ai-agent \
      --template-file infra/main.bicep \
      --parameters @infra/parameters.json
*/

targetScope = 'resourceGroup'

// ── Parameters ────────────────────────────────────────────────────────────────
@description('Base name used for all resource names.')
param appName string = 'aiagent'

@description('Azure region.')
param location string = resourceGroup().location

@description('Container image tag to deploy.')
param imageTag string = 'latest'

@description('OpenAI API key (stored in Key Vault, not in Bicep state).')
@secure()
param openAiApiKey string

@description('Postgres admin password.')
@secure()
param postgresAdminPassword string = newGuid()

@description('Allowed HTTP domains for the http_request tool (comma-separated).')
param allowedHttpDomains string = 'httpbin.org,jsonplaceholder.typicode.com,api.openai.com'

@description('OpenAI model name.')
param openAiModel string = 'gpt-4o'

// ── Variables ──────────────────────────────────────────────────────────────────
var uniqueSuffix = uniqueString(resourceGroup().id)
var acrName = '${appName}acr${uniqueSuffix}'
var kvName = '${appName}kv${take(uniqueSuffix,8)}'
var laName = '${appName}-logs'
var envName = '${appName}-env'
var appName2 = '${appName}-app'
var redisName = '${appName}-redis'
var pgServerName = '${appName}-pg-${take(uniqueSuffix,6)}'
var identityName = '${appName}-identity'
var imageName = '${acrName}.azurecr.io/${appName}:${imageTag}'

// ── Managed Identity ───────────────────────────────────────────────────────────
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

// ── Container Registry ─────────────────────────────────────────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

// Grant AcrPull to managed identity
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identity.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Key Vault ──────────────────────────────────────────────────────────────────
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// Grant Key Vault Secrets User to managed identity
resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, identity.id, 'SecretsUser')
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6') // Key Vault Secrets User
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Store OpenAI key in Key Vault
resource openAiSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'openai-api-key'
  properties: {
    value: openAiApiKey
  }
}

// Store Postgres password in Key Vault
resource pgSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'postgres-admin-password'
  properties: {
    value: postgresAdminPassword
  }
}

// ── Log Analytics ──────────────────────────────────────────────────────────────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: laName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ── Container Apps Environment ─────────────────────────────────────────────────
resource caEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ── Azure Cache for Redis ──────────────────────────────────────────────────────
resource redis 'Microsoft.Cache/redis@2023-08-01' = {
  name: redisName
  location: location
  properties: {
    sku: { name: 'Basic', family: 'C', capacity: 0 }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
  }
}

var redisConnStr = '${redis.properties.hostName}:${redis.properties.sslPort},password=${redis.listKeys().primaryKey},ssl=True,abortConnect=False'

resource redisSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'redis-connection-string'
  properties: { value: redisConnStr }
}

// ── PostgreSQL Flexible Server ─────────────────────────────────────────────────
resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: pgServerName
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    administratorLogin: 'agentadmin'
    administratorLoginPassword: postgresAdminPassword
    version: '16'
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
  }
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: pg
  name: 'agentdb'
}

var pgDsn = 'postgresql+asyncpg://agentadmin:${postgresAdminPassword}@${pg.properties.fullyQualifiedDomainName}:5432/agentdb?ssl=require'

resource pgDsnSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'postgres-dsn'
  properties: { value: pgDsn }
}

// ── Container App ──────────────────────────────────────────────────────────────
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName2
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    environmentId: caEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: identity.id
        }
      ]
      secrets: [
        {
          name: 'openai-api-key'
          keyVaultUrl: openAiSecret.properties.secretUri
          identity: identity.id
        }
        {
          name: 'redis-conn'
          keyVaultUrl: redisSecret.properties.secretUri
          identity: identity.id
        }
        {
          name: 'postgres-dsn'
          keyVaultUrl: pgDsnSecret.properties.secretUri
          identity: identity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: appName2
          image: imageName
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'OPENAI_API_KEY',          secretRef: 'openai-api-key' }
            { name: 'REDIS_URL',                secretRef: 'redis-conn' }
            { name: 'POSTGRES_DSN',             secretRef: 'postgres-dsn' }
            { name: 'OPENAI_MODEL',             value: openAiModel }
            { name: 'APP_ENV',                  value: 'production' }
            { name: 'LOG_LEVEL',                value: 'INFO' }
            { name: 'ALLOWED_HTTP_DOMAINS',     value: allowedHttpDomains }
            { name: 'DOCS_PATH',                value: '/app/docs/' }
            { name: 'SERVICE_NAME',             value: 'ai-agent' }
            { name: 'AZURE_KEYVAULT_URL',       value: kv.properties.vaultUri }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/api/v1/health', port: 8000 }
              initialDelaySeconds: 15
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/api/v1/health', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 5
        rules: [
          {
            name: 'http-scale'
            http: { metadata: { concurrentRequests: '20' } }
          }
        ]
      }
    }
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────────
output agentUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output acrLoginServer string = acr.properties.loginServer
output keyVaultUrl string = kv.properties.vaultUri
output containerAppName string = containerApp.name
