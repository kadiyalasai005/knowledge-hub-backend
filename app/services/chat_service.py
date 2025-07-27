# app/services/chat_service.py
import logging
import json
from typing import List, Dict, Optional, Any # Added Any
import uuid

# Import necessary components from the application
from app.core.config import settings
from . import embedding_service    # Service for getting query embeddings
from . import vector_store_service # Service for querying ChromaDB

# Import Google Vertex AI components
try:
    from google.cloud import aiplatform
    import vertexai
    # Import specific classes needed
    from vertexai.generative_models import GenerativeModel, Part, GenerationConfig, SafetySetting, HarmCategory
except ImportError:
    logging.critical("Failed to import google-cloud-aiplatform or vertexai.", exc_info=True)
    GenerativeModel = None # Define as None if import fails
except Exception as e:
     logging.critical(f"CRITICAL: Unexpected error importing Google AI libs: {e}", exc_info=True)
     GenerativeModel = None

log = logging.getLogger(__name__)

# --- Initialize Vertex AI Client and Model ---
gemini_model_client: Optional[GenerativeModel] = None

if GenerativeModel: # Proceed only if import succeeded
    try:
        # Simplified Initialization: Let init handle idempotency checks internally
        # Initialize Vertex AI - ensure project ID is set in settings
        aiplatform.init(
            project=settings.GCP_PROJECT_ID,
            # location=None # Location removed previously
        )
        log.info(f"Vertex AI client initialized in chat_service (Project: {settings.GCP_PROJECT_ID})")

        # Instantiate the Generative Model Client
        gemini_model_client = GenerativeModel(settings.LLM_MODEL)
        log.info(f"Using Gemini model for chat: {settings.LLM_MODEL}")

    except Exception as e:
        log.error(f"Failed to initialize Vertex AI or load generative model in chat_service: {e}", exc_info=True)
        gemini_model_client = None # Ensure it's None on failure
else:
    log.error("GenerativeModel class not available due to import error. Chat service disabled.")

# --- Service Functions ---

async def get_relevant_chunks(doc_id: uuid.UUID, user_id: uuid.UUID, query: str) -> List[Dict]:
    """
    Gets relevant chunks for a query from a specific document using vector search,
    filtering by doc_id and user_id (converted to strings for metadata filter).
    """
    # --- Keep implementation from previous step ---
    log.info(f"Getting relevant chunks for doc_id='{doc_id}', user='{user_id}', query='{query[:50]}...'")
    doc_id_str = str(doc_id)
    user_id_str = str(user_id)
    try:
        query_embedding_list = embedding_service.get_google_embeddings([query])
        if not query_embedding_list or query_embedding_list[0] is None:
            log.error(f"Failed to generate embedding for query: '{query[:50]}...'")
            return []
        query_embedding = query_embedding_list[0]
        filter_metadata = {
            "$and": [
                {"doc_id": doc_id_str},  # Condition 1: doc_id must match
                {"user_id": user_id_str} # Condition 2: user_id must match
            ]
        }
        retrieved_results = vector_store_service.query_vector_db(
            query_embedding=query_embedding, k=settings.TOP_K_RESULTS, filter_metadata=filter_metadata
        )
        return retrieved_results
    except Exception as e:
        log.error(f"Error retrieving chunks for doc_id {doc_id_str}: {e}", exc_info=True)
        return []


async def generate_response(doc_id: uuid.UUID, user_id: uuid.UUID, query: str) -> str:
    """
    Generates an LLM response based on retrieved chunks for a specific document.
    Passes generation/safety config directly to the API call.
    """
    if gemini_model_client is None:
        log.error("Gemini generative model client not initialized. Cannot generate response.")
        raise ConnectionError("Chat service model is not available.")

    # 1. Get relevant chunks
    retrieved_chunks = await get_relevant_chunks(doc_id=doc_id, user_id=user_id, query=query)

    if not retrieved_chunks:
        log.warning(f"No relevant chunks found for doc_id {doc_id} and query '{query[:50]}...'.")
        return "Based on the available content from this document, I cannot answer your question."

    # 2. Format context string
    # ... (keep context formatting logic as before) ...
    try:
        context_parts = [chunk['content'] for chunk in retrieved_chunks if chunk.get('content')]
        if not context_parts:
             log.warning(f"Retrieved chunks had no text content for doc_id {doc_id}.")
             return "Retrieved sections had no text content to analyze for an answer."
        context = "\n\n---\n\n".join(context_parts)
        log.info(f"Formatted context for LLM (approx {len(context)} chars) from {len(context_parts)} chunks.")
    except Exception as format_e:
         log.error(f"Error formatting context for doc_id {doc_id}: {format_e}", exc_info=True)
         return "Sorry, there was an error preparing the information needed to answer your question."

    # 3. Construct LLM Prompt
    # ... (keep prompt construction as before) ...
    prompt = f"""You are an AI assistant for the document with ID '{str(doc_id)}'. Your task is to answer the user's question based *solely* on the provided context below.

    **Instructions:** ... (keep instructions: read context, answer only from context, state if cannot answer, be concise, handle tables) ...

    **Context:**
    ---
    {context}
    ---

    **Question:** {query}

    **Answer:**"""

    # --- Define Generation/Safety Config as Dictionaries HERE ---
    generation_config_dict: Dict[str, Any] = {
        "temperature": 0.3,
        "top_p": 0.8,
        "top_k": 40,
        "max_output_tokens": 1024
    }
    safety_settings_dict: Dict[HarmCategory, SafetySetting.HarmBlockThreshold] = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: SafetySetting.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: SafetySetting.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: SafetySetting.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: SafetySetting.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    }
    # --- End Config Definition ---


    # 4. Call Gemini LLM API
    try:
        log.info(f"Sending request to Gemini model: {settings.LLM_MODEL} for doc_id {doc_id}")

        # --- Pass config dictionaries directly to the generate_content_async method ---
        response = await gemini_model_client.generate_content_async(
            prompt,
            generation_config=generation_config_dict, # Pass dict here
            safety_settings=safety_settings_dict     # Pass dict here
        )
        # --- End Config Passing Change ---

        # 5. Parse and return answer
        # ... (keep response parsing logic as before) ...
        if response.candidates and response.candidates[0].content.parts:
             answer = response.candidates[0].content.parts[0].text
             log.info(f"Received answer from Gemini model (approx {len(answer)} chars) for doc_id {doc_id}.")
             return answer.strip()
        elif response.prompt_feedback and response.prompt_feedback.block_reason:
             block_reason = response.prompt_feedback.block_reason
             log.warning(f"Gemini request blocked for safety (doc_id {doc_id}). Reason: {block_reason}")
             return f"I cannot provide an answer due to safety constraints (Reason: {block_reason})."
        else:
             log.warning(f"Gemini response structure unexpected or empty for doc_id {doc_id}. Response: {response}")
             return "I received an unexpected or empty response from the language model."

    except Exception as e:
        log.error(f"Error calling Gemini API for doc_id {doc_id}: {e}", exc_info=True)
        # Raise error to be caught by API endpoint handler
        raise ConnectionError(f"Language model API error: {e}") from e