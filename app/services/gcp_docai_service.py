# app/services/gcp_docai_service.py
import logging
from typing import Optional
from google.api_core.client_options import ClientOptions
from google.cloud import documentai # Import the Document AI client library

# Import settings to get project ID, location, processor ID
from app.core.config import settings

log = logging.getLogger(__name__)

# Initialize Document AI Client
docai_client = None
processor_name = None
if settings.GCP_PROJECT_ID and settings.DOCUMENT_AI_LOCATION and settings.DOCUMENT_AI_PROCESSOR_ID:
    try:
        # You need to specify the regional endpoint
        # e.g., us-documentai.googleapis.com or eu-documentai.googleapis.com
        opts = ClientOptions(api_endpoint=f"{settings.DOCUMENT_AI_LOCATION}-documentai.googleapis.com")
        docai_client = documentai.DocumentProcessorServiceClient(client_options=opts)

        # The full resource name of the processor, e.g.:
        # projects/project-id/locations/location/processors/processor-id
        processor_name = docai_client.processor_path(
            settings.GCP_PROJECT_ID, settings.DOCUMENT_AI_LOCATION, settings.DOCUMENT_AI_PROCESSOR_ID
        )
        log.info(f"Document AI client initialized. Processor: {processor_name}")
    except ImportError:
         log.error("Failed to import google.cloud.documentai. Is 'google-cloud-documentai' package installed?")
         docai_client = None
    except Exception as e:
        log.error(f"Failed to initialize Document AI client: {e}", exc_info=True)
        docai_client = None
else:
    log.warning("Document AI settings (Project ID, Location, Processor ID) not fully configured. Document AI processing disabled.")


def process_document_online(file_content: bytes, mime_type: str) -> Optional[documentai.Document]:
    """
    Processes a document using the Document AI synchronous API (Online Processing).

    Args:
        file_content: The raw byte content of the file.
        mime_type: The MIME type of the file (e.g., "application/pdf").

    Returns:
        A Document AI Document object containing the parsed results, or None on failure.
    """
    if not docai_client or not processor_name:
        log.error("Document AI client or processor not initialized. Cannot process document.")
        # Raise an error to be caught by the Celery task
        raise ConnectionError("Document AI service is not configured or available.")

    try:
        log.info(f"Processing document online using processor: {settings.DOCUMENT_AI_PROCESSOR_ID}")
        # Construct the RawDocument object
        raw_document = documentai.RawDocument(content=file_content, mime_type=mime_type)

        # Configure the process request
        # Specify ProcessOptions to skip human review for online processing
        # You can add more options here if needed (e.g., specific pages)
        request = documentai.ProcessRequest(
            name=processor_name,
            raw_document=raw_document,
            skip_human_review=True # Required for online processing
        )

        # Call the process_document method
        result = docai_client.process_document(request=request)

        log.info("Document processed successfully by Document AI (online).")
        return result.document # Return the parsed Document object

    except Exception as e:
        log.error(f"Document AI online processing failed: {e}", exc_info=True)
        # Re-raise the exception to be caught by the Celery task retry logic
        raise

# --- Add batch processing function later ---
# def process_document_batch(gcs_input_uri: str, gcs_output_uri: str, mime_type: str) -> Optional[str]: ...