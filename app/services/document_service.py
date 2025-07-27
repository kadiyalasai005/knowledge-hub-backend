# app/services/document_service.py
from fastapi import UploadFile, HTTPException, status as http_status
from sqlalchemy.orm import Session
# Removed: import shutil
# Removed: from pathlib import Path
import logging
import os # Keep os for cleanup check potentially, though GCS handles deletion mostly
import uuid
from typing import List, Optional

# Import DB model AND the Enum directly
from app.db.models.document import Document, DocumentStatus

# Import specific schemas and CRUD module
from app.schemas import document as document_schemas
from app.crud import crud_document

# --- Import the Celery task ---
try:
    from tasks.document_tasks import process_document as process_document_task
    log_task_import = logging.getLogger(__name__) # Use logger from this module
    log_task_import.info("Successfully imported Celery task 'process_document'.")
except ImportError as e:
     logging.critical(f"CRITICAL: Could not import Celery task 'process_document': {e}. Background processing will fail.", exc_info=True)
     process_document_task = None
except Exception as e:
     logging.critical(f"CRITICAL: Unexpected error importing Celery task: {e}", exc_info=True)
     process_document_task = None

# --- Import GCS storage service ---
from . import gcs_storage_service
# Import vector store service for deletion part
from . import vector_store_service


log = logging.getLogger(__name__)

# --- REMOVED UPLOAD_DIR and save_upload_file_local ---

# --- Keep delete_storage_file if needed elsewhere, or rely solely on GCS delete ---
# It's better practice to let gcs_storage_service handle all storage operations now.
# def delete_storage_file(storage_path: str): ... # Removed


async def handle_document_upload(db: Session, *, file: UploadFile, user_id: uuid.UUID) -> Document:
    """
    Handles initial document upload: uploads file to GCS, creates metadata record in DB (PENDING),
    and enqueues background processing task via Celery.
    Returns the initial SQLAlchemy Document model instance.
    """
    log.info(f"Handling GCS upload for filename: {file.filename} by user: {user_id}")
    db_doc: Optional[Document] = None
    gcs_uri: Optional[str] = None
    doc_id = uuid.uuid4() # Generate ID upfront to use in GCS path

    try:
        # 1. Upload File to GCS (Service handles connection/bucket)
        # The service function generates the structured path like users/.../docs/.../filename
        gcs_uri = await gcs_storage_service.upload_file_to_gcs(
            file=file, user_id=user_id, doc_id=doc_id
        )
        # file object is closed within upload_file_to_gcs

        # 2. Create Initial Metadata Record in PostgreSQL
        # Ensure DocumentCreateInternal schema can handle UUID for user_id
        # Ensure CRUD function can handle passed ID
        doc_in = document_schemas.DocumentCreateInternal(
            # Note: We pass the generated doc_id here, ensure your CRUD handles it
            # Alternatively, let DB generate ID and refresh db_doc after creation
            original_filename=file.filename, # Use original filename here
            storage_path=gcs_uri,        # Store the GCS URI (gs://...)
            user_id=user_id,             # Pass the UUID from authenticated user
            mime_type=file.content_type or "application/octet-stream", # Pass MIME type
            status=DocumentStatus.PENDING    # Initial status
        )
        # Assuming crud function accepts doc_id or we refetch after creation
        db_doc = crud_document.create_document_metadata(db=db, doc_id=doc_id, doc_in=doc_in)
        # Optional: Refresh if create doesn't load relationships or all defaults
        # db.refresh(db_doc)
        log.info(f"Document metadata created ID {db_doc.id}, status {db_doc.status}, path {db_doc.storage_path}")

        # 3. Enqueue Celery Task for background processing
        if process_document_task is None:
             log.critical(f"Celery task 'process_document' not available. Cannot process doc ID {db_doc.id}")
             raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail="Background processing system is unavailable.")

        log.info(f"Enqueueing background processing task for doc ID {db_doc.id}")
        try:
            # Pass GCS URI as the file_path argument to the task
            process_document_task.delay(
                doc_id_str=str(db_doc.id),
                user_id=str(user_id), # Convert UUID to string for Celery arg
                file_path=gcs_uri      # Pass GCS URI (gs://...)
            )
            log.info(f"Task enqueued successfully for doc ID {db_doc.id}")
        except Exception as celery_e:
             # Handle errors during task sending (e.g., Redis connection error)
             log.error(f"Failed to enqueue Celery task for doc ID {db_doc.id}: {celery_e}", exc_info=True)
             # Attempt to rollback DB and delete GCS file for consistency
             try:
                  if db_doc: db.delete(db_doc); db.commit(); log.warning(f"Rolled back DB record for doc ID {db_doc.id}.")
             except Exception as revert_e: log.error(f"Failed to rollback DB record: {revert_e}"); db.rollback()
             if gcs_uri: await gcs_storage_service.delete_file_from_gcs(gcs_uri) # Attempt GCS cleanup

             raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to schedule document processing.")

        # Return the document object immediately with PENDING status
        return db_doc

    except HTTPException as e:
        # If GCS upload failed, gcs_uri might be None
        # If DB create failed after GCS upload, gcs_uri will be set
        log.error(f"HTTPException during initial upload handling for {file.filename}: {e.detail}", exc_info=False)
        if gcs_uri: # If file was uploaded to GCS but subsequent steps failed
            log.warning(f"Attempting GCS cleanup for {gcs_uri} due to error: {e.detail}")
            try: await gcs_storage_service.delete_file_from_gcs(gcs_uri)
            except Exception as cleanup_e: log.error(f"Failed GCS cleanup for {gcs_uri}: {cleanup_e}")
        raise e # Re-raise the original HTTPException
    except Exception as e:
        # Catch unexpected errors during the overall process
        log.error(f"Unexpected error during initial upload handling for {file.filename}: {e}", exc_info=True)
        if gcs_uri: # If file was uploaded to GCS but subsequent steps failed
            log.warning(f"Attempting GCS cleanup for {gcs_uri} due to unexpected error.")
            try: await gcs_storage_service.delete_file_from_gcs(gcs_uri)
            except Exception as cleanup_e: log.error(f"Failed GCS cleanup for {gcs_uri}: {cleanup_e}")
        # Ensure DB session is rolled back if db_doc was added but not committed before error
        if db_doc and db_doc in db.new:
             db.rollback()
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initiate document upload process.") from e


async def delete_document_data(db: Session, *, doc_id: uuid.UUID, user_id: uuid.UUID) -> bool:
     """
     Orchestrates deletion: finds doc, deletes GCS file, vector chunks, DB record.
     Uses UUID for user_id check.
     """
     log.info(f"Initiating deletion process for doc_id: {doc_id}, user: {user_id}")
     # 1. Find document and check ownership using UUID
     db_doc = crud_document.get_document(db=db, doc_id=doc_id, user_id=user_id)
     if not db_doc:
          log.warning(f"Deletion failed: Document {doc_id} not found for user {user_id}.")
          return False # Indicate not found

     gcs_uri = db_doc.storage_path # Get GCS URI from DB
     doc_id_str = str(db_doc.id) # Convert to string for vector store filter if needed
     all_succeeded = True # Use a flag to track overall success

     # 2. Delete from Vector Store
     log.debug(f"Attempting to delete vector chunks for doc_id {doc_id_str}")
     try:
          # Pass doc_id as string if metadata stores it as string
          vector_store_service.delete_document_chunks(doc_id=doc_id_str)
          log.info(f"Vector chunk deletion request successful for doc_id {doc_id_str}")
     except Exception as e:
          log.error(f"Failed to delete vector chunks for doc_id {doc_id_str}: {e}", exc_info=True)
          all_succeeded = False # Mark failure but continue cleanup

     # 3. Delete from File Storage (GCS)
     log.debug(f"Attempting to delete GCS file: {gcs_uri}")
     try:
          # Call the GCS delete function using the stored URI
          await gcs_storage_service.delete_file_from_gcs(gcs_uri)
          log.info(f"GCS file deletion request successful for {gcs_uri}")
     except Exception as e:
          # Log error but maybe don't mark overall deletion as failed just for this?
          log.error(f"Failed to delete storage file {gcs_uri} for doc_id {doc_id_str}: {e}", exc_info=True)

     # 4. Delete from Metadata DB (Do this last)
     log.debug(f"Attempting to delete metadata record from DB for doc_id {doc_id_str}")
     try:
          crud_document.delete_document(db=db, db_doc=db_doc)
          log.info(f"Successfully deleted metadata record from DB for doc_id {doc_id_str}")
     except Exception as e:
          log.error(f"Failed to delete DB record for doc_id {doc_id_str}: {e}", exc_info=True)
          all_succeeded = False # Mark failure

     if all_succeeded:
          log.info(f"Successfully completed deletion process for doc_id: {doc_id_str}")
     else:
          log.warning(f"Deletion process completed with one or more errors for doc_id: {doc_id_str}")

     return all_succeeded # Return overall success/failure status

# --- Other potential service functions ---
# async def get_document_status(...)
# async def list_documents(...)