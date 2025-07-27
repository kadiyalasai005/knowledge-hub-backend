# app/services/gcs_storage_service.py
import logging
from google.cloud import storage
from google.cloud.exceptions import NotFound, GoogleCloudError
from fastapi import UploadFile, HTTPException, status
from datetime import timedelta, timezone, datetime
import uuid
import os
from pathlib import Path
from typing import Optional # <-- ADDED Optional import

# Import settings to get project ID and bucket name
from app.core.config import settings

log = logging.getLogger(__name__)

# --- Initialize GCS Client ---
storage_client = None
bucket_name = settings.GCS_BUCKET_NAME
if bucket_name and settings.GCP_PROJECT_ID:
    try:
        # --- ADD LOGGING BEFORE CLIENT INIT ---
        log.info(f"Attempting to initialize GCS client for Project ID: '{settings.GCP_PROJECT_ID}' and Bucket: '{bucket_name}'")
        # --- END LOGGING ---

        # --- Ensure project ID is passed ---
        storage_client = storage.Client(project=settings.GCP_PROJECT_ID)
        # --- End Ensure ---

        # Optional: Check bucket existence
        # bucket = storage_client.get_bucket(bucket_name)
        log.info(f"Google Cloud Storage client initialized successfully.")

    except ImportError:
         log.error("Failed to import google.cloud.storage. Is package installed?")
         storage_client = None
    except Exception as e:
        log.error(f"Failed to initialize GCS client for bucket '{bucket_name}': {e}", exc_info=True)
        storage_client = None

elif not settings.GCP_PROJECT_ID:
    log.error("GCP_PROJECT_ID not configured. GCS Storage service disabled.")
    storage_client = None
elif not bucket_name:
     log.error("GCS_BUCKET_NAME not configured. GCS Storage service disabled.")
     storage_client = None
# --- End Initialization ---

def _get_gcs_blob_name(user_id: uuid.UUID, doc_id: uuid.UUID, filename: str) -> str:
    """Generates a structured blob name for GCS."""
    safe_filename = Path(filename).name
    safe_filename = "".join(c if c.isalnum() or c in ['.', '_', '-'] else '_' for c in safe_filename) # Allow hyphens too
    max_len = 100
    if len(safe_filename) > max_len:
         name, ext = os.path.splitext(safe_filename) # Need to import os here
         safe_filename = name[:max_len-len(ext)-1] + ext
    return f"users/{str(user_id)}/docs/{str(doc_id)}/{safe_filename}"

async def upload_file_to_gcs(file: UploadFile, user_id: uuid.UUID, doc_id: uuid.UUID) -> str:
    """Uploads file content to GCS and returns the GCS URI (gs://...)."""
    if not storage_client or not bucket_name:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GCS storage service not available.")

    blob_name = _get_gcs_blob_name(user_id, doc_id, file.filename)
    log.info(f"Uploading file to GCS. Bucket: '{bucket_name}', Blob: '{blob_name}'")
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        await file.seek(0)
        # Upload using stream (recommended for Cloud Functions/Run compatibility)
        blob.upload_from_string(await file.read(), content_type=file.content_type)
        # Or keep upload_from_file if it works reliably in your env
        # blob.upload_from_file(file.file, content_type=file.content_type)
        gcs_uri = f"gs://{bucket_name}/{blob_name}"
        log.info(f"File successfully uploaded to: {gcs_uri}")
        return gcs_uri
    except GoogleCloudError as e:
        log.error(f"GCS Error uploading file to blob '{blob_name}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Cloud storage upload error.")
    except Exception as e:
        log.error(f"Unexpected error uploading file to GCS blob '{blob_name}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error during cloud storage upload.")
    finally:
         await file.close()

async def delete_file_from_gcs(storage_uri: Optional[str]):
    """Deletes a file from GCS given its gs:// URI."""
    if not storage_client or not bucket_name:
        log.error("GCS storage service not available for deletion.")
        return

    if not storage_uri or not storage_uri.startswith(f"gs://{bucket_name}/"):
        log.warning(f"Invalid or missing storage URI, skipping GCS deletion: {storage_uri}")
        return

    try:
        blob_name = storage_uri[len(f"gs://{bucket_name}/"):]
        log.warning(f"Attempting to delete GCS blob: Bucket='{bucket_name}', Blob='{blob_name}'")
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete() # Returns None, raises NotFound on error if blob doesn't exist
        log.info(f"Successfully deleted GCS blob: {blob_name}")
    except NotFound:
         log.warning(f"Blob not found in GCS during delete attempt (already deleted?): {blob_name}")
    except GoogleCloudError as e:
         log.error(f"GCS error deleting blob {blob_name}: {e}", exc_info=True)
    except Exception as e:
        log.error(f"Unexpected error deleting blob {blob_name} from GCS: {e}", exc_info=True)


async def generate_signed_view_url(storage_uri: Optional[str], expiration_minutes: int = 15) -> Optional[str]:
    """Generates a temporary signed URL for viewing/downloading a GCS file."""
    if not storage_client or not bucket_name:
        log.error("GCS storage service not available for generating signed URL.")
        return None # Or raise HTTPException(503)? Let's return None

    if not storage_uri or not storage_uri.startswith(f"gs://{bucket_name}/"):
        log.warning(f"Invalid GCS URI for signed URL: {storage_uri}")
        return None

    try:
        blob_name = storage_uri[len(f"gs://{bucket_name}/"):]
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        # Check existence explicitly before generating URL
        if not blob.exists():
             log.warning(f"Blob not found when generating signed URL: {blob_name}")
             return None

        # Generate signed URL (requires service account with IAM Signer role potentially)
        expiration_time = datetime.now(timezone.utc) + timedelta(minutes=expiration_minutes)
        url = blob.generate_signed_url(
            version="v4",
            expiration=expiration_time, # Use datetime object
            method="GET",
        )
        log.info(f"Generated signed URL for blob: {blob_name}")
        return url
    except NotFound: # Catch just in case exists() check has race condition
         log.warning(f"Blob not found when generating signed URL (NotFound Exception): {blob_name}")
         return None
    except GoogleCloudError as e:
         log.error(f"GCS error generating signed URL for blob {blob_name}: {e}", exc_info=True)
         # Often permission errors - Service Account Token Creator role needed
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not generate view URL due to Cloud Storage error.")
    except Exception as e:
         log.error(f"Unexpected error generating signed URL for blob {blob_name}: {e}", exc_info=True)
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not generate view URL.")

def download_file_bytes(storage_uri: Optional[str]) -> bytes:
    """Downloads file content as bytes from a GCS URI."""
    if not storage_client or not bucket_name:
        log.error("GCS storage service not available for download.")
        raise ConnectionError("GCS storage service not configured.")

    if not storage_uri or not storage_uri.startswith(f"gs://{bucket_name}/"):
        log.error(f"Invalid GCS URI provided for download: {storage_uri}")
        raise ValueError(f"Invalid GCS URI format: {storage_uri}")

    try:
        blob_name = storage_uri[len(f"gs://{bucket_name}/"):]
        log.info(f"Attempting to download GCS blob: Bucket='{bucket_name}', Blob='{blob_name}'")
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        # Download content as bytes
        content = blob.download_as_bytes()
        log.info(f"Successfully downloaded {len(content)} bytes from GCS blob: {blob_name}")
        return content
    except NotFound:
         log.error(f"File not found in GCS during download attempt: {blob_name}")
         # Let Celery retry mechanism handle this via the raised exception
         raise FileNotFoundError(f"File not found in GCS: {storage_uri}")
    except GoogleCloudError as e:
         log.error(f"GCS error downloading blob {blob_name}: {e}", exc_info=True)
         raise ConnectionError(f"Cloud Storage download error: {e.message}") from e
    except Exception as e:
        log.error(f"Unexpected error downloading blob {blob_name} from GCS: {e}", exc_info=True)
        raise RuntimeError(f"Unexpected error during GCS download") from e
# --- END ADD ---