# app/schemas/document.py
from pydantic import BaseModel, EmailStr, ConfigDict # Import ConfigDict for Pydantic V2
from typing import Optional, List # Keep List if used elsewhere
import uuid # <-- Make sure uuid is imported
from datetime import datetime
from app.db.models.document import DocumentStatus

# Shared properties
class DocumentBase(BaseModel):
    original_filename: Optional[str] = None
    mime_type: Optional[str] = None

# Internal creation schema (keep user_id as UUID if passed from service)
class DocumentCreateInternal(DocumentBase):
    original_filename: str
    mime_type: str
    storage_path: str
    user_id: uuid.UUID # <-- Should expect UUID from service layer now
    status: DocumentStatus = DocumentStatus.PENDING

# Base schema for reading from DB - reflects DB model types
class DocumentInDBBase(DocumentBase):
    id: uuid.UUID
    # --- CHANGE THIS LINE ---
    user_id: uuid.UUID # <-- Change from Optional[str] to uuid.UUID
    # --- END CHANGE ---
    storage_path: str
    status: DocumentStatus
    detail: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    mime_type: Optional[str] = None

    # Pydantic V2 Configuration: Enable ORM mode (reading from attributes)
    model_config = ConfigDict(from_attributes=True)
    # class Config: # For Pydantic v1
    #     orm_mode = True


# Schema for returning document details to client
class DocumentRead(DocumentInDBBase):
    pass # Inherits fields including corrected user_id

# Schema for status response
class DocumentStatusResponse(BaseModel):
    status: DocumentStatus
    detail: Optional[str] = None

# Schema for upload response
class DocumentUploadResponse(BaseModel):
    message: str
    doc_id: uuid.UUID
    filename: str
    status: DocumentStatus # Initial status (e.g., PENDING)

class DocumentViewResponse(BaseModel):
    view_url: Optional[str] = None
    message: str
    filename: Optional[str] = None