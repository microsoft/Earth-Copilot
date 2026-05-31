# Quick Deploy - Planetary Explorer (GitHub Actions)

**Full automated deployment to Azure via GitHub Actions**

Deploy Planetary Explorer to your Azure subscription with full automation. This workflow deploys all infrastructure, backend, and frontend in < 1 hour.

> **Prefer a one-command local deploy?** After `az login`, run
> `./deploy-infrastructure.ps1` from the repo root. It auto-picks a region
> (preflight verifies AOAI `gpt-4o`, Container Apps, ACR availability), defaults
> all opt-ins OFF, and accepts the same toggles via env vars: `MPC_PRO`,
> `PRIVATE`, `FABRIC`, `WEATHER_MODELS`, `LOCATION`. The GitHub Actions flow below is the
> recommended path for shared / repeatable environments.

### What Gets Deployed

Planetary Explorer is a multi-agent geospatial AI system powered by **Azure AI Foundry**, **Microsoft Agent Framework (MAF)**, **Semantic Kernel**, **Azure AI Agent Service**, and **Model Context Protocol (MCP)**.

**Core stack (always deployed):**
- **Azure AI Foundry** - Model deployment for AI agents (GPT-5 or model of choice)
- **Azure AI Agent Service** - Multi-turn tool orchestration for GEOINT agents (Hub + Project)
- **Azure Container Apps** - Backend API hosting the full agent surface (STAC, Clarifier, Load, Raster Sampling, Contextual, Vision, Terrain, Mobility, Comparison, Building Damage, Extreme Weather, Site Intel, Resilience, Forecast)
- **Azure App Service (Web App)** - React frontend hosting
- **Azure Maps** - Geocoding and map visualization
- **Azure AI Search** - Vector search for private data catalogs (RAG) and BCP / permitting precedent docs
- **Azure Storage** - Blob storage for raster intermediate results and ingest
- **Azure Key Vault** - Secrets and connection strings
- **Azure Container Registry** - Docker image storage
- **Log Analytics + Application Insights** - Monitoring, traces, container logs

**Opt-in (off by default):**
- **VNet + Private Endpoints + Private DNS** - `-EnablePrivateEndpoints`
- **MPC Pro MCP Sidecar** (Container App) - `-EnableMpcPro`
- **Weather Stub Server** (Container App, CPU-only Aurora + Earth-2 FCN stub) - `-EnableWeatherModels`
- **Microsoft Fabric F2 Capacity** - `-EnableFabric`
- **MCP Server** (Container App, for VS Code / Claude clients) - workflow input `deploy_mcp_server`

**Data sources (external, no setup required):**
- **Microsoft Planetary Computer STAC API** - 130+ global satellite collections
- **NASA VEDA STAC API** - Earth science datasets from NASA missions


## Deployment Overview

These instructions work for any Azure subscription:

| Aspect | Value | Who Provides It |
|--------|-------|-----------------|
| Source repo to fork | `microsoft/Planetary-Explorer` | OSS |
| Azure subscription | User's own | User |
| Service principal | Created by user | User |
| GitHub secret | `AZURE_CREDENTIALS` | User |
| Resource group | `rg-planetaryexplorer` (default) | Workflow (`vars.RESOURCE_GROUP`) |
| Location | `eastus2` (default; local script auto-picks via preflight if not set) | Workflow (`vars.LOCATION`) |
| Project name prefix | `planetaryexplorer` (default) | Workflow (`vars.PROJECT_NAME`) |
| Resource names | Auto-generated unique | Workflow (dynamic) |
| Private endpoints | **OFF** by default | Workflow (opt-in: `enable_private_endpoints`) |
| MPC Pro | **OFF** by default | Workflow input `enable_mpc_pro` + `mpc_pro_stac_url` (overrides `main.parameters.json`) |
| Fabric capacity | **OFF** by default | Workflow inputs `enable_fabric` + `deploy_fabric_capacity` (BYO via `fabric_capacity_resource_id`) |
| Forecast Agent weather models | **OFF** by default | Workflow input `deploy_weather_stub` (CPU mock) or `aurora_endpoint_url` / `earth2_fcn_endpoint_url` / `mai_weather_endpoint_url` overrides |
| MCP server Container App | **OFF** by default | Workflow input `deploy_mcp_server` + `mcp_image_name` |
| Authentication | **ON** if `AUTH_CLIENT_ID` secret is set | User creates app registration + sets secret. Override per-run with `disable_auth=true`. |
| **Auto-deploy on push** | **OFF** by default | Set repo variable `ENABLE_AUTO_DEPLOY=true` (Settings → Variables → Actions) to let pushes to `main`/`dev` trigger the workflow. Without it, only `workflow_dispatch` runs the deploy — so a fork can review code freely without burning Azure cost on every commit. |

---

## What You'll Need

- **Azure Account**: Active Azure subscription
- **GitHub Account**: To fork this repository
- **Azure CLI 2.51+**: Required for Azure authentication and resource provider registration. The `--json-auth` flag in Step 7 was added in 2.51 — run `az upgrade` if you're on an older version. ([Install in Step 3](#step-3-install-required-cli-tools))
- **GitHub CLI**: Optional but recommended for easier secret configuration ([Install in Step 3](#step-3-install-required-cli-tools))

### Required Azure Permissions

You need these permissions (all configured manually before deploying):

| Permission Type | Required Role | Purpose | Required? |
|-----------------|---------------|---------|-----------|
| **Azure AD / Entra ID** | "Users can register applications" = Yes (default) OR **Application Developer** role | Create service principal (Step 7) + app registration (Step 8.3) | **Yes** |
| **Azure Subscription** | **Contributor** + **User Access Administrator** (or **Owner**) | Deploy resources + assign roles | **Yes** |

> **Heads up**
> - **`User Access Administrator`** is *not* granted to a default Contributor. Step 7's second `az role assignment create` will fail unless you're a subscription **Owner**. If you're not, ask your subscription Owner to run that single command for you.
> - **"Users can register applications"** is disabled in many enterprise tenants. If so, both Step 7 (`az ad sp create-for-rbac`) and Step 8.3 (creating the app registration) will fail with *Insufficient privileges*. Check with your tenant admin before starting.
> - **GPT-5 quota** is *not* granted by default — most subscriptions need to either request `GlobalStandard` quota in advance, or deploy with `-f deploy_gpt5=false` (the app then uses GPT-4o, which every Azure OpenAI region has).
> - **Region quota** — the GitHub Actions path defaults to `eastus2`. If your subscription has no AOAI / Container Apps quota in eastus2, set `vars.LOCATION` in Settings → Environments → dev to a region where you do (e.g. `eastus`, `swedencentral`, `westus3`). The local `deploy-infrastructure.ps1` path auto-picks a region for you via preflight.

---

## Step 1: Fork the Repository

1. Go to: https://github.com/microsoft/Planetary-Explorer
2. Click the **"Fork"** button at the top right
3. Choose your GitHub account as the destination
4. Wait for the fork to complete (~10 seconds)


**You now have your own copy of Planetary Explorer!**

---

## Step 2: Clone and Open in VS Code

```powershell
# Clone your fork
git clone https://github.com/YOUR-USERNAME/Planetary-Explorer.git
cd Planetary-Explorer

# Open in VS Code
code .
```

Replace `YOUR-USERNAME` with your GitHub username.

---

## Step 3: Install Required CLI Tools

### Azure CLI

**Windows**:
```powershell
winget install Microsoft.AzureCLI
```

**macOS**:
```bash
brew install azure-cli
```

**Linux**:
```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

Restart your terminal and verify:
```powershell
az --version
```

### GitHub CLI (Optional but Recommended)

The GitHub CLI makes it easier to configure secrets, trigger deployments, and monitor workflows.

**Windows**:
```powershell
winget install GitHub.cli
```

**macOS**:
```bash
brew install gh
```

**Linux**:
```bash
# Debian/Ubuntu
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update && sudo apt install gh
```

Restart your terminal and authenticate:
```powershell
gh --version
gh auth login
```

Follow the prompts to authenticate with your GitHub account.

---

## Step 4: Authenticate to Azure

```powershell
# Authenticate with Azure CLI (opens browser)
az login

# Verify you're using the correct subscription
az account show --query "{Name:name, SubscriptionId:id, TenantId:tenantId}" -o table

# If you have multiple subscriptions, set the correct one:
az account set --subscription "YOUR-SUBSCRIPTION-ID"

# If you have multiple tenants and need a specific one:
az login --tenant YOUR-TENANT-ID
```

---

## Step 5: Open GitHub Copilot in Agent Mode (Recommended)

For an AI-assisted deployment experience, use **GitHub Copilot Agent Mode** in VS Code:

1. Press `Ctrl+Shift+I` (Windows/Linux) or `Cmd+Shift+I` (macOS) to open Copilot Chat
2. Click the **Agent Mode** toggle (or type `@workspace` to start)
3. Ask Copilot to help with deployment:
   ```
   Help me deploy Planetary Explorer to Azure following QUICK_DEPLOY.md
   ```

![VS Code Agent Mode](documentation/images/vsc_agentmode.png)

---

## Step 6: Register Azure Resource Providers (One-Time Setup)

**Required for Container Apps, AI services, and Agent Service.**

```bash
# Register required resource providers
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.ContainerService
az provider register --namespace Microsoft.CognitiveServices
az provider register --namespace Microsoft.Maps
az provider register --namespace Microsoft.MachineLearningServices   # Required for AI Foundry Hub/Project (Agent Service)

# Verify registration (should show "Registered")
az provider show --namespace Microsoft.App --query "registrationState"
az provider show --namespace Microsoft.MachineLearningServices --query "registrationState"
```

**This takes 2-3 minutes.** Wait for all to show "Registered" before proceeding.

---

## Step 7: Create Service Principal (One-Time Setup)

**This gives GitHub Actions permission to deploy to your Azure subscription.**

### Create the Service Principal

```powershell
# Get your subscription ID
$subscriptionId = az account show --query id -o tsv

# Create service principal with Contributor role
az ad sp create-for-rbac `
  --name "sp-planetaryexplorer-dev" `
  --role Contributor `
  --scopes /subscriptions/$subscriptionId `
  --json-auth

# IMPORTANT: Copy the JSON output above - you'll need it for GitHub secrets!

# Also grant User Access Administrator role (required for role assignments)
$appId = az ad sp list --display-name "sp-planetaryexplorer-dev" --query "[0].appId" -o tsv
az role assignment create `
  --assignee $appId `
  --role "User Access Administrator" `
  --scope /subscriptions/$subscriptionId
```

**Important**: Copy the entire JSON output from the first command (from `{` to `}`). You'll need this in Step 8.

**Keep this secret safe!** Don't commit it to Git or share it publicly.

**Why two roles?**
- **Contributor**: Deploys Azure resources (Container Apps, Key Vault, etc.)
- **User Access Administrator**: Creates role assignments (ACR pull permissions, Key Vault access)

---

## Step 8: Configure GitHub Environment

### Option A: GitHub CLI (Recommended - Fastest)

Use the GitHub CLI to configure the environment and secret:

```powershell
# Navigate to your cloned repo
cd Planetary-Explorer

# Create the dev environment (replace YOUR-USERNAME with your GitHub username)
gh api repos/YOUR-USERNAME/Planetary-Explorer/environments/dev -X PUT

# Set the service principal secret
gh secret set AZURE_CREDENTIALS --env dev
# When prompted, paste the entire JSON from Step 7 (curly braces and all), press Enter,
# then on a NEW empty line press Ctrl+Z then Enter (Windows PowerShell) or Ctrl+D (macOS/Linux).
```

### Option B: GitHub Web UI

**8.1 Create Environment**
1. Go to your forked repo on GitHub
2. Click **Settings** tab → **Environments** (left sidebar)
3. Click **New environment**
4. Name: `dev`
5. Click **Configure environment**

**8.2 Add Service Principal Secret**

Use the JSON output from **Step 7** (the service principal you created).

1. Scroll to **Environment secrets**
2. Click **Add secret**
3. Name: `AZURE_CREDENTIALS`
4. Value: Paste the **entire JSON** from Step 7 (including curly braces)
5. Click **Add secret**

The JSON should look like this:
```json
{
  "clientId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "clientSecret": "your-secret-here",
  "subscriptionId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "tenantId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  ...
}
```

> **Note:** The workflow automatically discovers resource names at runtime. To customize defaults, set GitHub Environment variables (`vars.RESOURCE_GROUP`, `vars.LOCATION`, `vars.PROJECT_NAME`) in Settings → Environments → dev. No workflow file edits needed.

### 8.3 Enable Authentication (Recommended)

The pipeline automatically configures Entra ID authentication (EasyAuth) on **both the frontend and backend** — but it needs an **app registration** that you create once manually.

- **Frontend** (App Service): Redirects unauthenticated users to the Microsoft login page
- **Backend** (Container App): Returns `401 Unauthorized` for API requests without a valid token (health and docs endpoints are excluded)
- The frontend automatically forwards the user's identity token on every API call

1. Go to [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** → **App registrations** → **New registration**
2. **Name**: `PlanetaryExplorer-Auth` (or any name you prefer)
3. **Supported account types**: Single tenant (this organization only)
4. **Redirect URI**: Leave blank (the pipeline sets this automatically)
5. Click **Register**
6. Copy the **Application (client) ID** from the overview page

Then set it as a GitHub secret:

```powershell
# Set the app registration client ID
gh secret set AUTH_CLIENT_ID --env dev
# Paste the Application (client) ID and press Enter, then on a NEW empty line
# press Ctrl+Z then Enter (Windows PowerShell) or Ctrl+D (macOS/Linux).
```

> **Why manual?** Creating app registrations requires Microsoft Graph API permissions (`Application.ReadWrite.All`) — these are directory-level permissions separate from Azure RBAC. A standard deployment service principal (Contributor + User Access Administrator) doesn't have them. 

> **Skip this step** if you want to deploy without authentication first and add it later.

> **AADSTS50011 after deploy?** If sign-in fails with *"The redirect URI ... does not match"*, the workflow tried to patch your app registration but the deployment SP lacked `Application.ReadWrite.OwnedBy`. Fix manually with:
> ```powershell
> az ad app update --id <AUTH_CLIENT_ID> --web-redirect-uris "https://<your-webapp>.azurewebsites.net/.auth/login/aad/callback"
> ```
> Then refresh the sign-in page (Entra propagation < 1 min).

---

## Step 9: Deploy via GitHub Actions

**Now the automated part begins!** The default deployment is **public** with Entra ID authentication (if `AUTH_CLIENT_ID` is set in Step 8.3).

### Option A: GitHub CLI (Recommended)

```powershell
# Trigger deployment — public by default; auth enabled if AUTH_CLIENT_ID is set (Step 8.3).
# deploy_gpt5=false uses GPT-4o instead (available in every AOAI region, no special quota).
gh workflow run deploy.yml -f force_all=true -f deploy_gpt5=false

# Watch the workflow run
gh run watch
```

If you've already requested and been granted `GlobalStandard` quota for GPT-5, drop the flag (it defaults to `true`):

```powershell
gh workflow run deploy.yml -f force_all=true
```

> **Want a fully private deployment?** For production lockdown with VNet, private endpoints, and ACR agent pool:
> ```powershell
> gh workflow run deploy.yml -f force_all=true -f enable_private_endpoints=true
> ```
> This adds VNet integration, private DNS zones, and a VNet-integrated ACR build agent. First deploy takes ~30-45 min.

> Flags can be combined: `-f enable_private_endpoints=true -f deploy_gpt5=false`

### Option B: GitHub Web UI

1. Go to your forked repository on GitHub
2. Click the **Actions** tab
3. Select **"Deploy Planetary Explorer"** workflow
4. Click **"Run workflow"** button
5. Check **"Force deploy all components"** to deploy everything
6. Check **"Enable private endpoints"** for a fully private/VNet deployment (optional)
7. Uncheck **"Deploy GPT-5 model"** if your subscription lacks `GlobalStandard` quota
8. Click **"Run workflow"**

### Optional Integrations (Off by Default)

The default deployment enables only the **public Microsoft Planetary Computer STAC API** — no extra Azure cost, no extra setup. The following integrations are wired up but **disabled by default** because they require resources you may not have:

| Toggle | Default | What it adds | When to enable |
|---|---|---|---|
| `enable_mpc_pro` + `mpc_pro_stac_url` | `false` | Routes STAC searches through a **private GeoCatalog** (MPC Pro) you own. UI exposes an "MPC Pro" toggle that is locked when disabled. | You have a `Microsoft.Orbital/geoCatalogs` instance with private collections. |
| `enable_fabric` + `deploy_fabric_capacity` (or `fabric_capacity_resource_id` for BYO) | `false` | Provisions (or attaches BYO) a **Microsoft Fabric F-SKU capacity** + wires the API to a Fabric lakehouse. Powers **Site Intel** and **Resilience** agents. | You want Site Intel / Resilience to read live Delta tables (power, water, candidate sites, facilities, supply edges). |
| `deploy_weather_stub` + `weather_stub_image_name` | `false` | Provisions a CPU-only Container App that mocks Aurora + Earth-2 FCN scoring endpoints so the **Forecast Agent** works end-to-end without GPU quota. Image must be built and pushed to ACR first (see `planetary-explorer/weather-stub-server/`). | You want a demo-quality Forecast Agent without requesting `Standard_NC24ads_A100_v4` quota. |
| `aurora_endpoint_url` / `earth2_fcn_endpoint_url` / `mai_weather_endpoint_url` | empty | Production overrides for the **Forecast Agent**. When set, the backend points at your real Foundry endpoints instead of the stub. MAI Weather has no stub equivalent. | You have GPU quota + a deployed Foundry managed online endpoint (Aurora / Earth-2) or are allow-listed for MAI Weather. |
| `deploy_mcp_server` + `mcp_image_name` | `false` | Deploys a separate **MCP server** Container App exposing every Planetary Explorer agent as MCP tools for VS Code Copilot / Claude Desktop / other MCP clients. | You want to call Planetary Explorer from an MCP-compatible AI assistant. |
| `disable_auth` | `false` | Skips the EasyAuth configuration step — app deploys publicly. Dev/test only. | You want a quick public demo and accept that anyone with the URL can use it. |

Flip them on directly from the workflow_dispatch inputs — no file edits needed:

```powershell
# Enable MPC Pro and point at your GeoCatalog
gh workflow run deploy.yml -f force_all=true `
  -f enable_mpc_pro=true `
  -f mpc_pro_stac_url="https://<gc>.<region>.geocatalog.spatio.azure.com/stac"

# Provision a new Fabric F2 capacity (powers Site Intel + Resilience)
gh workflow run deploy.yml -f force_all=true `
  -f enable_fabric=true `
  -f deploy_fabric_capacity=true

# BYO existing Fabric capacity instead
gh workflow run deploy.yml -f force_all=true `
  -f enable_fabric=true `
  -f fabric_capacity_resource_id="/subscriptions/.../resourceGroups/.../providers/Microsoft.Fabric/capacities/myCapacity"

# Stand up the CPU weather stub so the Forecast Agent works without GPU quota
gh workflow run deploy.yml -f force_all=true `
  -f deploy_weather_stub=true `
  -f weather_stub_image_name="planetary-explorer-weather-stub:latest"

# Point Forecast Agent at real Foundry endpoints (any subset; missing ones fall back to stub or skip)
gh workflow run deploy.yml -f force_all=true `
  -f aurora_endpoint_url="https://aurora-endpoint.region.inference.ml.azure.com/score" `
  -f earth2_fcn_endpoint_url="https://earth2-fcn.region.inference.ml.azure.com/score" `
  -f mai_weather_endpoint_url="https://mai-weather.region.inference.ml.azure.com/score"

# Deploy the MCP server Container App
gh workflow run deploy.yml -f force_all=true `
  -f deploy_mcp_server=true `
  -f mcp_image_name="planetary-explorer-mcp:latest"
```

For values that don't have a workflow input (e.g. `fabricAdministrators`, `fabricWorkspaceId`, `fabricLakehouseId`), edit `planetary-explorer/infra/main.parameters.json` before re-running:

```jsonc
{
  "fabricSkuName":         { "value": "F2" },
  "fabricAdministrators":  { "value": ["you@contoso.com"] },
  "fabricWorkspaceId":     { "value": "<workspace-guid>" },
  "fabricLakehouseId":     { "value": "<lakehouse-guid>" }
}
```

The container exposes the effective config at `GET /api/config` → `features: { mpcPublic, mpcPro, fabric }` so the UI hides/locks controls accordingly. No code changes needed — set the toggles, redeploy, the UI adapts.

---

## Step 10: Monitor Deployment

**Expected deployment time**: ~20-30 minutes on the first run (cold ACR build + AI Foundry Hub/Project + Agent Service capability host wiring), ~10-15 minutes on subsequent runs. ~30-45 minutes on the first deploy with `enable_private_endpoints=true` (adds ACR VNet-integrated agent pool provisioning).

> **If the workflow fails on `Microsoft.CognitiveServices/accounts/deployments`** with a quota or capacity error, your chosen region doesn't have the model SKU available. Either re-run with `-f deploy_gpt5=false`, or change `vars.LOCATION` (Settings → Environments → dev) to a region with quota and re-run.

```powershell
# Watch the workflow run (if using GitHub CLI)
gh run watch

# Or view in browser
gh run list --workflow=deploy.yml
```

The workflow runs these jobs:
1. **Detect Changes** — Determines which components need deployment (or deploys all if `force_all=true`)
2. **Deploy Infrastructure** — All Azure resources including AI Foundry (model of your choice + Agent Service Hub/Project), Container Apps Environment, ACR, Azure Maps, AI Search, Key Vault, Storage, Log Analytics, and optional VNet + Private Endpoints / Fabric capacity / Weather stub / MCP server
3. **Deploy Backend** — Container App with FastAPI + the full agent surface: Clarifier (L1+L2), Action Router, Query Splitter, Load Agent, Raster Sampling, Contextual, Vision, Terrain, Mobility, Comparison, Building Damage, Extreme Weather, **Site Intel** (MAF), **Resilience** (MAF), **Forecast** (MAF; Aurora + Earth-2 FCN + MAI Weather). Credentials wired via managed identity.
4. **Deploy Frontend** — App Service with React UI (Public/Pro STAC toggle, GEOINT module selectors, Site Intel + Resilience + Forecast panels)
5. **Enable Agent Service** — Enables Agent Service capability hosts on AI Foundry so GEOINT agents can use multi-turn tool orchestration (fallback: `scripts\enable-agent-service.ps1`)
6. **Configure Auth** — Configures Entra ID EasyAuth on both frontend (login redirect) and backend Container App (Return401) using the app registration from Step 8.3 (skipped if `AUTH_CLIENT_ID` secret is not set or `disable_auth=true`)
7. **Summary** — Prints deployment status, endpoints, auth configuration, and Agent Service status

![GitHub Actions Auto Deploy](documentation/images/auto_deploy_github_actions.png)
**Example Resource Group:**

![Azure Resource Group](documentation/images/resources.png)

**Example Azure AI Foundry Deployment:**

![Azure AI Foundry Deployment](documentation/images/foundry.png)

---

## Step 11: Access Your Application

After deployment completes, you can find your application URLs in multiple ways:

### Option 1: GitHub Workflow Summary 

1. Go to your repository → **Actions** tab
2. Click on the completed **"Deploy Planetary Explorer"** workflow run
3. Scroll down to the **"Deployment Summary"** at the bottom
4. The summary lists your **Frontend URL**, **Backend API URL**, and **API Docs URL**

> All resource names are auto-generated with a unique suffix based on your subscription. The exact URLs are known after deployment.

### Option 2: Azure Portal

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to your resource group: `rg-planetaryexplorer`
3. Find the **App Service** (name starts with `app-`)
4. Click on it → the **URL** is shown at the top right

### Option 3: Azure CLI

```powershell
# Get frontend URL
az webapp show --name (az webapp list --resource-group rg-planetaryexplorer --query "[0].name" -o tsv) --resource-group rg-planetaryexplorer --query "defaultHostName" -o tsv

# Get backend URL
az containerapp show --name (az containerapp list --resource-group rg-planetaryexplorer --query "[0].name" -o tsv) --resource-group rg-planetaryexplorer --query "properties.configuration.ingress.fqdn" -o tsv
```

**Your Planetary Explorer is now live!** Open the frontend URL and click **Get Started** to try sample searches. The rest of the steps in this guide are optional.

![Get Started](documentation/images/get_started.png)

---

## Step 12 (Optional): Restrict Access to Specific Users

If you completed Step 8.3, authentication is enabled and **all users in your tenant** can sign in. To restrict access to only specific users:

### Option A: Azure Portal (Recommended — No Graph Permissions Needed)

1. Go to [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** → **Enterprise applications**
2. Search for your app registration name (e.g., `PlanetaryExplorer-Auth`)
3. **Properties** → Set **Assignment required?** to **Yes** → **Save**
4. **Users and groups** → **Add user/group** → Add the users who should have access

**Example — Adding 3 authorized users:**

| Step | Action |
|------|--------|
| 1 | In **Enterprise applications**, click your app (`PlanetaryExplorer-Auth`) |
| 2 | Left menu → **Properties** → toggle **Assignment required?** to **Yes** → click **Save** |
| 3 | Left menu → **Users and groups** → click **+ Add user/group** |
| 4 | Click **Users** → **None Selected** → search for and select each user by email: |
|   | `alice@contoso.com` |
|   | `bob@contoso.com` |
|   | `charlie@contoso.com` |
| 5 | Click **Select** → click **Assign** |

Once **Assignment required** is set to **Yes**, only users you explicitly add in step 4 can sign in. Everyone else in the tenant gets an `AADSTS50105` error. This applies to both the frontend login and backend API calls since they share the same app registration.

### Option B: Set Before Deploying

Set the `AUTH_AUTHORIZED_USERS` variable before running the workflow. The pipeline will attempt to configure user restrictions (requires the service principal to have Microsoft Graph `AppRoleAssignment.ReadWrite.All` permission, which most SPs don't have by default).

```powershell
# Comma-separated list of user principal names (UPNs)
gh variable set AUTH_AUTHORIZED_USERS --env dev --body "user1@yourdomain.com,user2@yourdomain.com"
```

### If You Skipped Step 8.3 (No Auth Yet)

You can enable auth at any time by completing Step 8.3 and re-running the workflow:

```powershell
# Set the secret, then redeploy
gh secret set AUTH_CLIENT_ID --env dev
gh workflow run deploy.yml -f force_all=true
```

---

## Step 13 (Optional): Integrate with Microsoft Copilot Studio

**Why?** Your analysts already live in **Microsoft Teams** and **M365 Copilot**. Instead of switching to a separate web app, Copilot Studio lets them search satellite imagery and analyze terrain directly from their chat window — no context switching. It's the fastest path to adoption for organizations already on Microsoft 365.

Copilot Studio acts as a **distribution channel** — all AI intelligence stays in your deployed backend. No code changes needed. The backend already supports the **M365 Copilot audience** in its auth layer.

| What You Get | How It Works |
|---|---|
| Chat with Planetary Explorer in Microsoft Teams | Copilot Studio agent calls your Container App API through a custom connector |
| Use Planetary Explorer as a declarative agent inside M365 Copilot | M365 Copilot routes natural-language queries to the same backend |
| Multi-turn conversations with session memory | Backend preserves chat session state across turns |

**Getting started:** Create a Copilot Studio agent with a custom connector pointing to your deployed backend API. See [Microsoft Copilot Studio documentation](https://learn.microsoft.com/microsoft-copilot-studio/) for setup instructions.

> **Requirements:** Copilot Studio license (included in M365 E3/E5 or standalone) + deployed Planetary Explorer backend.

---

## Step 14 (Optional): Connect via MCP Server

**Why?** If your developers use **GitHub Copilot**, **Claude**, or other AI coding assistants, the MCP (Model Context Protocol) server lets them query satellite data and analyze terrain **directly from their IDE** — no browser, no API docs, no curl commands. The AI assistant discovers Planetary Explorer's capabilities automatically and calls them in context.

| What You Get | How It Works |
|---|---|
| Query satellite imagery from VS Code Copilot Chat | MCP tools with dynamic capability discovery |
| Multi-turn conversations with context memory | MCP preserves session state across turns |
| Works with any MCP-compatible client | GitHub Copilot, Claude Desktop, custom agents |
| Domain-specific expert prompts | Built-in geospatial analyst personas |

**Follow the full guide:** [planetary-explorer/mcp-server/README.md](planetary-explorer/mcp-server/README.md)

> **Requirements:** Deployed Planetary Explorer backend + an MCP-compatible client (GitHub Copilot in VS Code, Claude Desktop, etc.).

---

## Appendix A: Local One-Command Deploy (alternative to GitHub Actions)

For developers who don't want to set up GitHub Actions, `deploy-infrastructure.ps1`
delivers the same stack from a local shell. Defaults: **public, all opt-ins off,
auto-picked region** (preflight verifies AOAI `gpt-4o`, Container Apps, ACR, and
any enabled opt-ins are available in the chosen region).

```powershell
# Public, minimal stack, region auto-selected
.\deploy-infrastructure.ps1

# Override via env vars (CI / one-click deploy friendly)
$env:MPC_PRO = 'true'; $env:FABRIC = 'true'; $env:PRIVATE = 'true'
.\deploy-infrastructure.ps1

# Or via flags
.\deploy-infrastructure.ps1 -EnableMpcPro -EnableFabric -EnablePrivateEndpoints

# Pin a region (skips preflight)
.\deploy-infrastructure.ps1 -Location eastus2
```

| Flag (switch / env)                        | Default | Effect |
|--------------------------------------------|---------|--------|
| `-EnableMpcPro` / `MPC_PRO`                | off     | UI surfaces the MPC Pro toggle (requires your GeoCatalog URL in `mpcProStacUrl`). |
| `-EnablePrivateEndpoints` / `PRIVATE`      | off     | VNet + private endpoints + private DNS. |
| `-EnableFabric` / `FABRIC`                 | off     | Provisions a Fabric F2 capacity (~$262/mo). |
| `-EnableWeatherModels` / `WEATHER_MODELS`  | off     | Deploys the CPU-only weather stub (`planetary-explorer/weather-stub-server/`) and wires the Forecast Agent's Aurora + Earth-2 FCN providers to it — no GPU quota needed. Override with real Foundry endpoints via `auroraEndpointUrl` / `earth2FcnEndpointUrl` / `maiWeatherEndpointUrl` Bicep params when you have GPU quota. |

---

## Appendix B: Multiple Environments (prod + dev)

Planetary Explorer supports any number of side-by-side environments. Each environment
lives in its own resource group (`rg-<envName>`) with its own resource names
(derived from `uniqueString(subscription, envName, location)`), so prod and dev
never collide. Tear down one environment without touching the others.

```powershell
# Deploy prod (default — creates rg-planetaryexplorer)
.\deploy-infrastructure.ps1 `
    -EnvironmentName planetaryexplorer `
    -EnableAuthentication `
    -MicrosoftEntraClientId "<prod-app-reg-client-id>" `
    -MicrosoftEntraTenantId "<tenant-id>"

# Deploy dev from a feature branch (creates rg-planetaryexplorer-dev, separate Entra app reg)
git checkout experimental/v2-pipeline
.\deploy-infrastructure.ps1 `
    -EnvironmentName planetaryexplorer-dev `
    -EnableAuthentication `
    -MicrosoftEntraClientId "<dev-app-reg-client-id>" `
    -MicrosoftEntraTenantId "<tenant-id>"

# Tear down only the dev environment when you're done
az group delete --name rg-planetaryexplorer-dev --yes --no-wait
```

After infra is provisioned, push the matching container image into each
environment's ACR and run the per-env backend / frontend deploy scripts. The
existing `deploy-backend.ps1` / `deploy-frontend.ps1` scripts auto-discover the
resource group from `rg-<envName>` — just pass `-EnvironmentName` to point them
at the right one.

> **OSS contributors:** the same script works for any environment name. A new
> user running `.\deploy-infrastructure.ps1` (no args) gets a single
> `rg-planetaryexplorer` environment — no surprise resources. They can opt into a
> second environment any time by re-running with `-EnvironmentName <name>`.

---

## Appendix C: Extend & Integrate

After deploying the core application, you can extend Planetary Explorer with these optional integrations:

| Integration | What It Does | Enable | Guide |
|-------------|-------------|--------|-------|
| **MPC Pro / GeoCatalog** | Same chat, your tenant's STAC. Mirror MPC collections + ingest private items; agents see both Public and Pro with one toggle. Provenance reported per response. | `-EnableMpcPro` + `mpcProStacUrl=<url>` | [Planetary Computer Pro](https://planetarycomputer.microsoft.com/docs/concepts/what-is-pc-pro/) |
| **Microsoft Fabric** | Powers Site Intel + Resilience over your Lakehouse Delta tables (sites, facilities, supply edges, infrastructure). Falls back to bundled seed data if not configured. | `-EnableFabric` + workspace env vars | [Microsoft Fabric](https://learn.microsoft.com/fabric/) |
| **Weather Models (Forecast Agent)** | Wires Aurora + Earth-2 FCN + MAI Weather into the Forecast ensemble. CPU-only stub is included; swap in Foundry endpoints when you have GPU quota. | `-EnableWeatherModels` or set `auroraEndpointUrl` / `earth2FcnEndpointUrl` / `maiWeatherEndpointUrl` | `planetary-explorer/weather-stub-server/` |
| **Copilot Studio + M365** | Chat in **Microsoft Teams** (bot) or **M365 Copilot** (declarative agent / connector). Backend already supports the M365 audience in the auth layer. | Register Teams bot / declarative agent | [Microsoft Copilot Studio](https://learn.microsoft.com/microsoft-copilot-studio/) |
| **MCP Server** | Expose every Planetary Explorer agent as MCP tools for VS Code GitHub Copilot, Claude Desktop, and other MCP-compatible clients. | Deploy `mcp-server/` | [Setup Guide](planetary-explorer/mcp-server/README.md) |
| **ArcGIS** | Connect Esri ArcGIS for enterprise GIS workflows and map services. | Configure custom connector | [Esri ArcGIS](https://www.esri.com/) |

