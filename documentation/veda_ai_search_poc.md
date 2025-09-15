# 🔍 VEDA AI Search POC Documentation

## 📋 Overview

The VEDA AI Search POC (Proof of Concept) demonstrates semantic search capabilities over NASA's VEDA (Visualization, Exploration, and Data Analysis) Earth Science collections using Azure AI Search with vector embeddings. This enables users to discover relevant Earth Science datasets through natural language queries rather than manual STAC catalog browsing.

## 🎯 Purpose

Traditional STAC (SpatioTemporal Asset Catalog) browsing requires users to know exact collection names and navigate hierarchical catalogs. The VEDA AI Search POC solves this by:

- **Semantic Understanding**: Query "fire data for California" to find burn severity datasets
- **Vector Similarity**: Find relevant collections even with different terminology
- **Natural Language**: Use conversational queries instead of technical metadata searches
- **AI-Powered Discovery**: Leverage GPT models for intelligent data recommendations

## 🔧 Technical Components

### 1. Data Source: VEDA STAC Collections

**API Endpoint**: `https://openveda.cloud/api/stac/collections`

**Sample Collections**:
- Bangladesh Land Cover (2001-2020) - MODIS-based land use change analysis
- Thomas Fire Burn Severity - BARC classification for 2017 California wildfire
- ERA5 Climate Reanalysis - Temperature, pressure, wind, cloud fraction data
- Blizzard Tracking Data - Storm events and meteorological patterns

**Metadata Structure**:
```json
{
  "id": "barc-thomasfire",
  "title": "Burn Area Reflectance Classification for Thomas Fire", 
  "description": "BARC from BAER program for Thomas fire, 2017",
  "extent": {
    "spatial": {"bbox": [[-119.73, 34.20, -118.89, 34.73]]},
    "temporal": {"interval": [["2017-12-01", "2017-12-31"]]}
  }
}
```

### 2. Vector Embeddings: Azure OpenAI

**Model**: `text-embedding-ada-002`
- **Dimensions**: 1536
- **Input**: Combined collection title + description
- **Output**: Semantic vector representation enabling similarity search

**Embedding Process**:
```python
# Combine metadata for semantic richness
content = f"{collection['title']} {collection['description']}"

# Generate vector embedding
embedding = azure_openai.embed_query(content)
# Result: [0.123, -0.456, 0.789, ...] (1536 dimensions)
```

### 3. Search Index: Azure AI Search

**Index Name**: `veda-collections`
**Algorithm**: HNSW (Hierarchical Navigable Small World)
**Search Type**: Vector similarity with cosine distance

**Index Schema**:
```json
{
  "fields": [
    {"name": "id", "type": "String", "key": true},
    {"name": "title", "type": "String", "searchable": true},
    {"name": "description", "type": "String", "searchable": true},
    {"name": "spatial_extent", "type": "String"},
    {"name": "temporal_extent", "type": "String"},
    {"name": "content_vector", "type": "Collection(Single)", "dimensions": 1536},
    {"name": "content", "type": "String", "searchable": true}
  ]
}
```

### 4. AI Agent: LangChain Framework

**Agent Type**: Conversational ReAct (Reasoning + Acting)
**Memory**: ConversationBufferMemory for context retention
**Tools**:
- **VEDA Collections Search**: Vector similarity search
- **Geocoding**: Location name to coordinates conversion  
- **Fire Events**: Placeholder for NASA FIRMS integration

**Agent Workflow**:
1. **Query Analysis**: Parse user intent and extract key terms
2. **Tool Selection**: Choose appropriate search/analysis tools
3. **Vector Search**: Generate query embedding and find similar collections
4. **Result Filtering**: Apply relevancy threshold (0.75+)
5. **Response Generation**: Format results with AI explanation

## 🚀 Usage Examples

### Basic Search
```python
from veda_search_poc.agent import VEDASearchAgent

agent = VEDASearchAgent()
results = agent.search_veda_collections("wildfire burn severity California")
```

**Sample Result**:
```json
[
  {
    "id": "barc-thomasfire",
    "title": "Burn Area Reflectance Classification for Thomas Fire",
    "description": "BARC from BAER program for Thomas fire, 2017",
    "relevance_score": 0.841,
    "spatial_extent": "California, USA",
    "temporal_extent": "2017-12-01 to 2017-12-31"
  }
]
```

### Conversational Agent in Earth Copilot
```python
# Full AI agent with natural language processing
response = agent.process_query("Show me climate data for monitoring temperature trends")
print(response['answer'])
# "I found several relevant datasets including ERA5 temperature reanalysis..."
```