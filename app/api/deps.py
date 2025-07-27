# app/api/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt # For JWT decoding/validation
from pydantic import ValidationError
import logging

# Import settings, schemas, models, crud, security utils
from app.core.config import settings
from app.core import security # Needed for SECRET_KEY, ALGORITHM if not directly from settings
from app.schemas import token as token_schemas # For TokenData schema
from app.schemas import user as user_schemas # For UserRead maybe? No, return model
from app.db.models import user as user_models # Import the User model
from app.crud import crud_user
from app.db.database import SessionLocal # Keep if get_db is here

log = logging.getLogger(__name__)

# --- Keep get_db Dependency ---
def get_db():
    if SessionLocal is None:
        log.error("Database session factory (SessionLocal) is not initialized.")
        raise HTTPException(status_code=503, detail="Database not available")
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception as e:
            log.error(f"Error closing DB session: {e}", exc_info=True)

# --- ADD Authentication Dependency ---

# Define the OAuth2 scheme. 'tokenUrl' points to YOUR login endpoint.
# This tells FastAPI/SwaggerUI where to go to get a token.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

async def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme) # Extracts token from Authorization: Bearer header
) -> user_models.User: # Return the SQLAlchemy User model
    """
    Dependency to get the current user from the JWT token in the request header.
    Raises HTTPException 401 if token is invalid, expired, or user not found.
    """
    # Define the exception to raise for various authentication errors
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decode the JWT token
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        # The 'sub' (subject) claim should hold our unique user identifier (email)
        username: str | None = payload.get("sub")
        if username is None:
            log.warning("Token validation failed: 'sub' claim missing.")
            raise credentials_exception

        # Store token data in a schema for validation (optional but good practice)
        token_data = token_schemas.TokenData(sub=username)
        log.debug(f"Token decoded successfully for subject: {token_data.sub}")

    except JWTError as e:
        # Handle errors like expired signature, invalid signature etc.
        log.warning(f"Token validation failed: JWTError - {e}", exc_info=True)
        raise credentials_exception from e
    except ValidationError as e:
        # Handle Pydantic validation errors if TokenData schema fails
        log.warning(f"Token validation failed: Pydantic ValidationError - {e}", exc_info=True)
        raise credentials_exception from e
    except Exception as e:
        # Catch any other unexpected errors during decode/validation
        log.error(f"Unexpected error during token decoding: {e}", exc_info=True)
        raise credentials_exception from e


    # Fetch the user from the database based on the email in the token's subject
    user = crud_user.get_user_by_email(db, email=token_data.sub)
    if user is None:
        log.warning(f"Token validation failed: User '{token_data.sub}' not found in DB.")
        raise credentials_exception

    # Optional: Add checks here if needed (e.g., user is active)
    # if not user.is_active:
    #     log.warning(f"Token validation failed: User '{token_data.sub}' is inactive.")
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    log.info(f"Authenticated user retrieved from token: {user.email}")
    return user # Return the SQLAlchemy User model object

# --- Optional: Dependency for active users ---
# async def get_current_active_user(
#     current_user: user_models.User = Depends(get_current_user),
# ) -> user_models.User:
#     if not current_user.is_active:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
#     return current_user

# --- Optional: Dependency for superusers ---
# async def get_current_active_superuser(
#     current_user: user_models.User = Depends(get_current_active_user),
# ) -> user_models.User:
#     if not current_user.is_superuser:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="The user doesn't have enough privileges",
#         )
#     return current_user