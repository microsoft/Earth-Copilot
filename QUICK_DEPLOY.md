# 🚀 Quick Deploy - Earth Copilot (GitHub Actions)

**Full automated deployment to Azure via GitHub Actions**

Deploy Earth Copilot to your Azure subscription with full automation. This workflow deploys all infrastructure, backend, and frontend in < 1 hour.

---

## What You'll Need

- **Azure Account**: Active Azure subscription with **Contributor** access (or higher)
- **GitHub Account**: To fork this repository
- **Permissions**: Ability to create service principals in Azure AD (or ask your admin)

---

## Step 1: Fork the Repository

1. Go to: https://github.com/microsoft/Earth-Copilot
2. Click the **"Fork"** button at the top right
3. Choose your GitHub account as the destination
4. Wait for the fork to complete (~10 seconds)

✅ **You now have your own copy of Earth Copilot!**

---

## Step 2: Open in Your Preferred Environment

### Option A: GitHub Codespaces (Fastest - Zero Setup)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/microsoft/Earth-Copilot)

Click the badge above or:
1. Go to your forked repository
2. Click **Code** → **Codespaces** → **Create codespace on main**
3. Wait ~2 minutes for the environment to initialize
4. All CLI tools are pre-installed!

### Option B: Clone to Your Preferred IDE

```powershell
# Clone your fork
git clone https://github.com/YOUR-USERNAME/Earth-Copilot.git
cd Earth-Copilot

# Open in your preferred IDE (VS Code etc.)
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
# Authenticate with Azure CLI
az login

# Verify you're using the correct subscription
az account show --query "{Name:name, SubscriptionId:id}" -o table

# If you have multiple subscriptions, set the correct one:
az account set --subscription "YOUR-SUBSCRIPTION-ID"
```

---

## Step 5: Open GitHub Copilot in Agent Mode (Recommended)

For an AI-assisted deployment experience, use **GitHub Copilot Agent Mode** in VS Code:

1. Open VS Code with your cloned repository
2. Press `Ctrl+Shift+I` (Windows/Linux) or `Cmd+Shift+I` (macOS) to open Copilot Chat
3. Click the **Agent Mode** toggle (or type `@workspace` to start)
4. Ask Copilot to help with deployment:
   ```
   Help me deploy Earth Copilot to Azure following QUICK_DEPLOY.md
   ```

![VS Code Agent Mode](documentation/images/vsc_agentmode.png)


> 💡 **Tip**: Let Copilot guide you through the process.

---

## Step 6: Register Azure Resource Providers (One-Time Setup)

**Required for Container Apps and AI services.**

```powershell
# Register required resource providers
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.ContainerService
az provider register --namespace Microsoft.CognitiveServices
az provider register --namespace Microsoft.Maps

# Verify registration (should show "Registered")
az provider show --namespace Microsoft.App --query "registrationState"
```

⏱️ **This takes 2-3 minutes.** Wait for all to show "Registered" before proceeding.

---

## Step 7: Create Service Principal (One-Time Setup)

**This gives GitHub Actions permission to deploy to your Azure subscription.**

```powershell
# Get your subscription ID
$subscriptionId = az account show --query id -o tsv

# Create service principal with Contributor role
$sp = az ad sp create-for-rbac `
  --name "sp-earthcopilot-dev" `
  --role Contributor `
  --scopes /subscriptions/$subscriptionId `
  --sdk-auth

# IMPORTANT: Copy the JSON output above - you'll need it for GitHub secrets!

# Also grant User Access Administrator role (required for role assignments)
$appId = az ad sp list --display-name "sp-earthcopilot-dev" --query "[0].appId" -o tsv
az role assignment create `
  --assignee $appId `
  --role "User Access Administrator" `
  --scope /subscriptions/$subscriptionId
```

**Important**: Copy the entire JSON output from the first command (from `{` to `}`). You'll need this in Step 8.

⚠️ **Keep this secret safe!** Don't commit it to Git or share it publicly.

**Why two roles?**
- **Contributor**: Deploys Azure resources (Container Apps, Key Vault, etc.)
- **User Access Administrator**: Creates role assignments (ACR pull permissions, Key Vault access)

---

## Step 8: Configure GitHub Environment

### Option A: GitHub CLI (Recommended - Fastest)

Use the GitHub CLI to configure the environment and secret:

```powershell
# Navigate to your cloned repo
cd Earth-Copilot

# Create the dev environment (replace YOUR-USERNAME with your GitHub username)
gh api repos/YOUR-USERNAME/Earth-Copilot/environments/dev -X PUT

# Set the service principal secret
gh secret set AZURE_CREDENTIALS --env dev
# When prompted, paste the entire JSON output from Step 7, then press Ctrl+Z (Windows) or Ctrl+D (macOS/Linux)
```

### Option B: GitHub Web UI

**7.1 Create Environment**
1. Go to your forked repo on GitHub
2. Click **Settings** tab → **Environments** (left sidebar)
3. Click **New environment**
4. Name: `dev`
5. Click **Configure environment**

**7.2 Add Service Principal Secret**

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

> **Note:** The workflow automatically discovers resource names at runtime. Only the resource group (`rg-earthcopilot`) and region (`eastus2`) are fixed. To change these, edit the `env:` section in [.github/workflows/deploy.yml](.github/workflows/deploy.yml).

---

## Step 9: Deploy via GitHub Actions

**Now the automated part begins!** The workflow will deploy all infrastructure, backend, and frontend.

### Option A: GitHub CLI (Recommended)

```powershell
# Trigger deployment (deploys all components)
gh workflow run deploy.yml -f force_all=true

# Watch the workflow run
gh run watch
```

### Option B: GitHub Web UI

1. Go to your forked repository on GitHub
2. Click the **Actions** tab
3. Select **"Deploy Earth Copilot"** workflow
4. Click **"Run workflow"** button
5. Check **"Force deploy all components"** to deploy everything
6. Click **"Run workflow"**

![GitHub Actions Auto Deploy](documentation/images/auto_deploy_github_actions.png)

---

## Step 10: Monitor Deployment

**Expected deployment time**: 10-15 minutes

```powershell
# Watch the workflow run (if using GitHub CLI)
gh run watch

# Or view in browser
gh run list --workflow=deploy.yml
```

The workflow runs 3 jobs sequentially:
1. **Deploy Infrastructure** - All Azure resources (including AI Foundry with GPT-4o model)
2. **Deploy Backend** - Container App with FastAPI + automatic Azure OpenAI credential configuration
3. **Deploy Frontend** - App Service with React UI

---

## Step 11: Access Your Application

After deployment completes, you can find your application URLs in multiple ways:

### Option 1: GitHub Workflow Summary (Easiest)

1. Go to your repository → **Actions** tab
2. Click on the completed **"Deploy Earth Copilot"** workflow run
3. Scroll down to the **"Deployment Summary"** at the bottom
4. You'll see:
   - **Frontend URL**: `https://app-{uniqueString}.azurewebsites.net`
   - **Backend API**: `https://ca-api-{uniqueString}.eastus2.azurecontainerapps.io`
   - **API Docs**: `https://ca-api-{uniqueString}.eastus2.azurecontainerapps.io/docs`

### Option 2: Azure Portal

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to your resource group: `rg-earthcopilot`
3. Find the **App Service** (name starts with `app-`)
4. Click on it → the **URL** is shown at the top right

### Option 3: Azure CLI

```powershell
# Get frontend URL
az webapp show --name (az webapp list --resource-group rg-earthcopilot --query "[0].name" -o tsv) --resource-group rg-earthcopilot --query "defaultHostName" -o tsv

# Get backend URL
az containerapp show --name (az containerapp list --resource-group rg-earthcopilot --query "[0].name" -o tsv) --resource-group rg-earthcopilot --query "properties.configuration.ingress.fqdn" -o tsv
```

🎉 **Your Earth Copilot is now live!** Open the frontend URL in your browser to start using the app.

---

## Step 12 (Optional): Enable Microsoft Entra ID Authentication

Authentication is **not enabled by default**. To lock down access:

**Script (fastest):**
```powershell
.\scripts\enable-webapp-auth.ps1 -ResourceGroupName rg-earthcopilot -WebAppName <your-webapp-name>
```
Use the Web App name from the deployment outputs (e.g., `app-xxxxx`).

**Portal (manual):**
1. Azure Portal → App Service → your web app
2. Authentication → Add identity provider → Microsoft
3. Choose "Current tenant - Single organization" → Add → Save

---

## Step 13: Try Your First Search! 🎉

Open your frontend URL in a browser and click **Get Started** to try sample searches:

![Get Started](documentation/images/get_started.png)


**That's it!** You now have a fully deployed Earth Copilot instance. 🎉
