# app/api/v1/endpoints/chat.py
from fastapi import APIRouter, Depends, HTTPException, Body, status
from sqlalchemy.orm import Session
import logging
import uuid # Import uuid for path parameter validation

# Import schemas, services, dependencies
# Use aliases for clarity if needed, especially if schema names are generic
from app.schemas import chat as chat_schemas
from app.services import chat_service
from app.api import deps
from app.db.models import user as user_models # Import User model

# Import CRUD and Status Enum for checks (even if auth is deferred)
from app.crud import crud_document
from app.db.models.document import DocumentStatus

log = logging.getLogger(__name__)
router = APIRouter()

@router.post(
    "/document/{doc_id}",
    response_model=chat_schemas.ChatResponse, # Final response model with the answer
    summary="Chat with a specific document",
    description="Send a query about a specific document (identified by its UUID) "
                "and receive an answer generated based on its content."
)
async def chat_with_document(
    doc_id: uuid.UUID, # Use UUID type for path parameter validation and auto-docs
    request: chat_schemas.ChatRequest = Body(..., description="The user's query"), # Get query from request body
    db: Session = Depends(deps.get_db), # Inject DB session for potential checks
    current_user: user_models.User = Depends(deps.get_current_user),
):
    """
    Handles chat queries for a specific document using RAG with a Gemini model.
    """
    doc_id_str = str(doc_id) # Convert UUID to string if needed by services/logging
    # --- Placeholder for Authentication ---
    # Replace this with the actual user ID from the authenticated token later
    user_id = current_user.id
    user_id_str = str(user_id)
    log.info(f"Chat request received for doc_id: {doc_id_str} by user: {user_id_str}. Query: '{request.query[:100]}...'")

    # --- Basic Document Validation ---
    # Even without multi-user auth, check if the document exists and is ready
    try:
        # Use a CRUD function (you'll need to implement get_document in crud_document.py)
        # For now, let's assume a basic check or skip it, but it should be here
        db_doc = crud_document.get_document(db=db, doc_id=doc_id, user_id=user_id) # Assumes get_document checks user_id
        if not db_doc:
            log.warning(f"Chat attempt failed: Document not found or user mismatch for doc_id {doc_id_str}, user {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or you do not have permission to access it."
            )

        if db_doc.status != DocumentStatus.READY:
            log.warning(f"Chat attempt failed: Document status is '{db_doc.status}' for doc_id {doc_id_str}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document is not ready for chat. Current status: {db_doc.status}"
            )
        log.info(f"Document {doc_id_str} found and status is READY.")

    except HTTPException:
         raise # Re-raise HTTPException directly
    except Exception as e:
         log.error(f"Error checking document status/existence for doc_id {doc_id_str}: {e}", exc_info=True)
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error verifying document status.")


    # --- Call Chat Service ---
    try:
        # This service function now performs retrieval and calls the LLM
        answer_text = await chat_service.generate_response(
            doc_id=doc_id_str,
            user_id=user_id_str,
            query=request.query
        )

        # Return the final answer using the ChatResponse schema
        return chat_schemas.ChatResponse(answer=answer_text)

    except HTTPException as http_exc:
         # Re-raise specific HTTP exceptions from the service layer (e.g., 503 from LLM)
         log.warning(f"HTTPException during chat processing for doc_id {doc_id_str}: Status={http_exc.status_code}, Detail={http_exc.detail}")
         raise http_exc
    except Exception as e:
        # Catch any other unexpected errors during chat processing
        log.exception(f"Unexpected error processing chat request for doc_id {doc_id_str}: {e}", exc_info=True) # Log full traceback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while processing your chat request."
        )


# --- Placeholder for Global Chat ---
@router.post(
    "/global",
    # response_model=chat_schemas.ChatResponse, # Or maybe a different one with multiple sources?
    summary="Chat across all accessible documents (Not Implemented)",
    description="Send a query to get an answer based on all documents accessible to the user."
)
async def chat_globally(
    request: chat_schemas.ChatRequest = Body(...),
    db: Session = Depends(deps.get_db),
    # current_user: schemas.User = Depends(deps.get_current_active_user) # TODO: Add later
):
    # TODO: Implement global chat logic
    # 1. Get user_id
    # 2. Embed query
    # 3. Query vector_store_service WITHOUT doc_id filter (maybe filter by user_id)
    # 4. Get top K results from potentially multiple documents
    # 5. Option A: Return raw chunks/sources (simpler)
    # 6. Option B: Format context, call LLM for synthesized answer (more complex)
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Global chat not implemented yet.")