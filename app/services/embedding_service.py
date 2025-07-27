# app/services/embedding_service.py
import tiktoken
import logging
from typing import List
from app.core.config import settings # Import model name, chunk settings
from google.cloud import aiplatform # GCP Client library
from vertexai.language_models import TextEmbeddingModel # Specific model class

log = logging.getLogger(__name__)

# Initialize Vertex AI client (do this once, maybe move to main app setup later)
# Assumes application default credentials (ADC) are set up (e.g., via gcloud auth login)
try:
    aiplatform.init(project=settings.GCP_PROJECT_ID) # Can be None if not set, library might infer) # project/location often inferred from ADC
    log.info(f"Vertex AI client initializing with Project ID: {settings.GCP_PROJECT_ID}")
    log.info("Vertex AI client initialized successfully.")
    # Instantiate the embedding model client
    embedding_model_client = TextEmbeddingModel.from_pretrained(settings.EMBEDDING_MODEL)
    log.info(f"Using embedding model: {settings.EMBEDDING_MODEL}")

except ValueError as e:
    # Catch the specific project ID error if it happens here
    log.error(f"Vertex AI Initialization Error: {e}. Ensure GCP_PROJECT_ID is set correctly in .env and ADC/credentials are valid.", exc_info=True)
    # Keep embedding_model_client as None

except Exception as e:
    log.error(f"Failed to initialize Vertex AI or load embedding model: {e}", exc_info=True)
    embedding_model_client = None # Handle this downstream

def split_text_into_chunks(text: str,
                           max_tokens: int = settings.CHUNK_SIZE_TOKENS,
                           overlap: int = settings.CHUNK_OVERLAP_TOKENS) -> List[str]:
    """Splits text into chunks based on token count using tiktoken."""
    # (Keep implementation from previous phases - uses tiktoken)
    if not text:
        return []
    try:
        tokenizer = tiktoken.get_encoding("cl100k_base") # Common encoder
    except Exception as e:
        log.error(f"Failed to get tiktoken encoder: {e}", exc_info=True)
        # Basic fallback split
        words = text.split()
        step = max_tokens - overlap
        if step <= 0: step = max_tokens # Avoid infinite loop if overlap >= max_tokens
        return [" ".join(words[i:i + max_tokens]) for i in range(0, len(words), step)]

    tokens = tokenizer.encode(text)
    chunks = []
    i = 0
    while i < len(tokens):
        end = min(i + max_tokens, len(tokens))
        chunk_tokens = tokens[i:end]
        try:
            chunk_text = tokenizer.decode(chunk_tokens)
            # Avoid adding empty chunks if decode results in nothing
            if chunk_text.strip():
                chunks.append(chunk_text)
        except Exception as decode_e:
            log.warning(f"Failed to decode token chunk: {decode_e}")

        step = max_tokens - overlap
        if step <= 0: step = 1 # Ensure progress
        i += step

    log.info(f"Split text into {len(chunks)} chunks.")
    return chunks

def get_google_embeddings(texts: List[str]) -> List[List[float]]:
    """Generates embeddings using Google Vertex AI TextEmbeddingModel."""
    if embedding_model_client is None:
        log.error("Embedding model client failed to initialize. Cannot get embeddings.")
        # Raise a specific error that the service layer / endpoint can catch
        raise RuntimeError("Embedding service is unavailable due to initialization failure.")
    if not texts:
        return []

    log.info(f"Requesting embeddings for {len(texts)} text chunks...")
    try:
        # The SDK handles batching internally to some extent, but check API limits
        # Max 250 items per request for most regions, 5 for others - need robust batching
        # Let's implement simple batching for safety
        all_embeddings = []
        batch_size = 5 # Use a safe small batch size based on Vertex AI limits for some regions
                      # Increase if you know your region supports more (e.g., 250 for us-central1)

        for i in range(0, len(texts), batch_size):
             batch_texts = texts[i:i + batch_size]
             # Handle potential empty strings in the batch if necessary
             batch_texts = [t if t.strip() else " " for t in batch_texts]

             instances = embedding_model_client.get_embeddings(batch_texts)
             batch_embeddings = [embedding.values for embedding in instances]
             all_embeddings.extend(batch_embeddings)
             log.info(f"Processed batch {i//batch_size + 1}/{(len(texts)+batch_size-1)//batch_size} for embeddings.")
             # Consider adding a small delay if hitting rate limits
             # import time; time.sleep(0.1)

        log.info(f"Successfully generated embeddings for {len(all_embeddings)} chunks.")
        return all_embeddings

    except Exception as e:
        log.error(f"Failed to get embeddings from Vertex AI: {e}", exc_info=True)
        # Depending on requirements, you might return partial results or raise
        raise # Re-raise for now, task handler should catch it