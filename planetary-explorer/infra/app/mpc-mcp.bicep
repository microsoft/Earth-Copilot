// Internal-only Container App that runs Microsoft's upstream
// ``geocatalog-mcp-server`` (the MPC Pro MCP server, distributed via VS
// Code extension ``ms-planetarycomputer.mpc-pro-mcp-tools``). Consumed
// by the Planetary Explorer backend container as an MCP client.
//
// Auth model (verified against ms-planetarycomputer.mpc-pro-mcp-tools
// v1.0.9 bundle): the server acquires a bearer token against the
// data-plane audience ``https://geocatalog.spatio.azure.com/.default``.
// Access to a specific GeoCatalog instance is granted **inside that
// instance** (data-plane RBAC, configured via the MPC Pro portal or
// the GeoCatalog Admin API) -- *not* via ARM role assignments. So the
// only ARM-level grant we need here is AcrPull on the registry.

param name string
param location string = resourceGroup().location
param tags object = {}

param containerAppsEnvironmentName string
param containerRegistryName string

@description('Container image for the MPC MCP sidecar (e.g. planetary-explorer-mpc-mcp:v1.0.9).')
param imageName string

@description('Default GeoCatalog URL the sidecar should advertise to clients that omit ``geocatalog_uri`` on tool calls. Optional. Per-call override is always supported.')
param defaultGeoCatalogUri string = ''

@description('Default storage account hint passed to ingest tools as ``STORAGE_ACCOUNT_NAME``. Optional; per-call override always supported.')
param defaultStorageAccountName string = ''

@description('Default container hint passed to ingest tools as ``CONTAINER_NAME``. Optional; per-call override always supported.')
param defaultContainerName string = ''

@description('Min replicas. Catalog calls cache well; 1 covers normal load. Set to 0 only if you accept cold-start on every flip.')
@minValue(0)
@maxValue(10)
param minReplicas int = 1

@description('Max replicas. Tune up if you observe queueing during bulk inventory refreshes.')
@minValue(1)
@maxValue(30)
param maxReplicas int = 3

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' existing = {
  name: containerAppsEnvironmentName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

// User-assigned managed identity created BEFORE the Container App so we
// can grant AcrPull on the registry and have RBAC propagate before the
// container app's first image-pull attempt. Using a system-assigned
// identity here causes a chicken-and-egg: the principalId only exists
// after the app is created, but the app can't be created because the
// initial revision pull fails with 401 (no role yet). ARM rolls back
// the never-created role assignment and the deployment fails with
// "ContainerAppOperationError: Operation expired".
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${name}'
  location: location
  tags: tags
}

// AcrPull is created on the UAMI -- this happens BEFORE the container
// app references the identity, so by the time ACA tries to pull the
// image the role is already in place.
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(uami.id, containerRegistry.id, 'AcrPull')
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
    )
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource app 'Microsoft.App/containerApps@2023-05-01' = {
  name: name
  location: location
  tags: union(tags, { 'azd-service-name': 'mpc-mcp' })
  // Bind the pre-created UAMI alongside the system-assigned identity.
  // System-assigned stays so the principalId output (used for the
  // post-deploy GeoCatalog grant) is unchanged for any operator who
  // already wired it up via the original system-assigned principal.
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${uami.id}': {}
    }
  }
  // Explicit dependsOn ensures the role assignment lands before ACA
  // probes the registry. Bicep would normally infer this from the
  // registries[].identity reference below, but being explicit keeps
  // the ordering guarantee in front of future refactors.
  dependsOn: [
    acrPullRole
  ]
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      // Internal-only ingress -- reachable from inside the env, not
      // the public internet. The backend container app talks to this
      // over ``https://<fqdn>`` resolved by the env's internal DNS.
      ingress: {
        external: false
        targetPort: 8080
        allowInsecure: false
        transport: 'auto'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          // Reference the UAMI by resourceId. ACA exchanges this
          // identity for an ACR token at pull time; the AcrPull role
          // we created above is what makes the exchange return 200.
          identity: uami.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'mpc-mcp'
          image: '${containerRegistry.properties.loginServer}/${imageName}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              // The upstream binary inspects this env var when picking
              // a transport. ``streamable-http`` exposes the MCP
              // protocol on the HTTP server we ingress on.
              name: 'MCP_TRANSPORT'
              value: 'streamable-http'
            }
            {
              name: 'MCP_HTTP_HOST'
              value: '0.0.0.0'
            }
            {
              name: 'MCP_HTTP_PORT'
              value: '8080'
            }
            {
              // Upstream reads ``GEOCATALOG_URI`` as the default when
              // a tool call doesn't supply ``geocatalog_uri``. Leaving
              // this empty is fine -- callers pass the URI explicitly.
              name: 'GEOCATALOG_URI'
              value: defaultGeoCatalogUri
            }
            {
              name: 'STORAGE_ACCOUNT_NAME'
              value: defaultStorageAccountName
            }
            {
              name: 'CONTAINER_NAME'
              value: defaultContainerName
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8080
              }
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/healthz'
                port: 8080
              }
              periodSeconds: 10
              failureThreshold: 3
              initialDelaySeconds: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

// AcrPull is granted to the UAMI declared at the top of this file --
// the role is created BEFORE the container app references the identity,
// avoiding the chicken-and-egg failure mode where ACA's first image
// pull 401s while waiting for a not-yet-propagated role.

// ---------------------------------------------------------------------
// Post-deploy grant (manual, by design)
// ---------------------------------------------------------------------
//
// MPC Pro GeoCatalog access is *data-plane* RBAC, not ARM RBAC. After
// this module deploys, take the ``principalId`` output and add it as a
// member of the GeoCatalog instance via the MPC Pro UI (or the
// GeoCatalog Admin API) with the role you want (typically ``Reader``
// for read-only catalog routing, ``Contributor`` if you also want the
// agentic ingest tools to work).
//
// There is intentionally no Bicep-level role assignment here because:
//   1. The GeoCatalog instance is not an ARM resource that accepts
//      ``Microsoft.Authorization/roleAssignments`` for catalog access.
//   2. The data-plane grant has its own audit trail inside the
//      GeoCatalog and shouldn't be duplicated in ARM.
//
// See ``planetary-explorer/mpc-mcp-sidecar/README.md`` for the exact
// post-deploy steps and a validation curl that confirms the grant
// landed.

output name string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn
output uri string = 'https://${app.properties.configuration.ingress.fqdn}'
output principalId string = app.identity.principalId
