# app/api/v1/endpoints/documents.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import logging
import uuid
from typing import List # Import List
#from fastapi.responses import FileResponse 
import os
from app.services import gcs_storage_service

from app.schemas.msg import Msg # Import Msg schema
from app.crud import crud_document
# Import schemas and services correctly
from app.schemas import document as document_schemas
from app.services import document_service
from app.api import deps
from fastapi import status # Import status for codes
from app.db.models.document import DocumentStatus
from app.db.models import user as user_models # Import User model for type hint

log = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_MIME_TYPES = [
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/gif",
    "image/bmp",
    "image/webp",
]

@router.get(
    "/{doc_id}/status",
    response_model=document_schemas.DocumentStatusResponse,
    summary="Get Document Status",
    description="Retrieves the current processing status and any detail message for a specific document."
)
def get_document_status(
    doc_id: uuid.UUID,
    current_user: user_models.User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    user_id = current_user.id
    log.info(f"Getting status for doc_id: {doc_id}, user: {user_id}")

    db_doc = crud_document.get_document(db=db, doc_id=doc_id, user_id=user_id)
    if not db_doc:
        log.warning(f"Status check failed: Document {doc_id} not found for user {user_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or permission denied.")

    return document_schemas.DocumentStatusResponse(
        status=db_doc.status,
        detail=db_doc.detail
    )


@router.get(
    "/{doc_id}",
    response_model=document_schemas.DocumentRead, # Use the existing schema for the response
    summary="Get Document Details",
    description="Retrieves the full details for a specific document by its ID.",
    responses={
        404: {"description": "Document not found or permission denied."}
    }
)
def read_document(
    doc_id: uuid.UUID, # Path parameter validated as UUID
    current_user: user_models.User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    """
    Handles GET request to retrieve details of a single document.
    """
    user_id = current_user.id
    log.info(f"Request received to read document details for doc_id: {doc_id}, user: {user_id}")

    # Use the existing CRUD function to fetch the document
    db_doc = crud_document.get_document(db=db, doc_id=doc_id, user_id=user_id)

    # Handle case where document is not found for this user
    if db_doc is None:
        log.warning(f"Read request failed: Document {doc_id} not found for user {user_id}.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or permission denied."
        )

    # Log success and return the SQLAlchemy model instance
    # FastAPI will automatically convert it to the DocumentRead schema based on response_model
    log.info(f"Returning details for document: {db_doc.original_filename} (ID: {doc_id})")
    return db_doc

@router.post(
    "",
    response_model=document_schemas.DocumentUploadResponse, # Use upload response schema
    status_code=status.HTTP_202_ACCEPTED # Use 202 Accepted for async
)
async def upload_document_and_process_sync(
    *,
    db: Session = Depends(deps.get_db),
    current_user: user_models.User = Depends(deps.get_current_user),
    file: UploadFile = File(...),
    # current_user: schemas.User = Depends(deps.get_current_active_user) # Add later
):
    """
    Accepts document upload, saves it, creates initial metadata record,
    and triggers background processing task.
    """
    log.info(f"Received file upload request: {file.filename},Content-Type: {file.content_type}")
    user_id = current_user.id

    if file.content_type not in ALLOWED_MIME_TYPES:
        log.warning(f"Upload rejected: Invalid file type '{file.content_type}' for file '{file.filename}'")
        raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail=f"Invalid file type: {file.content_type}. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
        )
    try:
        # Call the service layer - returns the initial DB record with PENDING status
        initial_doc_model = await document_service.handle_document_upload(db=db, file=file, user_id=user_id)

        # Return confirmation immediately
        return document_schemas.DocumentUploadResponse(
            message="File uploaded successfully. Processing started in background.",
            doc_id=initial_doc_model.id,
            filename=initial_doc_model.original_filename,
            status=initial_doc_model.status # Should be PENDING here
        )

    except HTTPException as http_exc:
        # Re-raise specific HTTP exceptions (like 400, 500, 503)
        raise http_exc
    except Exception as e:
        # Catch unexpected errors during the whole process
        log.exception(f"Unexpected error during document upload endpoint: {file.filename}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred during file upload.")

@router.get(
    "",
    response_model=List[document_schemas.DocumentRead], # Return a list of documents
    summary="List User's Documents",
    description="Retrieves a list of documents uploaded by the user, with pagination."
)

def list_documents(
    current_user: user_models.User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
    skip: int = 0, # Query parameter for pagination offset
    limit: int = 100, # Query parameter for max items per page
):
    user_id = current_user.id # Use the ID (UUID) from the authenticated user

    log.info(f"Listing documents for user: {user_id}, skip={skip}, limit={limit}")
    try:
        documents = crud_document.get_documents_by_user(
            db=db, user_id=user_id, skip=skip, limit=limit
        )
        # FastAPI automatically converts the list of SQLAlchemy models
        # to a list of Pydantic schemas defined in response_model
        return documents
    except Exception as e:
        # Catch potential errors during DB query if not caught by CRUD
        log.exception(f"Error listing documents for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve documents.")

@router.delete(
    "/{doc_id}",
    response_model=Msg, # Return simple message on success
    summary="Delete Document",
    description="Deletes a document and its associated data (metadata, vector chunks, stored file)."
)

async def delete_document_endpoint( # Use async if service call is async
    doc_id: uuid.UUID,
    current_user: user_models.User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    user_id = current_user.id
    log.info(f"Received request to delete doc_id: {doc_id}, user: {user_id}")

    try:
         # Call the service layer function to handle orchestration
         success = await document_service.delete_document_data(db=db, doc_id=doc_id, user_id=user_id)

         if not success:
              # Service layer logged warnings/errors, but doc might have been partially deleted or not found
              # Decide on appropriate response - maybe still 404 if initial get failed?
              # Let's assume the service handled the "not found" case adequately and return 404 from there
              # If it returns False due to partial delete, maybe 500? Let's adjust service logic if needed.
              # For now, if service returns False maybe it means not found initially.
              raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or deletion failed.")

         return Msg(detail="Document deleted successfully")

    except HTTPException as http_exc:
         raise http_exc # Re-raise exceptions from service/crud layer
    except Exception as e:
         log.exception(f"Unexpected error during document deletion endpoint for doc_id {doc_id}: {e}", exc_info=True)
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred during document deletion.")

@router.get(
    "/{doc_id}/view",
    response_model=document_schemas.DocumentViewResponse, # <-- Use new schema
    summary="Get Document View URL",
    description="Retrieves a temporary signed URL to view/download the document from cloud storage.",
    responses={ # Update responses
        200: {"description": "Signed URL generated successfully."},
        404: {"description": "Document or underlying file not found."},
        500: {"description": "Could not generate view URL."},
        503: {"description": "Storage service unavailable."}
    }
)
async def view_document( # Make async
    doc_id: uuid.UUID,
    db: Session = Depends(deps.get_db),
    current_user: user_models.User = Depends(deps.get_current_user)
):
    user_id = current_user.id
    log.info(f"Request for view URL for doc_id: {doc_id} by user: {user_id}")

    db_doc = crud_document.get_document(db=db, doc_id=doc_id, user_id=user_id)
    if not db_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    storage_uri = db_doc.storage_path
    if not storage_uri or not storage_uri.startswith("gs://"):
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file location not found or invalid.")

    try:
        # Generate signed URL (default ~15 min expiry)
        signed_url = await gcs_storage_service.generate_signed_view_url(storage_uri=storage_uri)
        if not signed_url:
             # Likely blob not found in GCS
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in cloud storage.")

        log.info(f"Generated signed URL for doc_id {doc_id}")
        return document_schemas.DocumentViewResponse(
            view_url=signed_url,
            message="Signed URL generated successfully.",
            filename=db_doc.original_filename
        )
    except HTTPException as e:
         raise e # Re-raise specific errors (e.g., 404, 503)
    except Exception as e:
         log.error(f"Error generating signed URL for doc_id {doc_id}: {e}", exc_info=True)
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not generate view URL.")


# --- Add other document endpoints later ---