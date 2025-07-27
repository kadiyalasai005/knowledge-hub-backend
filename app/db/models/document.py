# app/db/models/document.py
import uuid as uuid_pkg # Use alias to avoid conflict with uuid type
import enum
from datetime import datetime
from typing import Optional, List # Import List for relationship

from sqlalchemy import Column, String, DateTime, Text, Boolean # Boolean not used here?
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy import ForeignKey
# Correct imports for SQLAlchemy 2.0 style
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .user import User

# Import Base from the correct location
#from app.db.database import Base # Assuming Base is in database.py now, adjust if needed
from app.db.base_class import Base # If you kept base_class.py

# Define possible statuses using Python's Enum
class DocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid_pkg.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    # --- UPDATE user_id to be a ForeignKey ---
    user_id: Mapped[uuid_pkg.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False) # Use user ID as string or UUID depending on User model PK type - let's make it UUID to match User.id
    # user_id: Mapped[uuid_pkg.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False) # <-- Alternative if user PK is UUID
    # --- END UPDATE ---

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False) # Path where file is stored (local or GCS URI)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True) # Nullable initially
    status: Mapped[DocumentStatus] = mapped_column(SQLEnum(DocumentStatus), default=DocumentStatus.PENDING, index=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # For storing error messages or other info
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    # --- ADD Relationship back to User ---
    user: Mapped["User"] = relationship("User", back_populates="documents")
    # --- END ADD ---

    def __repr__(self):
        return f"<Document(id={self.id}, name='{self.original_filename}', status='{self.status}')>"

# --- Make sure User model is imported somewhere SQLAlchemy can find it ---
# You might need to import it in your models/__init__.py if you have one,
# or ensure Base metadata is collected correctly where User is defined.
from .user import User # Add this import at the end or in an __init__.py