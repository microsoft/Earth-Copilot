# Security Verification - Quick Check
Write-Host ' Earth Copilot Security Check' -ForegroundColor Cyan
git grep -i 'politecoast|blueriver' | Select-Object -First 5
if (True) { Write-Host ' Found specific URLs' -ForegroundColor Red } else { Write-Host ' No specific URLs' -ForegroundColor Green }
