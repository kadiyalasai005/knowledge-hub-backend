# app/core/config.py
from pydantic_settings import BaseSettings
from typing import List, Union, Optional, Any
# Use validator from pydantic directly if using v2, or keep as is if v1 validator decorator works
from pydantic import field_validator, validator, PostgresDsn, AnyHttpUrl
import re
import logging # Import logging

log = logging.getLogger(__name__)

class Settings(BaseSettings):
    PROJECT_NAME: str = "Knowledge Hub API"
    API_V1_STR: str = "/api/v1"

    # --- DATABASE ---
    POSTGRES_SERVER: str = "db" # Default to service name
    POSTGRES_USER: str  # Remove default - must be set in environment
    POSTGRES_PASSWORD: str  # Remove default - must be set in environment
    POSTGRES_DB: str = "knowledge_hub_db"
    DATABASE_URL: Optional[PostgresDsn] = None

    @validator("DATABASE_URL", pre=True, always=True)
    def assemble_db_connection(cls, v: Optional[str], values: dict[str, Any]) -> str:
        if isinstance(v, str): return v
        user, password, server, db = values.get("POSTGRES_USER"), values.get("POSTGRES_PASSWORD"), values.get("POSTGRES_SERVER"), values.get("POSTGRES_DB")
        if all([user, password, server, db]):
            return str(PostgresDsn.build(scheme="postgresql", username=user, password=password, host=server, path=f"{db}"))
        raise ValueError("Missing PostgreSQL connection details and DATABASE_URL not set.")

    # --- Vector DB ---
    VECTOR_STORE_PATH: str = "./data/vector_store"
    CHROMA_COLLECTION_NAME: str = "knowledge_base"

    # --- Redis / Celery ---
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None

    @validator("CELERY_BROKER_URL", pre=True, always=True)
    def assemble_celery_broker(cls, v: Optional[str], values: dict[str, Any]) -> str:
        if isinstance(v, str): return v
        host, port = values.get('REDIS_HOST', 'redis'), values.get('REDIS_PORT', 6379)
        return f"redis://{host}:{port}/0"

    @validator("CELERY_RESULT_BACKEND", pre=True, always=True)
    def assemble_celery_backend(cls, v: Optional[str], values: dict[str, Any]) -> str:
        if isinstance(v, str): return v
        host, port = values.get('REDIS_HOST', 'redis'), values.get('REDIS_PORT', 6379)
        return f"redis://{host}:{port}/1"

    # --- Security ---
    SECRET_KEY: str  # Remove default - must be set in environment
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    # --- Google Cloud / AI ---
    GCP_PROJECT_ID: Optional[str] = None
    # GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    DOCUMENT_AI_PROCESSOR_ID: Optional[str] = None
    DOCUMENT_AI_LOCATION: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None # Keep optional if using Google primarily
    EMBEDDING_MODEL: str = "text-embedding-004"
    LLM_MODEL: str = "gemini-1.5-flash"

    # --- Processing ---
    CHUNK_SIZE_TOKENS: int = 500
    CHUNK_OVERLAP_TOKENS: int = 50
    TOP_K_RESULTS: int = 3

    # --- CORS ---
    # Change type hint to List[str] for compatibility with CORSMiddleware
    BACKEND_CORS_ORIGINS: str = "" # Default to empty list

    GCS_BUCKET_NAME: Optional[str] = None
    @validator("GCS_BUCKET_NAME", pre=True, always=True)
    def check_gcs_bucket_name(cls, v: Optional[str]) -> Optional[str]:
         if not v:
              logging.warning("GCS_BUCKET_NAME not set. GCS operations will fail.")
         return v

    # Pydantic V2 model_config
    model_config = {
        "case_sensitive": True,
        "env_file": ".env",
        "env_file_encoding": 'utf-8'
    }

settings = Settings()

# Log loaded origins for debugging (AFTER settings object is created)
log.info(f"Raw CORS Origins Loaded: {settings.BACKEND_CORS_ORIGINS}")