# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import requests
import json
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import *
from azure.core.credentials import AzureKeyCredential
from langchain_openai import AzureOpenAIEmbeddings
import os
import sys
from dotenv import load_dotenv
from pathlib import Path

# Load from root .env file
ROOT_ENV_PATH = Path(__file__).parent.parent.parent.parent / ".env"
print(f"Script location: {Path(__file__).parent}")
print(f"Looking for root .env at: {ROOT_ENV_PATH}")
print(f"Root .env exists: {ROOT_ENV_PATH.exists()}")

if ROOT_ENV_PATH.exists():
    print(f"Loading environment from root config: {ROOT_ENV_PATH}")
    load_dotenv(ROOT_ENV_PATH, override=True)
else:
    print("Root .env not found, loading local .env")
    load_dotenv()

# Configuration - map from main env variables
SEARCH_ENDPOINT = os.getenv("SEARCH_ENDPOINT")
SEARCH_KEY = os.getenv("SEARCH_API_KEY")  # From main config
INDEX_NAME = os.getenv("SEARCH_INDEX_NAME", "veda-collections")  # From main config
AOAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AOAI_KEY = os.getenv("EMBEDDING_KEY", "").strip()  # From main config
AOAI_VERSION = "2023-05-15"  # From main config embedding API version
AOAI_DEPLOYMENT = os.getenv("EMBEDDING_NAME", "").strip()  # From main config

# Debug: Print configuration
print("Configuration loaded:")
print(f"SEARCH_ENDPOINT: {SEARCH_ENDPOINT}")
print(f"SEARCH_KEY: {'***' if SEARCH_KEY else 'None'}")
print(f"INDEX_NAME: {INDEX_NAME}")
print(f"AOAI_ENDPOINT: {AOAI_ENDPOINT}")
print(f"AOAI_KEY: {'***' if AOAI_KEY else 'None'}")
print(f"AOAI_VERSION: {AOAI_VERSION}")
print(f"AOAI_DEPLOYMENT: {AOAI_DEPLOYMENT}")
print()

# Check if all required variables are set
missing_vars = []
if not SEARCH_ENDPOINT:
    missing_vars.append("SEARCH_ENDPOINT")
if not SEARCH_KEY:
    missing_vars.append("SEARCH_KEY")
if not INDEX_NAME:
    missing_vars.append("SEARCH_INDEX")
if not AOAI_ENDPOINT:
    missing_vars.append("AZURE_OPENAI_ENDPOINT")
if not AOAI_KEY:
    missing_vars.append("AZURE_OPENAI_API_KEY")
if not AOAI_DEPLOYMENT:
    missing_vars.append("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT")

if missing_vars:
    print(f"ERROR: Missing required environment variables: {', '.join(missing_vars)}")
    print("Please check your .env file")
    sys.exit(1)


def delete_existing_index():
    """Delete the existing index if it exists"""
    print(f"Attempting to delete existing index: {INDEX_NAME}")
    try:
        index_client = SearchIndexClient(
            endpoint=SEARCH_ENDPOINT, credential=AzureKeyCredential(SEARCH_KEY)
        )
        index_client.delete_index(INDEX_NAME)
        print(f"✓ Successfully deleted existing index: {INDEX_NAME}")
    except Exception as e:
        print(f"ℹ Index {INDEX_NAME} doesn't exist or couldn't be deleted: {e}")
        print("This is normal if the index doesn't exist yet.")


def create_vector_index():
    """Create index with vector fields"""
    print(f"Creating new vector index: {INDEX_NAME}")
    try:
        index_client = SearchIndexClient(
            endpoint=SEARCH_ENDPOINT, credential=AzureKeyCredential(SEARCH_KEY)
        )

        # Define fields including vector field
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SearchableField(name="description", type=SearchFieldDataType.String),
            SimpleField(name="spatial_extent", type=SearchFieldDataType.String),
            SimpleField(name="temporal_extent", type=SearchFieldDataType.String),
            # Add vector field for embeddings
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=1536,  # For text-embedding-ada-002
                vector_search_profile_name="my-vector-config",
            ),
            # Combined content field for generating embeddings
            SearchableField(name="content", type=SearchFieldDataType.String),
        ]

        print("Defined fields:")
        for field in fields:
            print(f"  - {field.name}: {field.type}")

        # Configure vector search
        vector_search = VectorSearch(
            profiles=[
                VectorSearchProfile(
                    name="my-vector-config",
                    algorithm_configuration_name="my-algorithms-config",
                )
            ],
            algorithms=[HnswAlgorithmConfiguration(name="my-algorithms-config")],
        )

        print("Configured vector search profiles")

        # Create the index
        index = SearchIndex(name=INDEX_NAME, fields=fields, vector_search=vector_search)

        print("Creating index...")
        result = index_client.create_index(index)
        print(f"✓ Successfully created vector index: {INDEX_NAME}")
        return result
    except Exception as e:
        print(f"✗ Error creating index: {e}")
        raise


def populate_vector_index():
    """Fetch collections from VEDA STAC and populate with embeddings"""
    print("Initializing embeddings...")

    try:
        # Initialize embeddings
        embeddings = AzureOpenAIEmbeddings(
            azure_deployment=AOAI_DEPLOYMENT,
            openai_api_version=AOAI_VERSION,
            azure_endpoint=AOAI_ENDPOINT,
            api_key=AOAI_KEY,
        )
        print("✓ Embeddings initialized successfully")
    except Exception as e:
        print(f"✗ Error initializing embeddings: {e}")
        raise

    # Fetch collections from VEDA STAC
    print("Fetching collections from VEDA STAC...")
    try:
        response = requests.get("https://openveda.cloud/api/stac/collections")
        response.raise_for_status()
        collections = response.json()
        print(f"✓ Fetched {len(collections.get('collections', []))} collections")
    except Exception as e:
        print(f"✗ Error fetching collections: {e}")
        raise

    try:
        search_client = SearchClient(
            endpoint=SEARCH_ENDPOINT,
            index_name=INDEX_NAME,
            credential=AzureKeyCredential(SEARCH_KEY),
        )
        print("✓ Search client initialized")
    except Exception as e:
        print(f"✗ Error initializing search client: {e}")
        raise

    documents = []
    total_collections = len(collections.get("collections", []))

    for i, collection in enumerate(collections.get("collections", []), 1):
        print(f"Processing collection {i}/{total_collections}: {collection['id']}")

        # Create combined content for embedding
        content = f"{collection.get('title', '')} {collection.get('description', '')}"

        # Generate embedding for the content
        try:
            embedding = embeddings.embed_query(content)
            print(f"  ✓ Generated embedding (length: {len(embedding)})")
        except Exception as e:
            print(f"  ✗ Error generating embedding for {collection['id']}: {e}")
            continue

        doc = {
            "id": collection["id"],
            "title": collection.get("title", ""),
            "description": collection.get("description", ""),
            "content": content,  # Combined content field
            "content_vector": embedding,  # Vector embedding
            "spatial_extent": json.dumps(
                collection.get("extent", {}).get("spatial", {})
            ),
            "temporal_extent": json.dumps(
                collection.get("extent", {}).get("temporal", {})
            ),
        }
        documents.append(doc)

    # Upload documents in batches
    if documents:
        print(f"Uploading {len(documents)} documents...")
        try:
            search_client.upload_documents(documents)
            print(f"✓ Successfully uploaded {len(documents)} documents with embeddings")
        except Exception as e:
            print(f"✗ Error uploading documents: {e}")
            raise
    else:
        print("✗ No documents to upload")


if __name__ == "__main__":
    try:
        print("=== Creating Vector Search Index ===")
        print()

        print("Step 1: Deleting existing index...")
        delete_existing_index()
        print()

        print("Step 2: Creating new vector index...")
        create_vector_index()
        print()

        print("Step 3: Populating index with embeddings...")
        populate_vector_index()
        print()

        print("✓ Vector index created and populated successfully!")

    except Exception as e:
        print(f"\n✗ Script failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)