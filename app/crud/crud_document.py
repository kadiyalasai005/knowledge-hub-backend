# app/crud/crud_document.py
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
from typing import Optional, List
import uuid # Import uuid

# Import models and schemas
from app.db.models.document import Document, DocumentStatus
from app.schemas import document as document_schemas # Use alias for clarity

log = logging.getLogger(__name__)

# --- Document CRUD Functions ---

def create_document_metadata(db: Session, *, doc_id: uuid.UUID, doc_in: document_schemas.DocumentCreateInternal) -> Document:
    """
    Creates a new document metadata record in the database.
    Assumes doc_in.user_id is the correct type (UUID) provided by the service layer.
    """
    log.info(f"Attempting to create document record for: {doc_in.original_filename}")
    # Create SQLAlchemy model instance from the Pydantic schema
    # Pydantic v2 uses model_dump(), v1 uses dict()
    # Ensure DocumentCreateInternal includes user_id: uuid.UUID
    create_data = doc_in.model_dump(exclude={'id'})
    db_doc = Document(
        id=doc_id, # Use passed ID
        **create_data
    )

    db.add(db_doc)
    try:
        db.commit()
        db.refresh(db_doc)
        log.info(f"Successfully created document record with ID: {db_doc.id}")
        return db_doc
    except SQLAlchemyError as e:
        db.rollback()
        log.error(f"Database error creating document record for {doc_in.original_filename}: {e}", exc_info=True)
        # Re-raise to be handled by the service layer
        raise
    except Exception as e:
        db.rollback()
        log.error(f"Unexpected error creating document record for {doc_in.original_filename}: {e}", exc_info=True)
        raise

def get_document(db: Session, *, doc_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Document]:
    """
    Retrieves a single document by its ID and verifies ownership using User ID.
    Returns the Document object or None if not found or user mismatch.
    """
    log.debug(f"Querying database for doc_id: {doc_id}, user_id: {user_id}")
    try:
        # Query the Document table, filtering by both id (UUID) and user_id (UUID)
        result = db.query(Document).filter(Document.id == doc_id, Document.user_id == user_id).first()
        if result:
            log.debug(f"Found document: {result.original_filename}")
        else:
            # Log potentially sensitive info at debug level
            log.debug(f"Document not found or user mismatch for doc_id: {doc_id}, user_id: {user_id}")
        return result # Returns the Document object or None
    except SQLAlchemyError as e:
        log.error(f"Database error retrieving document for ID {doc_id}: {e}", exc_info=True)
        return None # Return None on database error
    except Exception as e:
         log.error(f"Unexpected error retrieving document for ID {doc_id}: {e}", exc_info=True)
         return None


def get_documents_by_user(
    db: Session, *, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> List[Document]:
    """
    Retrieves a list of documents for a specific user (by UUID) with pagination.
    """
    log.debug(f"Querying documents for user_id: {user_id}, skip: {skip}, limit: {limit}")
    try:
        # Filter using user_id (UUID)
        return db.query(Document)\
                 .filter(Document.user_id == user_id)\
                 .order_by(Document.created_at.desc())\
                 .offset(skip)\
                 .limit(limit)\
                 .all()
    except SQLAlchemyError as e:
         log.error(f"Database error listing documents for user {user_id}: {e}", exc_info=True)
         return [] # Return empty list on error
    except Exception as e:
          log.error(f"Unexpected error listing documents for user {user_id}: {e}", exc_info=True)
          return []


def update_document_status(
        db: Session,
        *,
        db_doc: Document, # Takes the Document object to update
        status: DocumentStatus,
        detail: Optional[str] = None
    ) -> Document:
    """Updates the status and detail of an existing document."""
    log.info(f"Updating status for doc ID {db_doc.id} to {status}")
    db_doc.status = status
    db_doc.detail = detail
    db.add(db_doc) # Add to session to track changes
    try:
        db.commit()
        db.refresh(db_doc)
        log.info(f"Successfully updated status for doc ID {db_doc.id}")
        return db_doc
    except SQLAlchemyError as e:
        log.error(f"Database error updating document status for ID {db_doc.id}: {e}", exc_info=True)
        db.rollback()
        raise
    except Exception as e:
         log.error(f"Unexpected error during status update commit/refresh for ID {db_doc.id}: {e}", exc_info=True)
         db.rollback()
         raise


def delete_document(db: Session, *, db_doc: Document) -> Document:
    """Deletes a document record from the database."""
    doc_id = db_doc.id # Get ID before deletion for logging
    log.warning(f"Deleting document record from DB for doc_id: {doc_id}")
    try:
        db.delete(db_doc)
        db.commit()
        log.info(f"Successfully deleted document record from DB for doc_id: {doc_id}")
        return db_doc # Return the deleted object state (it's expired but might be useful)
    except SQLAlchemyError as e:
         log.error(f"Database error deleting document record for ID {doc_id}: {e}", exc_info=True)
         db.rollback()
         raise # Re-raise for service/API layer to handle
    except Exception as e:
          log.error(f"Unexpected error deleting document record for ID {doc_id}: {e}", exc_info=True)
          db.rollback()
          raise