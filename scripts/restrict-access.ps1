# Restrict Access to Specific Users
# This script enables user assignment requirement for the app

param(
    [Parameter(Mandatory=$true)]
    [string]$ClientId,
    
    [Parameter(Mandatory=$false)]
    [string[]]$UserEmails = @()
)

Write-Host "[LOCK] Restricting access to specific users for app: $ClientId" -ForegroundColor Cyan
Write-Host ""

# Step 1: Get or create service principal
Write-Host "[NOTE] Step 1: Getting service principal..." -ForegroundColor Yellow
try {
    $sp = az ad sp show --id $ClientId 2>$null | ConvertFrom-Json
    
    if (-not $sp) {
        Write-Host "Creating service principal..." -ForegroundColor Yellow
        az ad sp create --id $ClientId | Out-Null
        $sp = az ad sp show --id $ClientId | ConvertFrom-Json
    }
    
    $spObjectId = $sp.id
    Write-Host "[OK] Service Principal Object ID: $spObjectId" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Error: Could not get/create service principal: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 2: Enable user assignment requirement
Write-Host "[LOCK] Step 2: Enabling user assignment requirement..." -ForegroundColor Yellow
try {
    az ad sp update --id $spObjectId --set appRoleAssignmentRequired=true
    Write-Host "[OK] User assignment requirement enabled" -ForegroundColor Green
    Write-Host "   Now only assigned users can access the app." -ForegroundColor White
} catch {
    Write-Host "[FAIL] Error enabling user assignment requirement: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 3: Assign users if provided
if ($UserEmails.Count -gt 0) {
    Write-Host "[USERS] Step 3: Assigning users..." -ForegroundColor Yellow
    
    foreach ($email in $UserEmails) {
        try {
            Write-Host "  Adding: $email" -ForegroundColor White
            
            # Get user object ID
            $user = az ad user show --id $email 2>$null | ConvertFrom-Json
            
            if ($user) {
                # Assign user to the app
                az ad app owner add --id $ClientId --owner-object-id $user.id 2>$null | Out-Null
                Write-Host "  [OK] Added $email" -ForegroundColor Green
            } else {
                Write-Host "  [WARN]  User not found: $email" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "  [FAIL] Error adding user $email : $_" -ForegroundColor Red
        }
    }
    Write-Host ""
} else {
    Write-Host "ℹ️  No users specified. You can add users in Azure Portal:" -ForegroundColor Cyan
    Write-Host "   1. Go to Azure Portal > Azure Active Directory" -ForegroundColor White
    Write-Host "   2. Navigate to Enterprise Applications" -ForegroundColor White
    Write-Host "   3. Search for your app" -ForegroundColor White
    Write-Host "   4. Go to Users and groups" -ForegroundColor White
    Write-Host "   5. Click 'Add user/group'" -ForegroundColor White
    Write-Host ""
}

Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "[OK] ACCESS RESTRICTION COMPLETE!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "[NOTE] Summary:" -ForegroundColor Yellow
Write-Host "  - User assignment is now REQUIRED" -ForegroundColor White
Write-Host "  - Only assigned users can access the app" -ForegroundColor White
Write-Host "  - Unassigned users will see an error when trying to sign in" -ForegroundColor White
Write-Host ""
Write-Host "[+] To add more users later:" -ForegroundColor Yellow
Write-Host "   Method 1 - Using this script:" -ForegroundColor White
Write-Host "   .\restrict-access.ps1 -ClientId '$ClientId' -UserEmails 'user1@company.com','user2@company.com'" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Method 2 - Using Azure Portal:" -ForegroundColor White
Write-Host "   Azure Portal > Enterprise Applications > [Your App] > Users and groups > Add user/group" -ForegroundColor Cyan
Write-Host ""
Write-Host "[UNLOCK] To allow all tenant users again:" -ForegroundColor Yellow
Write-Host "   az ad sp update --id $spObjectId --set appRoleAssignmentRequired=false" -ForegroundColor Cyan
Write-Host ""
