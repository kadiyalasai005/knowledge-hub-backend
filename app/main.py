# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import re # Import re for splitting
import logging # Import logging

from app.core.config import settings
from app.api.v1.api import api_router

log = logging.getLogger(__name__) # Get logger if not already defined

# Create FastAPI app instance
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# --- ADD CORS PROCESSING LOGIC HERE ---
allowed_origins = []
if settings.BACKEND_CORS_ORIGINS:
    try:
        # Split by space or comma, remove empty strings
        raw_origins = settings.BACKEND_CORS_ORIGINS
        allowed_origins = [origin.strip() for origin in re.split(r'[ ,]+', raw_origins) if origin.strip()]
        log.info(f"Applying CORS for origins: {allowed_origins}")
    except Exception as e:
        log.error(f"Could not parse BACKEND_CORS_ORIGINS: '{settings.BACKEND_CORS_ORIGINS}'. Error: {e}", exc_info=True)
        allowed_origins = [] # Default to empty list on parsing error
else:
     log.warning("BACKEND_CORS_ORIGINS not set in environment. CORS might not work as expected.")


# Set CORS middleware using the processed list
if allowed_origins: # Only add middleware if origins are configured
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins, # Pass the parsed list of strings
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Restrict to specific methods
        allow_headers=["Authorization", "Content-Type", "Accept"],  # Restrict to specific headers
    )
# --- END CORS PROCESSING LOGIC ---

# Health Check
@app.get("/", tags=["Health Check"])
async def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}! API is running."}

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)