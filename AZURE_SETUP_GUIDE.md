# Earth Copilot - Azure Services Setup Guide

This guide walks you through creating the required Azure services for Earth Copilot using the Azure Portal UI.

## 📋 **Prerequisites**

- **Azure Subscription** with appropriate permissions
- **Azure Portal Access** - [portal.azure.com](https://portal.azure.com)
- **Resource Group** - Create one for organizing all Earth Copilot services

## 🏗️ **Step 1: Create Resource Group**

1. **Navigate to Resource Groups**
   - Go to [Azure Portal](https://portal.azure.com)
   - Search for "Resource groups" in the top search bar
   - Click **"Create"**

2. **Configure Resource Group**
   - **Subscription**: Select your Azure subscription
   - **Resource group name**: `earth-copilot-rg` (or your preferred name)
   - **Region**: Choose a region close to your users (e.g., East US, West Europe)
   - Click **"Review + create"** → **"Create"**

## 🤖 **Step 2: Azure AI Foundry (Core AI Services)**

Azure AI Foundry provides the core AI capabilities including GPT-5 and model routing.

### **Create AI Hub**
1. **Navigate to Azure AI Studio**
   - Go to [ai.azure.com](https://ai.azure.com)
   - Sign in with your Azure account
   - Click **"Create hub"**

2. **Configure AI Hub**
   - **Hub name**: `earth-copilot-ai-hub`
   - **Subscription**: Select your subscription
   - **Resource group**: Select `earth-copilot-rg`
   - **Location**: Same region as your resource group
   - **Connect Azure AI services**: Create new
   - **Connect Azure AI Search**: Skip for now (we'll create separately)
   - Click **"Create"**

### **Deploy GPT Model**
1. **Access Model Deployments**
   - In your AI Hub, go to **"Models + endpoints"**
   - Click **"Deploy model"** → **"Deploy base model"**

2. **Select and Deploy GPT Model**
   - Search for **"GPT-5"** or **"GPT-4o"** (use latest available)
   - Select the latest available version
   - Click **"Deploy"**

3. **Configure Deployment**
   - **Deployment name**: `gpt-5-deployment` (save this name for later)
   - **Model version**: Use default latest
   - **Deployment type**: Standard
   - **Tokens per minute rate limit**: 30K (adjust as needed)
   - Click **"Deploy"**

4. **Get Deployment Details**
   - Once deployed, note down:
     - **Endpoint URL** (for AZURE_OPENAI_ENDPOINT)
     - **API Key** (for AZURE_OPENAI_API_KEY)
     - **Deployment Name** (for AZURE_OPENAI_DEPLOYMENT_NAME)

## 🗺️ **Step 3: Azure Maps (Geographic Services)**

Azure Maps provides geocoding and location resolution services.

1. **Create Azure Maps Account**
   - In Azure Portal, search for **"Azure Maps"**
   - Click **"Create"**

2. **Configure Maps Account**
   - **Subscription**: Your subscription
   - **Resource group**: `earth-copilot-rg`
   - **Name**: `earth-copilot-maps`
   - **Location**: Same region as resource group
   - **Pricing tier**: S1 (recommended for production)
   - Click **"Review + create"** → **"Create"**

3. **Get API Key**
   - Go to your Maps account → **"Authentication"**
   - Copy the **Primary Key** (for AZURE_MAPS_SUBSCRIPTION_KEY)

## ⚡ **Step 4: Azure Function App (Backend API)**

The Function App hosts your backend API endpoints.

1. **Create Function App**
   - Search for **"Function App"** in Azure Portal
   - Click **"Create"**

2. **Configure Function App**
   - **Subscription**: Your subscription
   - **Resource group**: `earth-copilot-rg`
   - **Function App name**: `earth-copilot-functions` (must be globally unique)
   - **Runtime stack**: Python
   - **Version**: 3.11
   - **Region**: Same region as resource group
   - **Operating System**: Linux
   - **Hosting**: Consumption (Serverless)

3. **Review and Create**
   - Click **"Review + create"** → **"Create"**
   - Wait for deployment to complete

4. **Configure App Settings**
   - Go to your Function App → **"Configuration"** → **"Application settings"**
   - Add these settings (click **"+ New application setting"** for each):
     ```
     AZURE_OPENAI_ENDPOINT = <your-ai-hub-endpoint>
     AZURE_OPENAI_API_KEY = <your-ai-hub-api-key>
     AZURE_OPENAI_DEPLOYMENT_NAME = <your-deployment-name>
     AZURE_MAPS_SUBSCRIPTION_KEY = <your-maps-key>
     ```
   - Click **"Save"**

## 🔍 **Step 5: Azure AI Search (Enhanced Query Capabilities)**

Azure AI Search provides vector search and document indexing.

1. **Create Search Service**
   - Search for **"Azure AI Search"** in Azure Portal
   - Click **"Create"**

2. **Configure Search Service**
   - **Subscription**: Your subscription
   - **Resource group**: `earth-copilot-rg`
   - **Service name**: `earth-copilot-search` (must be globally unique)
   - **Location**: Same region as resource group
   - **Pricing tier**: Basic (sufficient for development)
   - Click **"Review + create"** → **"Create"**

3. **Get Service Details**
   - Go to your Search service → **"Overview"**
   - Note the **Service URL** and **Admin keys**

## 🔧 **Step 6: Configure Environment Variables**

Create a `.env` file in your Earth Copilot project root with these values:

```env
# Azure OpenAI (from AI Foundry)
AZURE_OPENAI_ENDPOINT=https://your-ai-hub.openai.azure.com/
AZURE_OPENAI_API_KEY=your-ai-hub-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5-deployment

# Azure Maps
AZURE_MAPS_SUBSCRIPTION_KEY=your-maps-primary-key

# Azure AI Search
AZURE_SEARCH_SERVICE_ENDPOINT=https://earth-copilot-search.search.windows.net
AZURE_SEARCH_ADMIN_KEY=your-search-admin-key

# Function App (for production deployment)
AZURE_FUNCTION_APP_NAME=earth-copilot-functions
```

## ✅ **Step 7: Verify Setup**

1. **Test Azure OpenAI Connection**
   ```bash
   # Use the provided tool
   python tools/check_azure_openai.py
   ```

2. **Verify All Services**
   - ✅ AI Foundry hub created with GPT-5 deployment
   - ✅ Azure Maps account with API key
   - ✅ Function App ready for deployment
   - ✅ AI Search service created
   - ✅ Environment variables configured