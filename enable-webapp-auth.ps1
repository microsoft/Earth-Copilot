# Enable Microsoft Entra Authentication for Azure Web App
# This script automates the setup of Azure AD authentication for App Service

param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroupName,
    
    [Parameter(Mandatory=$true)]
    [string]$WebAppName,
    
    [Parameter(Mandatory=$false)]
    [string]$AppDisplayName = "EarthCopilot-WebUI",
    
    [Parameter(Mandatory=$false)]
    [int]$SecretExpirationYears = 2,
    
    [Parameter(Mandatory=$false)]
    [ValidateSet("SingleTenant", "MultiTenant", "MultiTenantAndPersonal")]
    [string]$TenantType = "SingleTenant"
)

Write-Host "🔐 Setting up Microsoft Entra Authentication for Web App: $WebAppName" -ForegroundColor Cyan
Write-Host ""

# Display tenant type information
Write-Host "🏢 Tenant Configuration:" -ForegroundColor Yellow
switch ($TenantType) {
    "SingleTenant" {
        Write-Host "   Type: Single Tenant (Your organization only)" -ForegroundColor White
        Write-Host "   Access: Only users in YOUR Microsoft tenant can sign in" -ForegroundColor White
        $signInAudience = "AzureADMyOrg"
    }
    "MultiTenant" {
        Write-Host "   Type: Multi-Tenant (Any Microsoft organization)" -ForegroundColor White
        Write-Host "   Access: Users from ANY Microsoft/Entra ID tenant can sign in" -ForegroundColor White
        Write-Host "   Note: Personal Microsoft accounts (outlook.com) are NOT allowed" -ForegroundColor Yellow
        $signInAudience = "AzureADMultipleOrgs"
    }
    "MultiTenantAndPersonal" {
        Write-Host "   Type: Multi-Tenant + Personal Accounts (Any Microsoft account)" -ForegroundColor White
        Write-Host "   Access: Anyone with a Microsoft account can sign in" -ForegroundColor White
        Write-Host "   Note: Includes personal accounts like outlook.com and hotmail.com" -ForegroundColor Yellow
        $signInAudience = "AzureADandPersonalMicrosoftAccount"
    }
}
Write-Host ""

# Step 1: Get the web app URL
Write-Host "📍 Step 1: Getting web app URL..." -ForegroundColor Yellow
try {
    $webAppDetails = az webapp show --name $WebAppName --resource-group $ResourceGroupName | ConvertFrom-Json
    
    if (-not $webAppDetails) {
        Write-Host "❌ Error: Could not retrieve web app. Make sure it exists." -ForegroundColor Red
        exit 1
    }
    
    $webAppUrl = "https://$($webAppDetails.defaultHostName)"
    $redirectUri = "$webAppUrl/.auth/login/aad/callback"
    
    Write-Host "✅ Web App URL: $webAppUrl" -ForegroundColor Green
    Write-Host "✅ Redirect URI: $redirectUri" -ForegroundColor Green
} catch {
    Write-Host "❌ Error retrieving web app: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 2: Get Tenant ID
Write-Host "🏢 Step 2: Getting Tenant ID..." -ForegroundColor Yellow
try {
    $tenantId = az account show --query tenantId -o tsv
    Write-Host "✅ Tenant ID: $tenantId" -ForegroundColor Green
} catch {
    Write-Host "❌ Error getting tenant ID: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 3: Create Azure AD App Registration
Write-Host "📝 Step 3: Creating Azure AD App Registration..." -ForegroundColor Yellow
try {
    # Check if app already exists
    $existingApp = az ad app list --display-name $AppDisplayName --query "[0]" | ConvertFrom-Json
    
    if ($existingApp) {
        Write-Host "⚠️  App registration '$AppDisplayName' already exists. Using existing app." -ForegroundColor Yellow
        $clientId = $existingApp.appId
        
        # Update redirect URI and sign-in audience
        Write-Host "🔄 Updating app configuration..." -ForegroundColor Yellow
        az ad app update --id $clientId --web-redirect-uris $redirectUri --sign-in-audience $signInAudience | Out-Null
    } else {
        Write-Host "Creating new app registration..." -ForegroundColor Yellow
        $appRegistration = az ad app create `
            --display-name $AppDisplayName `
            --sign-in-audience $signInAudience `
            --web-redirect-uris $redirectUri | ConvertFrom-Json
        
        $clientId = $appRegistration.appId
        Write-Host "✅ Created app registration" -ForegroundColor Green
    }
    
    Write-Host "✅ Client ID: $clientId" -ForegroundColor Green
} catch {
    Write-Host "❌ Error creating app registration: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 4: Create Client Secret
Write-Host "🔑 Step 4: Creating client secret..." -ForegroundColor Yellow
try {
    $secretResult = az ad app credential reset `
        --id $clientId `
        --append `
        --display-name "WebUI-Auth-Secret-$(Get-Date -Format 'yyyy-MM-dd')" `
        --years $SecretExpirationYears | ConvertFrom-Json
    
    $clientSecret = $secretResult.password
    Write-Host "✅ Client secret created (expires in $SecretExpirationYears years)" -ForegroundColor Green
} catch {
    Write-Host "❌ Error creating client secret: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 5: Configure API Permissions
Write-Host "🔐 Step 5: Configuring API permissions..." -ForegroundColor Yellow
try {
    # Add Microsoft Graph delegated permissions
    az ad app permission add --id $clientId --api 00000003-0000-0000-c000-000000000000 --api-permissions e1fe6dd8-ba31-4d61-89e7-88639da4683d=Scope | Out-Null
    az ad app permission add --id $clientId --api 00000003-0000-0000-c000-000000000000 --api-permissions 64a6cdd6-aab1-4aaf-94b8-3cc8405e90d0=Scope | Out-Null
    az ad app permission add --id $clientId --api 00000003-0000-0000-c000-000000000000 --api-permissions 14dad69e-099b-42c9-810b-d002981feec1=Scope | Out-Null
    
    Write-Host "Success: API permissions configured for User.Read, profile, and email" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Warning: Could not configure API permissions automatically." -ForegroundColor Yellow
}
Write-Host ""

# Step 6: Create Service Principal (if not exists)
Write-Host "👤 Step 6: Creating service principal..." -ForegroundColor Yellow
try {
    $sp = az ad sp show --id $clientId 2>$null | ConvertFrom-Json
    if (-not $sp) {
        az ad sp create --id $clientId | Out-Null
        Write-Host "✅ Service principal created" -ForegroundColor Green
    } else {
        Write-Host "✅ Service principal already exists" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠️  Warning: Could not verify service principal" -ForegroundColor Yellow
}
Write-Host ""

# Step 7: Configure Web App Authentication
Write-Host "🚀 Step 7: Configuring Web App authentication..." -ForegroundColor Yellow
Write-Host ""

try {
    Write-Host "   Setting up Microsoft identity provider..." -ForegroundColor White
    
    # Configure authentication using az webapp auth commands
    az webapp auth update `
        --name $WebAppName `
        --resource-group $ResourceGroupName `
        --enabled true `
        --action RedirectToLoginPage `
        --aad-allowed-token-audiences "api://$clientId" `
        --aad-client-id $clientId `
        --aad-client-secret $clientSecret `
        --aad-token-issuer-url "https://sts.windows.net/$tenantId/" | Out-Null
    
    Write-Host "✅ Web App authentication configured!" -ForegroundColor Green
    
} catch {
    Write-Host "❌ Error configuring Web App authentication: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "⚠️  Fallback: You can configure it manually in Azure Portal:" -ForegroundColor Yellow
    Write-Host "1. Go to Azure Portal > App Services > $WebAppName" -ForegroundColor White
    Write-Host "2. Navigate to 'Authentication' in the left menu" -ForegroundColor White
    Write-Host "3. Click 'Add identity provider'" -ForegroundColor White
    Write-Host "4. Select 'Microsoft'" -ForegroundColor White
    Write-Host "5. Use these values:" -ForegroundColor White
    Write-Host "   - Client ID: $clientId" -ForegroundColor Cyan
    Write-Host "   - Client Secret: $clientSecret" -ForegroundColor Cyan
    Write-Host "   - Issuer URL: https://sts.windows.net/$tenantId/" -ForegroundColor Cyan
    exit 1
}
Write-Host ""

Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "📋 CONFIGURATION SUMMARY" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Resource Type:     Azure Web App (App Service)" -ForegroundColor White
Write-Host "Resource Group:    $ResourceGroupName" -ForegroundColor White
Write-Host "Web App Name:      $WebAppName" -ForegroundColor White
Write-Host "Web App URL:       $webAppUrl" -ForegroundColor White
Write-Host "Tenant Type:       $TenantType" -ForegroundColor White
Write-Host "Client ID:         $clientId" -ForegroundColor White
Write-Host "Tenant ID:         $tenantId" -ForegroundColor White
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "✅ SETUP COMPLETE!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "📝 What Happens Now:" -ForegroundColor Yellow
Write-Host "✓ Your web app requires authentication" -ForegroundColor White
Write-Host "✓ Users are redirected to Microsoft login page" -ForegroundColor White
Write-Host "✓ Only authenticated users can access the app" -ForegroundColor White

if ($TenantType -eq "SingleTenant") {
    Write-Host "✓ Only users in YOUR organization can sign in" -ForegroundColor White
} elseif ($TenantType -eq "MultiTenant") {
    Write-Host "✓ Users from ANY Microsoft organization can sign in" -ForegroundColor White
} else {
    Write-Host "✓ Anyone with a Microsoft account can sign in" -ForegroundColor White
}

Write-Host ""
Write-Host "🧪 Test It Now:" -ForegroundColor Yellow
Write-Host "1. Open a new incognito/private browser window" -ForegroundColor White
Write-Host "2. Navigate to: $webAppUrl" -ForegroundColor Cyan
Write-Host "3. You should be redirected to Microsoft login" -ForegroundColor White
Write-Host "4. Sign in with your Microsoft account" -ForegroundColor White
Write-Host "5. You'll be redirected back to the app" -ForegroundColor White
Write-Host ""
Write-Host "🔓 To disable authentication later:" -ForegroundColor Yellow
Write-Host "   az webapp auth update --name $WebAppName --resource-group $ResourceGroupName --enabled false" -ForegroundColor Cyan
Write-Host ""
Write-Host "🔒 To restrict to specific users (optional):" -ForegroundColor Yellow
Write-Host "   .\restrict-access.ps1 -ClientId '$clientId'" -ForegroundColor Cyan
Write-Host ""
