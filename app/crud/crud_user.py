# app/crud/crud_user.py
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
from typing import Optional

from app.db.models.user import User
from app.schemas import user as user_schemas # Use alias
from app.core.security import get_password_hash, verify_password

log = logging.getLogger(__name__)

def get_user_by_email(db: Session, *, email: str) -> Optional[User]:
    """Gets a user by email."""
    try:
         return db.query(User).filter(User.email == email).first()
    except SQLAlchemyError as e:
         log.error(f"Database error getting user by email {email}: {e}", exc_info=True)
         return None

def create_user(db: Session, *, user_in: user_schemas.UserCreate) -> User:
    """Creates a new user."""
    log.info(f"Attempting to create user with email: {user_in.email}")
    hashed_password = get_password_hash(user_in.password)
    db_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
        # Set defaults is_active=True, is_superuser=False from model
    )
    db.add(db_user)
    try:
        db.commit()
        db.refresh(db_user)
        log.info(f"Successfully created user: {db_user.email} (ID: {db_user.id})")
        return db_user
    except SQLAlchemyError as e:
        db.rollback()
        log.error(f"Database error creating user {user_in.email}: {e}", exc_info=True)
        # Specific check for unique constraint might be needed if depending on exception type
        if "unique constraint" in str(e).lower():
             raise ValueError("Email already registered") # Raise specific error
        raise # Re-raise general DB error
    except Exception as e:
        db.rollback()
        log.error(f"Unexpected error creating user {user_in.email}: {e}", exc_info=True)
        raise


def authenticate_user(db: Session, *, email: str, password: str) -> Optional[User]:
    """Authenticates a user."""
    log.debug(f"Attempting authentication for email: {email}")
    user = get_user_by_email(db=db, email=email)
    if not user:
        log.warning(f"Authentication failed: User not found for email {email}")
        return None
    if not user.is_active:
        log.warning(f"Authentication failed: User inactive for email {email}")
        return None
    if not verify_password(password, user.hashed_password):
        log.warning(f"Authentication failed: Invalid password for email {email}")
        return None
    log.info(f"Authentication successful for email: {email}")
    return user

# Add get_user(id), update_user, etc. later if needed