# Security Checklist for Earth Copilot Deployment

> **⚠️ IMPORTANT**: This checklist must be completed before deploying Earth Copilot to production or making your fork public.

## 🔒 Before Deployment

### 1. Environment Variables Configuration

- [ ] **Never commit `.env` files** to version control
- [ ] Copy `.env.example` to `.env` and fill in actual values
- [ ] Verify `.gitignore` includes `.env` and `.env.*` patterns
- [ ] Use Azure Key Vault for production secrets (recommended)

### 2. Azure Resources Configuration

Update the following files with your Azure resource names:

- [ ] `.github/workflows/deploy-container-app.yml` - Update environment variables:
  - `AZURE_CONTAINER_REGISTRY`
  - `CONTAINER_APP_NAME`
  - `RESOURCE_GROUP`
  - `IMAGE_NAME`

- [ ] `web-ui/vite.config.ts` - Update `CONTAINER_APP_URL`
- [ ] `web-ui/src/config/api.ts` - Update `API_BASE_URL` fallback
- [ ] `.github/copilot/mcp-servers.json` - Update MCP server URL

### 3. GitHub Secrets Configuration

Set up the following GitHub repository secrets for CI/CD:

- [ ] `AZURE_CLIENT_ID` - Service principal client ID
- [ ] `AZURE_TENANT_ID` - Azure tenant ID
- [ ] `AZURE_SUBSCRIPTION_ID` - Azure subscription ID

Use the `setup-github-auth.ps1` script to automate this setup.

### 4. Deployment Scripts

Review and update parameters in deployment scripts:

- [ ] `deploy-all.ps1` - Resource names
- [ ] `deploy-infrastructure.ps1` - Location and resource group
- [ ] `redeploy-mcp-server.ps1` - ACR and container app names

## 🚫 Never Commit These

### Sensitive Files
- [ ] `.env` files (any environment-specific configuration)
- [ ] `local.settings.json` (Azure Functions local settings)
- [ ] `.azure/` directory (Azure CLI cache)
- [ ] Any files containing API keys, tokens, or passwords
- [ ] SSH keys (`.pem`, `.key` files)
- [ ] Certificates (`.pfx`, `.p12`, `.cer`, `.crt` files)
- [ ] `*secrets*` or `*credentials*` files

### Deployment Artifacts
- [ ] `earth-copilot-mcp-deployment.json`
- [ ] `deployment-config.json`
- [ ] Build logs with sensitive output
- [ ] Container app URLs pointing to your specific instances

## ✅ Safe to Commit

- ✅ `.env.example` and `.env.template` files with placeholder values
- ✅ Documentation files (`README.md`, `DEPLOYMENT.md`, etc.)
- ✅ Configuration files with generic/placeholder values
- ✅ Source code without hardcoded credentials
- ✅ Infrastructure as Code (Bicep/Terraform) with parameterized values

## 🔍 Pre-Commit Verification

Run these checks before committing:

```powershell
# 1. Check for hardcoded secrets (run from repository root)
git grep -i "password\|secret\|key\|token" -- '*.ts' '*.tsx' '*.py' '*.ps1' '*.yml'

# 2. Verify .env files are not tracked
git ls-files | Select-String "\.env$"

# 3. Check for specific URLs
git grep -i "azurecontainerapps.io\|azurewebsites.net" -- '*.ts' '*.tsx' '*.py'

# 4. Look for Azure resource names
git grep -i "earthcopilot" -- '*.yml' '*.ts' '*.tsx'
```

## 🛡️ Production Security Best Practices

### Azure Key Vault Integration

Instead of environment variables, use Azure Key Vault for production:

1. **Create Azure Key Vault**:
   ```bash
   az keyvault create --name your-keyvault --resource-group your-rg --location eastus2
   ```

2. **Store secrets**:
   ```bash
   az keyvault secret set --vault-name your-keyvault --name AOAI-KEY --value "your-key"
   ```

3. **Grant access to Container Apps**:
   - Enable Managed Identity on your Container App
   - Grant Key Vault access to the Managed Identity

4. **Reference secrets in Container App**:
   ```bash
   az containerapp update --name your-app --resource-group your-rg \
     --set-env-vars "AOAI_KEY=secretref:aoai-key"
   ```

### Managed Identities

- [ ] Enable System-Assigned Managed Identity for Container Apps
- [ ] Use Managed Identity for Azure service authentication
- [ ] Avoid storing credentials in environment variables when possible

### Network Security

- [ ] Configure Virtual Network integration
- [ ] Set up Private Endpoints for Azure services
- [ ] Use Azure Front Door or Application Gateway with WAF
- [ ] Configure CORS policies appropriately
- [ ] Enable HTTPS only

### Authentication & Authorization

- [ ] Implement Azure AD authentication for production
- [ ] Enable authentication on Container Apps and App Services
- [ ] Use role-based access control (RBAC)
- [ ] Review and minimize API permissions

### Monitoring & Logging

- [ ] Enable Application Insights
- [ ] Configure log retention policies
- [ ] Set up alerts for security events
- [ ] Regularly review access logs
- [ ] Monitor for anomalous activity

## 🔄 After Deployment

### Regular Maintenance

- [ ] Rotate API keys and secrets regularly (every 90 days)
- [ ] Review and update dependencies for security patches
- [ ] Monitor Azure Security Center recommendations
- [ ] Conduct periodic security audits
- [ ] Keep deployment scripts up to date

### Incident Response

- [ ] Document incident response procedures
- [ ] Know how to quickly rotate compromised credentials
- [ ] Have a rollback plan for deployments
- [ ] Maintain contact information for security team

## 📚 Additional Resources

- [Azure Security Best Practices](https://docs.microsoft.com/azure/security/fundamentals/best-practices-and-patterns)
- [GitHub Security Best Practices](https://docs.github.com/code-security)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Azure Key Vault Documentation](https://docs.microsoft.com/azure/key-vault/)

## ⚠️ If Credentials Are Exposed

If you accidentally commit credentials:

1. **Immediately rotate/revoke** the exposed credentials
2. **Force push** a cleaned commit history or contact GitHub support
3. **Review access logs** for unauthorized access
4. **Update** all affected services with new credentials
5. **Document** the incident for future reference

Remember: Once pushed to a public repository, assume credentials are compromised even if quickly removed.

---

**Last Updated**: October 30, 2025
**Version**: 1.0
