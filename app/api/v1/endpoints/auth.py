# app/api/v1/endpoints/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import logging
from datetime import timedelta

from app.schemas import user as user_schemas, token as token_schemas # Import schemas
from app.crud import crud_user # Import user CRUD functions
from app.core import security # Import security utils
from app.api import deps # Import get_db dependency
from app.core.config import settings # Import settings for token expiry
from app.db.models import user as user_models

log = logging.getLogger(__name__)
router = APIRouter()

@router.post(
    "/register",
    response_model=user_schemas.UserRead, # Return public user data
    status_code=status.HTTP_201_CREATED,
    summary="Register New User"
)
def register_user(
    user_in: user_schemas.UserCreate, # Request body validated by this schema
    db: Session = Depends(deps.get_db)
):
    """
    Creates a new user account.
    """
    log.info(f"Registration attempt for email: {user_in.email}")
    # Check if user already exists
    existing_user = crud_user.get_user_by_email(db=db, email=user_in.email)
    if existing_user:
        log.warning(f"Registration failed: Email already registered: {user_in.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered.",
        )
    try:
         user = crud_user.create_user(db=db, user_in=user_in)
         # Don't return password hash
         return user # FastAPI will convert using UserRead response_model
    except ValueError as ve: # Catch specific error from CRUD
          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
         log.error(f"Unexpected error during registration for {user_in.email}: {e}", exc_info=True)
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error during registration.")


@router.post(
    "/token",
    response_model=token_schemas.Token,
    summary="Login For Access Token"
)
async def login_for_access_token( # Can be async or sync depending on authenticate_user
    form_data: OAuth2PasswordRequestForm = Depends(), # Use form data for username/password
    db: Session = Depends(deps.get_db)
):
    """
    OAuth2 compatible token login, get an access token for future requests.
    'username' field from form data is used as the email.
    """
    log.info(f"Login attempt for username (email): {form_data.username}")
    user = crud_user.authenticate_user(
        db=db, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Create JWT token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        subject=user.email, expires_delta=access_token_expires
    )
    log.info(f"Access token generated for user: {user.email}")
    # Return token
    return {"access_token": access_token, "token_type": "bearer"}

# --- Add /users/me endpoint later, requires authentication dependency ---
# @router.get("/users/me", response_model=user_schemas.UserRead)
# async def read_users_me(current_user: user_schemas.UserRead = Depends(deps.get_current_active_user)):
#     return current_user

@router.get(
    "/users/me",
    response_model=user_schemas.UserRead, # Return public user details
    summary="Get Current User",
    description="Fetches details for the currently authenticated user."
)
async def read_users_me(
    # This dependency automatically handles token validation and user fetching
    current_user: user_models.User = Depends(deps.get_current_user)
):
    """
    Get current logged in user details.
    """
    log.info(f"Fetching details for logged in user: {current_user.email}")
    # The dependency already did the work, just return the user object.
    # FastAPI converts the SQLAlchemy model to the Pydantic UserRead schema.
    return current_user
# --- END ADD ---