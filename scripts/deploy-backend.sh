#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# deploy-backend.sh
#
# Builds the backend container image in ACR, then either updates the existing
# Azure Container App or provisions a new one (with system-assigned managed
# identity, ACR pull, OpenAI access, KV-backed Maps secret, and the env vars
# the FastAPI app expects).
#
# Inputs (all read from env -- supplied by the GitHub Actions step or local
# caller):
#   RESOURCE_GROUP             RG containing ACR + CAE (+ optionally the CA)
#   PROJECT_NAME               e.g. planetaryexplorer-dev -- used to derive image
#                              + container-app names
#   ACR_NAME                   Azure Container Registry name
#   CAE_NAME                   Container Apps Environment name
#   CA_EXISTS                  "true" | "false"
#   CA_NAME                    Container app name (empty when CA_EXISTS=false;
#                              defaulted to ca-${PROJECT_NAME}-api)
#   ENABLE_PRIVATE_ENDPOINTS   "true" to use the dedicated VNet ACR agent pool
#   USE_MANAGED_IDENTITY       (optional) default "true". MI is the canonical
#                              auth path -- key fetch is skipped when on.
#   DEFAULT_STAC_MODE          (optional) default "public"
#
# Outputs (appended to $GITHUB_OUTPUT when running in Actions):
#   container_app_name
#   container_app_url
#
# This script is extracted from the previous inline `run: |` body of the
# "Build and Deploy Backend" workflow step, which exceeded the 21k-char
# expression limit after the recent MI/Key-Vault hardening.
# ------------------------------------------------------------------------------
set -euo pipefail

: "${RESOURCE_GROUP:?RESOURCE_GROUP env var is required}"
: "${PROJECT_NAME:?PROJECT_NAME env var is required}"
: "${ACR_NAME:?ACR_NAME env var is required}"
: "${CAE_NAME:?CAE_NAME env var is required}"
: "${CA_EXISTS:?CA_EXISTS env var is required (true|false)}"

USE_MANAGED_IDENTITY="${USE_MANAGED_IDENTITY:-true}"
DEFAULT_STAC_MODE="${DEFAULT_STAC_MODE:-public}"
ENABLE_PRIVATE_ENDPOINTS="${ENABLE_PRIVATE_ENDPOINTS:-false}"

echo " Building and deploying backend..."

cd planetary-explorer/container-app

TIMESTAMP=$(date +%Y%m%d%H%M%S)
IMAGE_TAG="$TIMESTAMP"
BUILD_TIMEOUT=1800
echo "Building image (timeout: ${BUILD_TIMEOUT}s)..."

AGENT_POOL=""
if [ "$ENABLE_PRIVATE_ENDPOINTS" = "true" ]; then
  AGENT_POOL=$(az acr agentpool list --registry "$ACR_NAME" --query "[0].name" -o tsv 2>/dev/null || echo "")
fi

if [ -n "$AGENT_POOL" ]; then
  echo "Using VNet agent pool: $AGENT_POOL"
  az acr build \
    --registry "$ACR_NAME" \
    --image "${PROJECT_NAME}-api:$IMAGE_TAG" \
    --image "${PROJECT_NAME}-api:latest" \
    --file Dockerfile.complete \
    --timeout "$BUILD_TIMEOUT" \
    --agent-pool "$AGENT_POOL" \
    ../
else
  az acr build \
    --registry "$ACR_NAME" \
    --image "${PROJECT_NAME}-api:$IMAGE_TAG" \
    --image "${PROJECT_NAME}-api:latest" \
    --file Dockerfile.complete \
    --timeout "$BUILD_TIMEOUT" \
    ../
fi

echo "Image built and pushed: ${ACR_NAME}.azurecr.io/${PROJECT_NAME}-api:$IMAGE_TAG"

ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query "loginServer" -o tsv)

# ------------------------------------------------------------------------------
# Helpers -- shared between create + update paths
# ------------------------------------------------------------------------------

# Resolve Azure OpenAI / AI Foundry account and pick best models. Sets:
#   AZURE_OPENAI_NAME, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY,
#   AZURE_OPENAI_DEPLOYMENT_NAME, AZURE_OPENAI_FAST_DEPLOYMENT,
#   AZURE_OPENAI_AVAILABLE_MODELS, USE_MANAGED_IDENTITY (may flip to true
#   when the account has disableLocalAuth=true)
resolve_openai() {
  AZURE_OPENAI_NAME=$(az cognitiveservices account list --resource-group "$RESOURCE_GROUP" --query "[?kind=='AIServices' || kind=='OpenAI'].name | [0]" -o tsv)
  AZURE_OPENAI_KEY=""
  AZURE_OPENAI_ENDPOINT=""
  AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5"
  AZURE_OPENAI_FAST_DEPLOYMENT="gpt-4o-mini"
  AZURE_OPENAI_AVAILABLE_MODELS=""

  if [ -z "$AZURE_OPENAI_NAME" ]; then
    echo "  WARNING: No Azure OpenAI / AI Foundry account found in $RESOURCE_GROUP"
    return
  fi

  AZURE_OPENAI_ENDPOINT=$(az cognitiveservices account show --name "$AZURE_OPENAI_NAME" --resource-group "$RESOURCE_GROUP" --query "properties.endpoint" -o tsv)
  LOCAL_AUTH_DISABLED=$(az cognitiveservices account show --name "$AZURE_OPENAI_NAME" --resource-group "$RESOURCE_GROUP" --query "properties.disableLocalAuth" -o tsv)
  if [ "$LOCAL_AUTH_DISABLED" = "true" ]; then
    echo "  INFO: Azure OpenAI has local auth disabled -- forcing managed identity"
    USE_MANAGED_IDENTITY="true"
  fi
  # Only fetch the plaintext key when we genuinely need it (MI off).
  if [ "$USE_MANAGED_IDENTITY" != "true" ]; then
    AZURE_OPENAI_KEY=$(az cognitiveservices account keys list --name "$AZURE_OPENAI_NAME" --resource-group "$RESOURCE_GROUP" --query "key1" -o tsv 2>/dev/null || echo "")
  fi
  AZURE_OPENAI_AVAILABLE_MODELS=$(az cognitiveservices account deployment list --name "$AZURE_OPENAI_NAME" --resource-group "$RESOURCE_GROUP" --query "[].name" -o tsv 2>/dev/null | tr '\n' ',' | sed 's/,$//')
  echo "  Azure OpenAI: $AZURE_OPENAI_NAME"
  echo "  Available Models: $AZURE_OPENAI_AVAILABLE_MODELS"

  for MODEL in gpt-5 gpt-4o gpt-4o-mini; do
    if echo ",$AZURE_OPENAI_AVAILABLE_MODELS," | grep -q ",$MODEL,"; then
      AZURE_OPENAI_DEPLOYMENT_NAME="$MODEL"
      break
    fi
  done
  echo "  Selected primary model: $AZURE_OPENAI_DEPLOYMENT_NAME"

  for FAST_MODEL in gpt-4o-mini gpt-4o; do
    if echo ",$AZURE_OPENAI_AVAILABLE_MODELS," | grep -q ",$FAST_MODEL,"; then
      AZURE_OPENAI_FAST_DEPLOYMENT="$FAST_MODEL"
      break
    fi
  done
  echo "  Selected fast model: $AZURE_OPENAI_FAST_DEPLOYMENT"
}

# Resolve Azure Maps subscription key. Sets AZURE_MAPS_KEY (may be empty).
resolve_maps() {
  AZURE_MAPS_KEY=""
  MAPS_ACCOUNT=$(az maps account list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")
  if [ -n "$MAPS_ACCOUNT" ]; then
    AZURE_MAPS_KEY=$(az maps account keys list --name "$MAPS_ACCOUNT" --resource-group "$RESOURCE_GROUP" --query "primaryKey" -o tsv)
    echo "  Azure Maps: $MAPS_ACCOUNT"
  else
    echo "  WARNING: No Azure Maps account found"
  fi
}

# Resolve MPC Pro / GeoCatalog STAC URL. Sets MPC_PRO_STAC_URL (may be empty).
# NOTE: the public endpoint is on properties.catalogUri, NOT endpointUri.
# Fallback order: (1) GeoCatalog resource in this RG, (2) current value already
# set on the container app (preserves the bicep-applied value when the catalog
# lives outside this RG), (3) empty.
resolve_geocatalog() {
  MPC_PRO_STAC_URL=""
  GEOCATALOG_NAME=$(az resource list -g "$RESOURCE_GROUP" --resource-type Microsoft.Orbital/geoCatalogs --query "[0].name" -o tsv 2>/dev/null || echo "")
  if [ -n "$GEOCATALOG_NAME" ]; then
    GEOCATALOG_URI=$(az resource show -g "$RESOURCE_GROUP" --resource-type Microsoft.Orbital/geoCatalogs --name "$GEOCATALOG_NAME" --query "properties.catalogUri" -o tsv 2>/dev/null || echo "")
    if [ -n "$GEOCATALOG_URI" ]; then
      MPC_PRO_STAC_URL="${GEOCATALOG_URI%/}/stac"
      echo "  MPC Pro GeoCatalog (in-RG): $MPC_PRO_STAC_URL"
    fi
  fi
  # Fallback: preserve whatever the bicep/infra step already set on the
  # container app. Without this, a Backend-only deploy (no GeoCatalog
  # resource in this RG) would wipe the value via --set-env-vars
  # MPC_PRO_STAC_URL="" and silently disable the Private collections panel.
  if [ -z "$MPC_PRO_STAC_URL" ] && [ "$CA_EXISTS" = "true" ]; then
    EXISTING_MPC_PRO=$(az containerapp show --name "$CA_NAME" --resource-group "$RESOURCE_GROUP" --query "properties.template.containers[0].env[?name=='MPC_PRO_STAC_URL'].value | [0]" -o tsv 2>/dev/null || echo "")
    if [ -n "$EXISTING_MPC_PRO" ]; then
      MPC_PRO_STAC_URL="$EXISTING_MPC_PRO"
      echo "  MPC Pro GeoCatalog (preserved from existing env): $MPC_PRO_STAC_URL"
    fi
  fi
}

# Migrate the Maps key into Key Vault and bind it as a Container Apps
# Key Vault reference. Sets MAPS_ENV_VALUE -- defaults to plaintext so we
# never leave the env var pointing at a non-existent secretref (KEDA fails
# to schedule replicas in that case).
configure_maps_secret() {
  local ca_name="$1"
  KV_NAME=$(az keyvault list -g "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")
  MAPS_ENV_VALUE="${AZURE_MAPS_KEY}"
  if [ -n "$KV_NAME" ] && [ -n "$AZURE_MAPS_KEY" ]; then
    echo "  Syncing Maps key to Key Vault: $KV_NAME"
    if az keyvault secret set --vault-name "$KV_NAME" --name azure-maps-subscription-key --value "$AZURE_MAPS_KEY" --output none \
       && az containerapp secret set \
            --name "$ca_name" \
            --resource-group "$RESOURCE_GROUP" \
            --secrets "azure-maps-subscription-key=keyvaultref:https://${KV_NAME}.vault.azure.net/secrets/azure-maps-subscription-key,identityref:system" \
            --output none; then
      MAPS_ENV_VALUE="secretref:azure-maps-subscription-key"
    else
      echo "  WARNING: failed to bind KV-ref secret; staying on plaintext"
    fi
  else
    echo "  No Key Vault found in RG -- using plaintext Maps key"
  fi
}

# Grant the existing system-assigned MI 'Cognitive Services OpenAI User' on
# the AI Foundry account. Idempotent; safe to re-run.
grant_openai_role() {
  local ca_name="$1"
  if [ "$USE_MANAGED_IDENTITY" != "true" ] || [ -z "$AZURE_OPENAI_NAME" ]; then
    return
  fi
  local ca_identity
  ca_identity=$(az containerapp show --name "$ca_name" --resource-group "$RESOURCE_GROUP" --query "identity.principalId" -o tsv 2>/dev/null || echo "")
  if [ -z "$ca_identity" ]; then
    return
  fi
  local openai_id
  openai_id=$(az cognitiveservices account show --name "$AZURE_OPENAI_NAME" --resource-group "$RESOURCE_GROUP" --query "id" -o tsv)
  echo "  Ensuring 'Cognitive Services OpenAI User' on $AZURE_OPENAI_NAME for MI $ca_identity"
  az role assignment create --assignee-object-id "$ca_identity" --assignee-principal-type ServicePrincipal --role "Cognitive Services OpenAI User" --scope "$openai_id" --output none 2>/dev/null || true
}

# When MI is the auth path we deliberately do NOT pass an OpenAI API key, so
# the app's MI branch is the only code path that can succeed. Sets
# OPENAI_KEY_ENV_PAIR -- pass it through to --set-env-vars / --env-vars.
compute_openai_key_pair() {
  if [ "$USE_MANAGED_IDENTITY" = "true" ]; then
    OPENAI_KEY_ENV_PAIR="AZURE_OPENAI_API_KEY="
  else
    OPENAI_KEY_ENV_PAIR="AZURE_OPENAI_API_KEY=${AZURE_OPENAI_KEY}"
  fi
}

# ------------------------------------------------------------------------------
# Update path -- existing Container App
# ------------------------------------------------------------------------------
update_container_app() {
  echo "Updating existing Container App..."
  echo "Fetching service credentials..."

  resolve_openai
  resolve_maps
  resolve_geocatalog
  configure_maps_secret "$CA_NAME"

  CA_FQDN=$(az containerapp show --name "$CA_NAME" --resource-group "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "")
  API_PUBLIC_BASE_URL="${CA_FQDN:+https://$CA_FQDN}"

  grant_openai_role "$CA_NAME"
  compute_openai_key_pair

  az containerapp update \
    --name "$CA_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --image "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-api:${IMAGE_TAG}" \
    --set-env-vars \
      "PORT=8080" \
      "STAC_API_URL=https://planetarycomputer.microsoft.com/api/stac/v1" \
      "MPC_PRO_STAC_URL=${MPC_PRO_STAC_URL}" \
      "DEFAULT_STAC_MODE=${DEFAULT_STAC_MODE}" \
      "API_PUBLIC_BASE_URL=${API_PUBLIC_BASE_URL}" \
      "CORS_ORIGINS=*" \
      "AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}" \
      "${OPENAI_KEY_ENV_PAIR}" \
      "AZURE_OPENAI_DEPLOYMENT_NAME=${AZURE_OPENAI_DEPLOYMENT_NAME}" \
      "AZURE_OPENAI_FAST_DEPLOYMENT=${AZURE_OPENAI_FAST_DEPLOYMENT}" \
      "AZURE_OPENAI_AVAILABLE_MODELS=${AZURE_OPENAI_AVAILABLE_MODELS}" \
      "USE_MANAGED_IDENTITY=${USE_MANAGED_IDENTITY}" \
      "AZURE_MAPS_SUBSCRIPTION_KEY=${MAPS_ENV_VALUE}" \
      "ENABLE_PIPELINE_V2=true" \
    --output none

  echo "Ensuring ingress port is correct (8080)..."
  az containerapp ingress update \
    --name "$CA_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --target-port 8080 \
    --output none

  echo "Container App updated with refreshed credentials"
}

# ------------------------------------------------------------------------------
# Create path -- new Container App
# ------------------------------------------------------------------------------
create_container_app() {
  echo "Creating new Container App..."
  CA_NAME="ca-${PROJECT_NAME}-api"

  resolve_openai
  resolve_maps
  resolve_geocatalog
  compute_openai_key_pair

  echo "Creating Container App with placeholder image..."
  az containerapp create \
    --name "$CA_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$CAE_NAME" \
    --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" \
    --target-port 8080 \
    --ingress external \
    --cpu 1.0 \
    --memory 2.0Gi \
    --min-replicas 1 \
    --max-replicas 3 \
    --system-assigned \
    --env-vars \
      "PORT=8080" \
      "STAC_API_URL=https://planetarycomputer.microsoft.com/api/stac/v1" \
      "MPC_PRO_STAC_URL=${MPC_PRO_STAC_URL}" \
      "DEFAULT_STAC_MODE=${DEFAULT_STAC_MODE}" \
      "CORS_ORIGINS=*" \
      "AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}" \
      "${OPENAI_KEY_ENV_PAIR}" \
      "AZURE_OPENAI_DEPLOYMENT_NAME=${AZURE_OPENAI_DEPLOYMENT_NAME}" \
      "AZURE_OPENAI_FAST_DEPLOYMENT=${AZURE_OPENAI_FAST_DEPLOYMENT}" \
      "AZURE_OPENAI_AVAILABLE_MODELS=${AZURE_OPENAI_AVAILABLE_MODELS}" \
      "USE_MANAGED_IDENTITY=${USE_MANAGED_IDENTITY}" \
      "AZURE_MAPS_SUBSCRIPTION_KEY=${AZURE_MAPS_KEY}" \
      "ENABLE_PIPELINE_V2=true" \
    --output none

  echo "Container App created with placeholder image: $CA_NAME"

  echo "Setting ingress target port to 8080..."
  az containerapp ingress update \
    --name "$CA_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --target-port 8080 \
    --output none

  CA_IDENTITY=$(az containerapp show --name "$CA_NAME" --resource-group "$RESOURCE_GROUP" --query "identity.principalId" -o tsv)
  echo "Managed Identity Principal ID: $CA_IDENTITY"

  if [ "$USE_MANAGED_IDENTITY" = "true" ] && [ -n "$AZURE_OPENAI_NAME" ]; then
    echo "Configuring managed identity for Azure OpenAI..."
    OPENAI_ID=$(az cognitiveservices account show --name "$AZURE_OPENAI_NAME" --resource-group "$RESOURCE_GROUP" --query "id" -o tsv)
    az role assignment create --assignee "$CA_IDENTITY" --role "Cognitive Services OpenAI User" --scope "$OPENAI_ID" --output none 2>/dev/null || true
    echo "Managed identity configured for Azure OpenAI"
  fi

  echo "Configuring managed identity for ACR pull..."
  ACR_ID=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query "id" -o tsv)
  az role assignment create --assignee "$CA_IDENTITY" --role "AcrPull" --scope "$ACR_ID" --output none 2>/dev/null || true
  echo "AcrPull role assigned to managed identity"

  echo "Waiting 90 seconds for role assignment propagation..."
  sleep 90

  echo "Configuring Container App to use managed identity for ACR..."
  az containerapp registry set \
    --name "$CA_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --server "$ACR_LOGIN_SERVER" \
    --identity system \
    --output none

  echo "Verifying registry authentication configuration..."
  REGISTRY_CONFIG=$(az containerapp show --name "$CA_NAME" --resource-group "$RESOURCE_GROUP" --query "properties.configuration.registries[?server=='${ACR_LOGIN_SERVER}'].identity" -o tsv)
  if [ "$REGISTRY_CONFIG" != "system" ]; then
    echo "WARNING: Registry identity not set to 'system', retrying..."
    sleep 30
    az containerapp registry set \
      --name "$CA_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --server "$ACR_LOGIN_SERVER" \
      --identity system \
      --output none
  fi
  echo "Registry authentication verified: using system-assigned managed identity"

  echo "Verifying AcrPull role assignment..."
  ROLE_EXISTS=$(az role assignment list --assignee "$CA_IDENTITY" --role "AcrPull" --scope "$ACR_ID" --query "[0].id" -o tsv 2>/dev/null || echo "")
  if [ -z "$ROLE_EXISTS" ]; then
    echo "WARNING: AcrPull role not found, waiting additional 60 seconds..."
    sleep 60
    az role assignment create --assignee "$CA_IDENTITY" --role "AcrPull" --scope "$ACR_ID" --output none 2>/dev/null || true
  fi
  echo "AcrPull role verified for managed identity"

  # Migrate the Maps key into Key Vault (system MI now exists) and bind it
  # as a KV-ref secret. Also populate API_PUBLIC_BASE_URL so backend-generated
  # absolute URLs work.
  KV_NAME=$(az keyvault list -g "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")
  MAPS_ENV_VALUE="${AZURE_MAPS_KEY}"
  if [ -n "$KV_NAME" ] && [ -n "$AZURE_MAPS_KEY" ]; then
    echo "  Granting Container App MI 'Key Vault Secrets User' on $KV_NAME..."
    KV_ID=$(az keyvault show --name "$KV_NAME" --query id -o tsv)
    az role assignment create --role "Key Vault Secrets User" --assignee-object-id "$CA_IDENTITY" --assignee-principal-type ServicePrincipal --scope "$KV_ID" --output none 2>/dev/null || true
    echo "  Syncing Maps key to Key Vault: $KV_NAME"
    az keyvault secret set --vault-name "$KV_NAME" --name azure-maps-subscription-key --value "$AZURE_MAPS_KEY" --output none || echo "  WARNING: failed to write KV secret"
    az containerapp secret set \
      --name "$CA_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --secrets "azure-maps-subscription-key=keyvaultref:https://${KV_NAME}.vault.azure.net/secrets/azure-maps-subscription-key,identityref:system" \
      --output none && MAPS_ENV_VALUE="secretref:azure-maps-subscription-key" || echo "  WARNING: failed to bind KV-ref secret; staying on plaintext"
  fi

  CA_FQDN=$(az containerapp show --name "$CA_NAME" --resource-group "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "")
  API_PUBLIC_BASE_URL="${CA_FQDN:+https://$CA_FQDN}"

  echo "Updating Container App with actual image from ACR..."
  az containerapp update \
    --name "$CA_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --image "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-api:${IMAGE_TAG}" \
    --set-env-vars \
      "AZURE_MAPS_SUBSCRIPTION_KEY=${MAPS_ENV_VALUE}" \
      "API_PUBLIC_BASE_URL=${API_PUBLIC_BASE_URL}" \
    --output none

  echo "Container App updated with image: ${ACR_LOGIN_SERVER}/${PROJECT_NAME}-api:${IMAGE_TAG}"
}

# ------------------------------------------------------------------------------
# Dispatch
# ------------------------------------------------------------------------------
if [ "$CA_EXISTS" = "true" ]; then
  update_container_app
else
  create_container_app
fi

# Emit outputs for downstream steps when running under GitHub Actions.
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "container_app_name=$CA_NAME" >> "$GITHUB_OUTPUT"
  CONTAINER_APP_URL=$(az containerapp show --name "$CA_NAME" --resource-group "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)
  echo "container_app_url=https://$CONTAINER_APP_URL" >> "$GITHUB_OUTPUT"
  echo "Backend deployed to: https://$CONTAINER_APP_URL"
else
  CONTAINER_APP_URL=$(az containerapp show --name "$CA_NAME" --resource-group "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)
  echo "Backend deployed to: https://$CONTAINER_APP_URL"
fi
