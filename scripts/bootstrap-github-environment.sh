#!/usr/bin/env bash
#
# Bootstrap GitHub Environment for Earth Copilot Deployment
#
# This script creates/updates a GitHub environment with variables and secrets
# for automated deployment via GitHub Actions.
#
# Usage:
#   ./scripts/bootstrap-github-environment.sh <config-file> [owner/repo]
#
# Example:
#   ./scripts/bootstrap-github-environment.sh .github/environment-config-dev.yml microsoft/Earth-Copilot
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check for gh CLI
    if ! command -v gh &> /dev/null; then
        log_error "GitHub CLI (gh) is not installed"
        log_info "Install from: https://cli.github.com/"
        exit 1
    fi
    
    # Check for yq (YAML parser)
    if ! command -v yq &> /dev/null; then
        log_warning "yq is not installed. Installing via snap..."
        if command -v snap &> /dev/null; then
            sudo snap install yq
        else
            log_error "Please install yq manually: https://github.com/mikefarah/yq"
            exit 1
        fi
    fi
    
    # Check gh authentication
    if ! gh auth status &> /dev/null; then
        log_error "GitHub CLI is not authenticated"
        log_info "Run: gh auth login"
        exit 1
    fi
    
    log_success "All prerequisites met"
}

# Parse config file
parse_config() {
    local config_file=$1
    
    if [ ! -f "$config_file" ]; then
        log_error "Config file not found: $config_file"
        exit 1
    fi
    
    log_info "Parsing configuration from: $config_file"
    
    # Extract values using yq
    ENV_NAME=$(yq '.environment.name' "$config_file")
    ENV_DESCRIPTION=$(yq '.environment.description' "$config_file")
    REQUIRE_APPROVAL=$(yq '.environment.requireApproval' "$config_file")
    
    # Extract variables
    AZURE_SUBSCRIPTION_ID=$(yq '.variables.AZURE_SUBSCRIPTION_ID' "$config_file")
    AZURE_RESOURCE_GROUP=$(yq '.variables.AZURE_RESOURCE_GROUP' "$config_file")
    AZURE_LOCATION=$(yq '.variables.AZURE_LOCATION' "$config_file")
    ENVIRONMENT_NAME=$(yq '.variables.ENVIRONMENT_NAME' "$config_file")
    
    # Optional variables
    DEPLOY_AI_SEARCH=$(yq '.variables.DEPLOY_AI_SEARCH // "false"' "$config_file")
    SKIP_MODELS=$(yq '.variables.SKIP_MODELS // "false"' "$config_file")
    ENABLE_AUTHENTICATION=$(yq '.variables.ENABLE_AUTHENTICATION // "false"' "$config_file")
    
    log_success "Configuration parsed successfully"
    echo "  Environment: $ENV_NAME"
    echo "  Subscription: $AZURE_SUBSCRIPTION_ID"
    echo "  Resource Group: $AZURE_RESOURCE_GROUP"
    echo "  Location: $AZURE_LOCATION"
}

# Create or update GitHub environment
create_environment() {
    local repo=$1
    
    log_info "Creating/updating GitHub environment: $ENV_NAME"
    
    # Check if environment exists
    if gh api "repos/$repo/environments/$ENV_NAME" &> /dev/null; then
        log_info "Environment exists, updating..."
    else
        log_info "Creating new environment..."
    fi
    
    # Create/update environment with protection rules
    if [ "$REQUIRE_APPROVAL" = "true" ]; then
        log_info "Setting up manual approval requirement..."
        # Note: Reviewers would need to be added separately via GitHub UI or API
        gh api -X PUT "repos/$repo/environments/$ENV_NAME" \
            -f wait_timer=0 \
            -f prevent_self_review=false
    else
        gh api -X PUT "repos/$repo/environments/$ENV_NAME"
    fi
    
    log_success "Environment created/updated: $ENV_NAME"
}

# Set environment variables
set_variables() {
    local repo=$1
    
    log_info "Setting environment variables..."
    
    # Array of variables to set
    declare -A VARS=(
        ["AZURE_SUBSCRIPTION_ID"]="$AZURE_SUBSCRIPTION_ID"
        ["AZURE_RESOURCE_GROUP"]="$AZURE_RESOURCE_GROUP"
        ["AZURE_LOCATION"]="$AZURE_LOCATION"
        ["ENVIRONMENT_NAME"]="$ENVIRONMENT_NAME"
        ["DEPLOY_AI_SEARCH"]="$DEPLOY_AI_SEARCH"
        ["SKIP_MODELS"]="$SKIP_MODELS"
        ["ENABLE_AUTHENTICATION"]="$ENABLE_AUTHENTICATION"
    )
    
    for var_name in "${!VARS[@]}"; do
        var_value="${VARS[$var_name]}"
        log_info "Setting $var_name..."
        
        gh api -X PUT "repos/$repo/environments/$ENV_NAME/variables/$var_name" \
            -f name="$var_name" \
            -f value="$var_value" &> /dev/null || {
            # Try creating if update fails
            gh api -X POST "repos/$repo/environments/$ENV_NAME/variables" \
                -f name="$var_name" \
                -f value="$var_value" &> /dev/null
        }
    done
    
    log_success "All variables set successfully"
}

# Set environment secrets
set_secrets() {
    local repo=$1
    
    log_info "Setting up environment secrets..."
    
    echo ""
    log_warning "You will be prompted to enter secret values."
    log_warning "Secrets will NOT be echoed to the terminal."
    echo ""
    
    # AZURE_CREDENTIALS
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}AZURE_CREDENTIALS${NC}"
    echo "This is the service principal JSON for Azure authentication."
    echo ""
    echo "To create, run:"
    echo "  az ad sp create-for-rbac \\"
    echo "    --name 'sp-earthcopilot-$ENV_NAME' \\"
    echo "    --role Contributor \\"
    echo "    --scopes /subscriptions/$AZURE_SUBSCRIPTION_ID \\"
    echo "    --sdk-auth"
    echo ""
    echo "Paste the entire JSON output below (press Ctrl+D when done):"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    AZURE_CREDENTIALS=$(cat)
    
    if [ -z "$AZURE_CREDENTIALS" ]; then
        log_error "AZURE_CREDENTIALS cannot be empty"
        exit 1
    fi
    
    # Validate JSON
    if ! echo "$AZURE_CREDENTIALS" | jq empty 2>/dev/null; then
        log_error "AZURE_CREDENTIALS is not valid JSON"
        exit 1
    fi
    
    log_info "Setting AZURE_CREDENTIALS secret..."
    gh secret set AZURE_CREDENTIALS \
        --repo "$repo" \
        --env "$ENV_NAME" \
        --body "$AZURE_CREDENTIALS"
    
    log_success "AZURE_CREDENTIALS set successfully"
    
    # Optional: Authentication secrets
    if [ "$ENABLE_AUTHENTICATION" = "true" ]; then
        echo ""
        log_info "Authentication is enabled. Setting up Entra ID secrets..."
        
        read -p "Microsoft Entra Client ID: " ENTRA_CLIENT_ID
        read -p "Microsoft Entra Tenant ID: " ENTRA_TENANT_ID
        read -sp "Microsoft Entra Client Secret: " ENTRA_CLIENT_SECRET
        echo ""
        
        gh secret set MICROSOFT_ENTRA_CLIENT_ID \
            --repo "$repo" \
            --env "$ENV_NAME" \
            --body "$ENTRA_CLIENT_ID"
        
        gh secret set MICROSOFT_ENTRA_TENANT_ID \
            --repo "$repo" \
            --env "$ENV_NAME" \
            --body "$ENTRA_TENANT_ID"
        
        gh secret set MICROSOFT_ENTRA_CLIENT_SECRET \
            --repo "$repo" \
            --env "$ENV_NAME" \
            --body "$ENTRA_CLIENT_SECRET"
        
        log_success "Authentication secrets set successfully"
    fi
}

# Main execution
main() {
    if [ $# -lt 1 ]; then
        log_error "Usage: $0 <config-file> [owner/repo]"
        log_info "Example: $0 .github/environment-config-dev.yml microsoft/Earth-Copilot"
        exit 1
    fi
    
    local config_file=$1
    local repo=${2:-}
    
    # Detect repo if not provided
    if [ -z "$repo" ]; then
        if [ -d ".git" ]; then
            repo=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")
        fi
        
        if [ -z "$repo" ]; then
            log_error "Could not detect repository. Please provide owner/repo as second argument."
            exit 1
        fi
    fi
    
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "  Earth Copilot GitHub Environment Bootstrap"
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Repository: $repo"
    echo ""
    
    check_prerequisites
    parse_config "$config_file"
    create_environment "$repo"
    set_variables "$repo"
    set_secrets "$repo"
    
    echo ""
    log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_success "  Bootstrap Complete!"
    log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    log_info "Next steps:"
    echo "  1. Go to: https://github.com/$repo/actions/workflows/deploy-infrastructure.yml"
    echo "  2. Click 'Run workflow'"
    echo "  3. Select environment: $ENV_NAME"
    echo "  4. Click 'Run workflow' button"
    echo ""
    log_info "The workflow will:"
    echo "  [OK] Deploy infrastructure to Azure"
    echo "  [OK] Build and deploy backend container"
    echo "  [OK] Build and deploy frontend app"
    echo "  [OK] Store all secrets in Key Vault"
    echo ""
    log_success "Your Earth Copilot will be live in ~10-15 minutes!"
}

main "$@"
