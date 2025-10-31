# VEDA AI Search Indexing

This directory contains the indexing script for creating an Azure AI Search index with VEDA (Visualization, Exploration, and Data Analysis) Earth Science collection data.

## 🔍 Purpose

Creates a vector search index in Azure AI Search containing NASA VEDA collection metadata with embeddings, enabling semantic search capabilities for the Earth Copilot React UI.

## 📁 Contents

```
ai-search/
├── scripts/
│   ├── create_search_index_with_vectors.py  # Index creation script
│   └── requirements.txt                     # Python dependencies
├── setup.sh                                 # Linux setup script
└── README.md                               # This file
```

## 🚀 Usage

### Prerequisites

- Azure AI Search service
- Azure OpenAI service with text-embedding-ada-002 deployment
- Environment variables configured in main `.env` file

### Required Environment Variables

The script reads from the main project `.env` file:

```env
# Azure AI Search
SEARCH_ENDPOINT=https://your-search-service.search.windows.net
SEARCH_API_KEY=your_search_admin_key
SEARCH_INDEX_NAME=veda-collections

# Azure OpenAI for Embeddings
EMBEDDING_KEY=your_azure_openai_api_key
EMBEDDING_NAME=text-embedding-ada-002
```

### Create the Index

```bash
cd /workspaces/Earth-Copilot/earth-copilot/ai-search
python scripts/create_search_index_with_vectors.py
```

## 🔧 What the Script Does

1. **Deletes existing index** (if present)
2. **Creates new vector index** with fields:
   - `id`: Collection identifier (key)
   - `title`: Collection title (searchable)
   - `description`: Collection description (searchable)  
   - `content`: Combined title + description (searchable)
   - `content_vector`: 1536-dimension embedding vector
   - `spatial_extent`: Geospatial bounds (JSON)
   - `temporal_extent`: Time bounds (JSON)

3. **Fetches VEDA collections** from https://openveda.cloud/api/stac/collections
4. **Generates embeddings** using Azure OpenAI text-embedding-ada-002
5. **Uploads documents** to the search index

## 🎯 Integration

The indexed data is used by:
- `earth-copilot/react-ui/src/services/vedaSearchService.ts` for semantic search
- React UI VEDA search functionality in the data catalog panel
- LLM chat responses grounded in real VEDA collection metadata

## 🔍 Vector Search Configuration

- **Algorithm**: HNSW (Hierarchical Navigable Small World)
- **Dimensions**: 1536 (text-embedding-ada-002 compatible)
- **Similarity**: Cosine similarity
- **Top Results**: Configurable (default: 5)

## 🐛 Troubleshooting

- **Missing environment variables**: Check main project `.env` file
- **Authentication errors**: Verify Azure service keys and endpoints
- **Index creation fails**: Ensure Azure AI Search service is running
- **Embedding errors**: Confirm Azure OpenAI deployment name and API version

## 📊 Expected Output

Successfully creates an index with ~140 VEDA collections, each with:
- Searchable metadata fields
- 1536-dimension vector embeddings
- Spatial and temporal extent information

The React UI can then perform semantic searches against this indexed data using natural language queries.
