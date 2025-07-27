#!/usr/bin/env python3
"""
Check ChromaDB script - Utility to inspect vector store contents
Run from project root: python check_chroma.py [options]
"""

import sys
import argparse
from pathlib import Path
import uuid

# Add project root to sys.path to allow importing app modules
# Assumes script is run from the project root directory
project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import settings AFTER adding project root to path
try:
    from app.core.config import settings
except ImportError as e:
    print(f"Error importing app.core.config. Make sure script is run from project root ('knowledge-hub-backend/'): {e}")
    sys.exit(1)

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
except ImportError as e:
    print(f"Error loading configuration: {e}")
    sys.exit(1)

def check_database(doc_id_to_check=None, check_count=False, limit=5):
    """Check ChromaDB collection and optionally filter by doc_id."""
    try:
        # Initialize ChromaDB client
        client = chromadb.PersistentClient(
            path=settings.VECTOR_STORE_PATH,
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        
        # Get the collection
        collection = client.get_collection(name=settings.CHROMA_COLLECTION_NAME)
        
        # Get total count if requested
        if check_count:
            total_count = collection.count()
            print(f"\n--- Total Chunks in ChromaDB Collection ---")
            print(f"Total: {total_count}")
            return
        
        # If no doc_id provided, just return
        if not doc_id_to_check:
            return
            
        # Validate UUID format
        try:
            uuid.UUID(doc_id_to_check)
        except ValueError:
            print(f"ERROR: Provided doc_id '{doc_id_to_check}' is not a valid UUID format.")
            return
            
        # Query for specific doc_id
        results = collection.get(
            where={"doc_id": doc_id_to_check},
            limit=limit
        )
        
        count = len(results['ids']) if results['ids'] else 0
        print(f"Found {count} chunks matching this doc_id.")
        
        if count > 0:
            print(f"\nShowing first {min(count, limit)} chunks:")
            print("-" * 20)
            for i in range(min(count, limit)):
                chunk_id = results['ids'][i]
                metadata = results['metadatas'][i]
                doc_content = results['documents'][i]
                
                print(f"Chunk ID: {chunk_id}")
                print(f"Metadata: {metadata}")
                print(f"Content Start: {doc_content[:300]}{'...' if len(doc_content) > 300 else ''}")
                print()
        else:
            print(f"No chunks found for doc_id: {doc_id_to_check}")
            
    except Exception as e:
        print(f"\nERROR: Failed to query ChromaDB for doc_id '{doc_id_to_check}'.")
        print(f"Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="Check ChromaDB vector store contents")
    parser.add_argument("--count", action="store_true", help="Print the total number of chunks in the collection.")
    parser.add_argument("--doc-id", type=str, help="Filter chunks by document ID (UUID)")
    parser.add_argument("--limit", type=int, default=5, help="Limit number of results to show (default: 5)")
    
    args = parser.parse_args()
    
    if not args.count and not args.doc_id:
        print("Usage: python check_chroma.py [--count] [--doc-id UUID] [--limit N]")
        parser.print_help()
        return
    
    check_database(
        doc_id_to_check=args.doc_id,
        check_count=args.count,
        limit=args.limit
    )

if __name__ == "__main__":
    main()