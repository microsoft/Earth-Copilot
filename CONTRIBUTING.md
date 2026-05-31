# Contributing to Planetary Explorer

Thank you for your interest in contributing to Planetary Explorer! This document provides guidelines and information for contributors.

##  Contributor License Agreement

**Important**: Contributions to Microsoft projects are subject to our [Contributor License Agreement (CLA)](https://cla.opensource.microsoft.com/). When you submit a pull request, a CLA bot will automatically determine whether you need to provide a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions provided by the bot. You will only need to do this once across all Microsoft repositories.

##  Getting Started

### Prerequisites

Before contributing, ensure you have the required technical background:

- **Azure Cloud Services** — Understanding of Azure Container Apps, Azure AI Foundry, Azure Maps, and Azure AI Search
- **Python Development** — Python 3.12+ with FastAPI / async
- **React / TypeScript** — Frontend development with Vite
- **AI / LLM Concepts** — Familiarity with Azure OpenAI and tool/function calling
- **Geospatial Data** — Knowledge of STAC (SpatioTemporal Asset Catalog) standards
- **Infrastructure as Code** — Experience with Bicep and the Azure Developer CLI (`azd`)

### Development Environment Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/microsoft/Planetary-Explorer.git
   cd Planetary-Explorer
   ```

2. **Install root dev tooling** (linters / formatters / pytest):
   ```bash
   pip install -r requirements.txt
   ```

3. **Install per-service runtime dependencies** as needed:
   ```bash
   # FastAPI backend (Container App)
   pip install -r planetary-explorer/container-app/requirements.txt

   # Web UI
   cd planetary-explorer/web-ui && npm install && cd ../..
   ```

4. **Provision Azure resources** with the Azure Developer CLI:
   ```bash
   azd auth login
   azd init      # picks up the root azure.yaml
   azd up        # provisions infra + builds + deploys
   ```
   See [`QUICK_DEPLOY.md`](QUICK_DEPLOY.md) for the full deploy walkthrough and feature toggles (Fabric, MPC Pro, private endpoints).

##  Build Instructions

### Local Development

**Backend** (FastAPI container):
```bash
cd planetary-explorer/container-app
uvicorn fastapi_app:app --reload --port 8080
```

**Frontend** (React / Vite):
```bash
cd planetary-explorer/web-ui
npm run dev
```

Access the application at: http://localhost:5173

### Testing

```bash
# Backend tests
cd planetary-explorer/container-app
python -m pytest

# Frontend tests
cd planetary-explorer/web-ui
npm test
```

##  Coding Conventions

### Python Code Standards

- **Style**: Follow PEP 8; we use `black` + `ruff` (installed via root `requirements.txt`).
- **Type Hints**: Use type annotations for all function parameters and return values.
- **Docstrings**: Google-style docstrings for all public functions and classes.
- **Error Handling**: Comprehensive error handling with structured logging.
- **Dependencies**: Pin minimum versions in the per-service `requirements.txt`. The Semantic Kernel runtime has been retired in favor of `sk_shim.py` — do not reintroduce it.

**Example**:
```python
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

def process_stac_query(
    query: str, 
    collections: List[str], 
    bbox: Optional[List[float]] = None
) -> Dict[str, Any]:
    """
    Process a natural language query into STAC API parameters.
    
    Args:
        query: Natural language query string
        collections: List of STAC collection IDs to search
        bbox: Optional bounding box [west, south, east, north]
        
    Returns:
        Dictionary containing STAC query parameters
        
    Raises:
        ValueError: If query is empty or invalid
    """
    try:
        # Implementation here
        pass
    except Exception as e:
        logger.error(f"Failed to process STAC query: {e}")
        raise
```

### TypeScript/React Standards

- **Style**: Use Prettier for formatting
- **Components**: Prefer functional components with hooks
- **Types**: Define explicit interfaces for all props and data structures
- **State Management**: Use React hooks for local state, context for global state
- **API Integration**: Use proper error boundaries and loading states

**Example**:
```typescript
interface QueryResult {
  success: boolean;
  data?: STACResponse;
  error?: string;
}

interface ChatProps {
  onQuerySubmit: (query: string) => Promise<QueryResult>;
  isLoading: boolean;
}

export const Chat: React.FC<ChatProps> = ({ onQuerySubmit, isLoading }) => {
  // Component implementation
};
```

### Infrastructure Code

- **Bicep**: Use descriptive parameter names and include comprehensive documentation
- **Azure Resources**: Follow Azure naming conventions and include appropriate tags
- **Security**: Implement least-privilege access and secure credential management

##  Project Roadmap

### Current Focus Areas

1. **Enhanced STAC Integration**: Expanding support for additional STAC catalogs beyond Microsoft Planetary Computer
2. **Improved AI Accuracy**: Refining semantic translation from natural language to STAC queries
3. **Visualization Enhancements**: Advanced mapping capabilities and data overlay options
4. **Performance Optimization**: Reducing query response times and improving scalability

### Planned Features

- **Multi-language Support**: Expanding beyond English for global accessibility
- **Advanced Analytics**: Statistical analysis tools for geospatial data
- **Collaboration Features**: Shared workspaces and team query management
- **Mobile Support**: Responsive design improvements for mobile devices

### Technology Upgrades

- **Azure AI Updates**: Migration to latest Azure AI services and models
- **Frontend Framework**: Potential React 19 adoption for improved performance
- **Backend Optimization**: Performance improvements in Azure Functions

##  Bug Reports and Feature Requests

### Reporting Bugs

When reporting bugs, please include:

1. **Clear description** of the issue
2. **Steps to reproduce** the problem
3. **Expected vs. actual behavior**
4. **Environment details** (OS, browser, Azure region)
5. **Screenshots or logs** if applicable
6. **STAC query examples** that demonstrate the issue

### Feature Requests

For new features, please provide:

1. **Use case description** and scientific rationale
2. **Proposed implementation** approach
3. **Impact assessment** on existing functionality
4. **Related STAC collections** or data sources

##  Pull Request Process

1. **Fork the repository** and create a feature branch
2. **Implement your changes** following coding conventions
3. **Add or update tests** for new functionality
4. **Update documentation** as needed
5. **Run the full test suite** and ensure all tests pass
6. **Submit a pull request** with a clear description

### PR Requirements

- **Title**: Clear, descriptive title summarizing the change
- **Description**: Detailed explanation of what changed and why
- **Testing**: Evidence that changes have been tested
- **Documentation**: Updates to README, API docs, or other relevant documentation
- **Breaking Changes**: Clear indication if the PR introduces breaking changes

### Review Process

- All PRs require review from project maintainers
- Automated checks must pass (builds, tests, linting)
- PRs may require updates based on feedback
- Once approved, maintainers will merge the PR

##  Additional Resources

- **Azure AI Documentation**: https://docs.microsoft.com/en-us/azure/ai/
- **STAC Specification**: https://stacspec.org/
- **Microsoft Planetary Computer**: https://planetarycomputer.microsoft.com/
- **Semantic Kernel Documentation**: https://learn.microsoft.com/en-us/semantic-kernel/
- **Azure Functions Python Guide**: https://docs.microsoft.com/en-us/azure/azure-functions/functions-reference-python

##  Support

- **General Questions**: Open a GitHub Discussion
- **Bug Reports**: Create a GitHub Issue
- **Security Issues**: Report via Microsoft Security Response Center (MSRC)

---

Thank you for contributing to Planetary Explorer! Together, we're making Earth science data more accessible to researchers worldwide. 