# Earth Copilot Web UI

This directory contains the React frontend for Earth Copilot, designed to be deployed to Azure App Service.

## 🏗️ Project Structure

```
web-ui/
├── src/
│   ├── components/        # React components
│   │   ├── Chat.tsx       # Main chat interface
│   │   ├── MapView.tsx    # Azure Maps integration
│   │   ├── Header.tsx     # Navigation header
│   │   └── ...
│   ├── services/          # API integration services
│   ├── styles/            # Global styles
│   ├── App.tsx            # Main application component
│   └── main.tsx           # Entry point
├── public/                # Static assets
├── package.json           # Node.js dependencies
├── vite.config.ts         # Vite build configuration
├── tsconfig.json          # TypeScript configuration
└── index.html             # HTML template
```

## 🚀 Deployment

### Azure App Service Details
- **Service Name:** Automatically generated (e.g., `app-xxxxx`)
- **Region:** East US 2 (default)
- **Type:** App Service (Node.js/Static Web App)

> **Note:** For full deployment instructions, see [QUICK_DEPLOY.md](../../QUICK_DEPLOY.md)

### Local Development

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Configure environment variables:**
   - Copy `.env.example` to `.env`
   - Fill in required values (Azure Maps keys, API endpoints, etc.)

3. **Run development server:**
   ```bash
   npm run dev
   ```
   The app will be available at `http://localhost:5173`

### Build for Production

```bash
npm run build
```

This creates optimized production files in the `dist/` directory.

### Deploy to Azure App Service

#### Option 1: Using GitHub Actions (Recommended)

Follow [QUICK_DEPLOY.md](../../QUICK_DEPLOY.md) for fully automated deployment.

#### Option 2: Using Azure CLI

```bash
# Build the application
npm run build

# Deploy to App Service (replace with your resource names)
az webapp up --name YOUR-WEBAPP-NAME --resource-group rg-earthcopilot --location eastus2
```

#### Option 3: Using VS Code Azure Extension

1. Install the Azure App Service extension
2. Right-click on the `dist` folder
3. Select "Deploy to Web App"
4. Choose your deployed Web App

## 🔧 Configuration

### Environment Variables

Create a `.env` file in this directory with:

```bash
VITE_API_BASE_URL=https://<your-container-app>.azurecontainerapps.io
VITE_AZURE_MAPS_SUBSCRIPTION_KEY=<your-azure-maps-key>
VITE_AZURE_MAPS_CLIENT_ID=<your-azure-maps-client-id>
```

> **Note:** The GitHub Actions deployment automatically configures these values.

### Azure App Service Configuration

After deployment, configure these application settings in Azure Portal:

1. Go to Azure Portal → App Service → your web app
2. Navigate to Configuration → Application settings
3. Add the following:
   - `VITE_API_BASE_URL`
   - `VITE_AZURE_MAPS_SUBSCRIPTION_KEY`
   - `VITE_AZURE_MAPS_CLIENT_ID`

## 📦 Technology Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Azure Maps** - Map visualization
- **Axios** - HTTP client
- **React Query** - Server state management

## 🔗 Integration

The web UI communicates with:
- **Router Function App:** Query routing and processing
- **Container App (FastAPI):** Backend API for data processing
- **Microsoft Planetary Computer:** STAC catalog search
- **Azure Maps:** Map tiles and geocoding

## 🧪 Testing

```bash
# Run tests (if configured)
npm test

# Type checking
npm run type-check

# Linting
npm run lint
```

## 📚 Documentation

For more information, see:
- [Main Project README](../../README.md)
- [System Requirements](../../SYSTEM_REQUIREMENTS.md)
- [Deployment Guide](../../documentation/deployment.md)
