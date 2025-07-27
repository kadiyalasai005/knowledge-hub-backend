# app/services/vector_store_service.py
import chromadb
import logging
from typing import List, Dict, Optional
from app.core.config import settings # Import settings for path, collection name etc.

log = logging.getLogger(__name__)

# --- Initialize ChromaDB Client ---
# This client/collection is initialized when the module loads, primarily for
# read (query) and delete operations initiated by the API process.
# The Celery task initializes its own client for writes (add).
chroma_client = None
vector_collection = None
try:
    # Initialize ChromaDB client using the persistent path from settings
    chroma_client = chromadb.PersistentClient(path=settings.VECTOR_STORE_PATH)

    # Get or create the collection specified in settings
    vector_collection = chroma_client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"} # Use cosine distance, good for text embeddings
    )
    log.info(f"Vector store service connected to ChromaDB collection '{settings.CHROMA_COLLECTION_NAME}' at {settings.VECTOR_STORE_PATH}")

except ImportError:
     log.error("Failed to import chromadb. Is the 'chromadb' package installed correctly?")
     chroma_client = None
     vector_collection = None
except Exception as e:
    # Catch other potential errors during initialization (e.g., path permissions)
    log.error(f"Failed to initialize ChromaDB client or collection: {e}", exc_info=True)
    chroma_client = None
    vector_collection = None


# --- Query Function ---
def query_vector_db(
    query_embedding: List[float],
    k: int = settings.TOP_K_RESULTS,
    filter_metadata: Optional[Dict[str, str]] = None # Filter expects simple key: string_value
) -> List[Dict]:
    """
    Queries the ChromaDB collection for relevant chunks based on embedding similarity
    and optional metadata filtering.

    Args:
        query_embedding: The embedding vector of the user's query.
        k: The number of top results to retrieve.
        filter_metadata: A dictionary specifying metadata fields and values to filter on
                         (e.g., {"doc_id": "some-uuid-string", "user_id": "some-user-id-string"}).

    Returns:
        A list of result dictionaries, each containing 'id', 'content', 'metadata', 'distance'.
        Returns an empty list if the collection is unavailable or on error.
    """
    results = []
    if vector_collection is None:
        log.error("ChromaDB collection is not available for querying.")
        # Depending on desired behavior, could raise or just return empty
        return results # Return empty list if service isn't ready

    try:
        log.info(f"Querying ChromaDB collection '{settings.CHROMA_COLLECTION_NAME}' with k={k}, filter={filter_metadata}")
        # Prepare query parameters, including the 'where' clause if filter_metadata is provided
        query_params = {
            "query_embeddings": [query_embedding],
            "n_results": k,
            "include": ["metadatas", "documents", "distances"] # Request needed fields
        }
        if filter_metadata:
            query_params["where"] = filter_metadata

        # Execute the query
        query_results = vector_collection.query(**query_params)

        # Process results into a more usable list of dicts
        if query_results and query_results.get("ids") and query_results["ids"][0]:
             count = len(query_results["ids"][0])
             log.info(f"ChromaDB query returned {count} results.")
             # Iterate safely, checking if lists exist and have the expected index
             ids = query_results["ids"][0]
             documents = query_results.get("documents", [[]])[0]
             metadatas = query_results.get("metadatas", [[]])[0]
             distances = query_results.get("distances", [[]])[0]

             for i, doc_id in enumerate(ids):
                 results.append({
                     "id": doc_id,
                     "content": documents[i] if documents and len(documents) > i else None,
                     "metadata": metadatas[i] if metadatas and len(metadatas) > i else None,
                     "distance": distances[i] if distances and len(distances) > i else None
                 })
        else:
             log.info("ChromaDB query returned no results for the given parameters.")

        return results

    except Exception as e:
        log.error(f"Error querying ChromaDB collection '{settings.CHROMA_COLLECTION_NAME}': {e}", exc_info=True)
        return [] # Return empty list on error

# --- Delete Function ---
def delete_document_chunks(doc_id: str):
    """
    Deletes all chunks associated with a specific doc_id from ChromaDB collection.

    Args:
        doc_id: The string representation of the document UUID whose chunks should be deleted.
    """
    if vector_collection is None:
        log.error("ChromaDB collection is not available. Cannot delete chunks.")
        raise RuntimeError("Vector store service is not available for deletion.")

    log.warning(f"Attempting to delete all chunks from ChromaDB for doc_id: {doc_id}")
    try:
        # Use the 'where' filter to target specific document chunks based on metadata
        # Ensure the key 'doc_id' matches exactly what was stored in metadata
        vector_collection.delete(where={"doc_id": doc_id})
        log.info(f"Successfully submitted deletion request to ChromaDB for doc_id: {doc_id} (Note: delete returns no confirmation of items deleted).")
        # Note: ChromaDB delete might not raise an error if no matching documents are found.
    except Exception as e:
        log.error(f"Error deleting chunks from ChromaDB for doc_id {doc_id}: {e}", exc_info=True)
        # Re-raise for the caller (e.g., document_service.delete_document_data) to handle
        raise RuntimeError(f"Failed to delete vector chunks for doc_id {doc_id}") from e