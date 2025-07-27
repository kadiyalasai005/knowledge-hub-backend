# tasks/document_tasks.py
import logging
import os
from pathlib import Path
import uuid
from celery.exceptions import Ignore, Reject # Import Celery exceptions
from celery import Task                 # Import Task for task instance typing
import chromadb                     # Import chromadb client library
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any, Set # Make sure all needed types are imported
import redis # Import synchronous redis client
import json # To format the message payload

# Import the Celery app instance defined in celery_app.py
# Ensure celery_app.py modifies sys.path so these imports work when worker starts
try:
    from .celery_app import celery_app
except ImportError:
    try: from celery_app import celery_app
    except ImportError: logging.critical("Could not import celery_app.", exc_info=True); celery_app = None
except Exception as e:
     logging.critical(f"CRITICAL: Unexpected error importing celery_app: {e}", exc_info=True)
     celery_app = None

# Import necessary application components
try:
    from app.db.database import SessionLocal # Get session factory
    from app.crud import crud_document
    from app.db.models.document import DocumentStatus, Document
    from app.services import gcp_docai_service, embedding_service, gcs_storage_service # Import DocAI service
    from app.core.config import settings # Import settings for ChromaDB path/name etc.
    # Import Document AI types for type hinting within helpers
    from google.cloud import documentai
except ImportError as e:
    logging.critical(f"CRITICAL: Error importing app modules in document_tasks.py: {e}. Worker might not function.", exc_info=True)
    SessionLocal = None # Prevent runtime errors below if import failed
except Exception as e:
    logging.critical(f"CRITICAL: Unexpected error during imports in document_tasks.py: {e}", exc_info=True)
    SessionLocal = None
    raise

log = logging.getLogger(__name__) # Celery automatically configures logging handlers


# --- Initialize Synchronous Redis Client for Publishing ---
redis_publisher_client = None
if settings.REDIS_HOST and settings.REDIS_PORT:
    try:
        redis_publisher_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0, # Use same DB as Celery broker or different? Usually fine.
            decode_responses=True # Ensure strings are used
        )
        redis_publisher_client.ping() # Check connection on startup
        log.info(f"Synchronous Redis client for publishing initialized (Host: {settings.REDIS_HOST}).")
    except Exception as redis_err:
        log.error(f"Failed to initialize synchronous Redis publisher client: {redis_err}", exc_info=True)
        redis_publisher_client = None # Task will log error if it tries to publish
else:
     log.warning("Redis host/port not configured for publisher, Redis publishing disabled.")


# --- HELPER FUNCTIONS for Parsing Document AI Response ---

def _get_text_from_layout(layout: Optional[documentai.Document.Page.Layout], full_text: str) -> str:
    """Safely extracts text segments from layout anchors."""
    if not layout or not layout.text_anchor or not layout.text_anchor.text_segments:
        return ""
    response = ""
    segments = layout.text_anchor.text_segments or []
    for segment in segments:
        start_index = int(segment.start_index) if segment.start_index is not None else 0
        end_index = int(segment.end_index) if segment.end_index is not None else 0
        start_index = max(0, start_index); end_index = min(len(full_text), end_index)
        if start_index < end_index: response += full_text[start_index:end_index]
    return response.strip()

def _table_to_markdown(table: documentai.Document.Page.Table, full_text: str) -> str:
    """Converts a Document AI Table object to a Markdown table string."""
    markdown_rows = []; headers = []; header_rows = table.header_rows or []; body_rows = table.body_rows or []; col_count = 0
    if header_rows:
        markdown_rows.append("| ")
        for header_row in header_rows:
            row_headers = []
            for cell in header_row.cells: cell_text = _get_text_from_layout(cell.layout, full_text).replace("\n", " ").replace("|", "\\|").strip(); row_headers.append(cell_text)
            headers.extend(row_headers)
        markdown_rows[-1] += " | ".join(headers) + " |"
        col_count = len(headers)
        if col_count > 0: markdown_rows.append("| " + " | ".join(["---"] * col_count) + " |")
    elif body_rows:
        col_count = len(body_rows[0].cells) if body_rows and body_rows[0].cells else 0
        if col_count > 0: markdown_rows.append("| " + " | ".join(["---"] * col_count) + " |")
    for body_row in body_rows:
        row_cells = []
        for cell in body_row.cells: cell_text = _get_text_from_layout(cell.layout, full_text).replace("\n", " ").replace("|", "\\|").strip(); row_cells.append(cell_text)
        while len(row_cells) < col_count: row_cells.append("")
        markdown_rows.append("| " + " | ".join(row_cells[:col_count]) + " |")
    return "\n\n" + "\n".join(markdown_rows) + "\n\n" if markdown_rows else ""

def _get_segment_indices(layout: Optional[documentai.Document.Page.Layout]) -> Set[int]:
    """Gets all character indices covered by a layout's text anchor segments."""
    indices = set()
    if not layout or not layout.text_anchor or not layout.text_anchor.text_segments: return indices
    for segment in layout.text_anchor.text_segments:
         start_index = int(segment.start_index) if segment.start_index is not None else -1
         end_index = int(segment.end_index) if segment.end_index is not None else -1
         if start_index >= 0 and end_index > start_index: indices.update(range(start_index, end_index))
    return indices

def _parse_docai_response(doc_ai_document: documentai.Document) -> str:
    """
    Parses the Document AI response, extracts text, formats tables/forms,
    attempts to avoid duplication, and combines into an enhanced text string.
    """
    log.info("Parsing detailed Document AI response...")
    if not doc_ai_document or not doc_ai_document.text:
        log.warning("Received empty or invalid Document AI object for parsing.")
        return ""

    full_text = doc_ai_document.text
    enhanced_page_parts = []
    processed_text_indices = set() # Track indices covered by tables/forms

    for page_num, page in enumerate(doc_ai_document.pages):
        page_number = page_num + 1
        page_output_parts = []
        page_processed_indices = set()
        log.debug(f"Parsing Page {page_number}...")

        # Process Tables
        page_tables_markdown = []
        if page.tables:
            log.debug(f"Page {page_number}: Found {len(page.tables)} tables.")
            for table_num, table in enumerate(page.tables):
                md_table = _table_to_markdown(table, full_text)
                if md_table:
                     page_tables_markdown.append(f"\n--- Table {table_num + 1} (Page {page_number}) ---\n{md_table}--- End Table {table_num + 1} ---\n")
                     for row_type in [table.header_rows, table.body_rows]:
                         for row in row_type:
                             for cell in row.cells: page_processed_indices.update(_get_segment_indices(cell.layout))

        # Process Form Fields
        page_form_fields_text = []
        if page.form_fields:
             log.debug(f"Page {page_number}: Found {len(page.form_fields)} form fields.")
             key_value_pairs = []
             for field in page.form_fields:
                 key_text = _get_text_from_layout(field.field_name, full_text).replace("\n", " ").strip()
                 value_text = _get_text_from_layout(field.field_value, full_text).replace("\n", " ").strip()
                 if key_text: key_value_pairs.append(f"{key_text}: {value_text}")
                 page_processed_indices.update(_get_segment_indices(field.field_name))
                 page_processed_indices.update(_get_segment_indices(field.field_value))
             if key_value_pairs:
                 page_form_fields_text.append(f"\n--- Form Fields (Page {page_number}) ---\n")
                 page_form_fields_text.append("\n".join(key_value_pairs))
                 page_form_fields_text.append("\n--- End Form Fields ---\n")

        # Process Remaining Text Blocks (Paragraphs)
        page_plain_text = []
        blocks_to_process = page.paragraphs
        if blocks_to_process:
            log.debug(f"Page {page_number}: Processing {len(blocks_to_process)} paragraphs.")
            for block in blocks_to_process:
                 block_indices = _get_segment_indices(block.layout)
                 is_processed = False
                 if block_indices:
                      overlap = page_processed_indices.intersection(block_indices)
                      if len(overlap) / len(block_indices) >= 0.3: is_processed = True # Check overlap > 30%
                 if not is_processed:
                     block_text = _get_text_from_layout(block.layout, full_text).strip()
                     if block_text: page_plain_text.append(block_text)

        # Assemble Page Content
        has_content = page_plain_text or page_form_fields_text or page_tables_markdown
        if has_content:
            enhanced_page_parts.append(f"\n\n========== PAGE {page_number} ==========\n")
            if page_plain_text:
                enhanced_page_parts.append("\n--- Text Content ---\n")
                enhanced_page_parts.append("\n\n".join(filter(None, page_plain_text)))
                enhanced_page_parts.append("\n--- End Text Content ---\n")
            enhanced_page_parts.extend(page_form_fields_text)
            enhanced_page_parts.extend(page_tables_markdown)
        # Update global processed indices
        processed_text_indices.update(page_processed_indices)


    log.info("Finished assembling enhanced text from Document AI response.")
    final_text = "".join(enhanced_page_parts).strip()
    if not final_text and full_text: log.warning("Parsing yielded empty text, falling back to raw text."); return full_text.strip()
    elif not final_text: log.warning("Parsing yielded empty text, original was also empty."); return ""
    else: log.info(f"Final enhanced text length: {len(final_text)}"); return final_text

# --- END HELPER FUNCTIONS ---


# --- Celery Task Definition ---
@celery_app.task(
    name="tasks.process_document",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    reject_on_worker_lost=True,
    acks_late=True
)
def process_document(self: Task, doc_id_str: str, user_id: str, file_path: str):
    """
    Celery task using Google Document AI for extraction, including table/form parsing,
    and publishing status updates to Redis Pub/Sub.
    """
    task_id = self.request.id
    log.info(f"[TASK RECEIVED:{task_id}] Processing doc_id: {doc_id_str} for user: {user_id}")
    log.debug(f"Task ID: {task_id}, File path: {file_path}")

    if SessionLocal is None:
        log.critical(f"[TASK FAILED:{task_id}] DB SessionLocal not available.")
        raise Reject("DB SessionLocal not initialized", requeue=False)

    db: Optional[Session] = None
    db_doc: Optional[Document] = None
    final_status_data: Optional[Dict[str, Any]] = None # Variable to hold status for finally block

    try:
        db = SessionLocal()
        if db is None:
            log.error(f"[TASK FAILED:{task_id}] Failed to get database session.")
            raise Reject("Could not establish database session.", requeue=False)

        # --- Fetch Document Record & Check Status ---
        try: doc_id_uuid = uuid.UUID(doc_id_str)
        except ValueError: raise Reject(f"Invalid UUID: {doc_id_str}", requeue=False)

        # Convert user_id string arg to UUID for DB operations
        try: user_id_uuid = uuid.UUID(user_id)
        except ValueError: raise Reject(f"Invalid User UUID: {user_id}", requeue=False)

        db_doc = crud_document.get_document(db=db, doc_id=doc_id_uuid, user_id=user_id_uuid)
        if not db_doc: raise Reject(f"Document {doc_id_str} not found.", requeue=False)
        if db_doc.status in [DocumentStatus.READY, DocumentStatus.FAILED]: raise Ignore()

        # --- Update Status to PROCESSING ---
        log.info(f"[TASK:{task_id}] Updating status to PROCESSING...")
        db_doc = crud_document.update_document_status(db=db, db_doc=db_doc, status=DocumentStatus.PROCESSING)

        # --- Processing Pipeline ---
        # 1. Check File Existence (Done implicitly by download)
        # 2. Read File Content (Download from GCS)
        log.info(f"[TASK:{task_id}] Downloading file content from GCS URI: {file_path}")
        # This service function will raise errors if download fails (e.g., NotFound)
        file_content = gcs_storage_service.download_file_bytes(file_path) # Call the new service function
        stored_mime_type = db_doc.mime_type # Get MIME type stored in DB
        if not stored_mime_type:
             raise ValueError("Missing MIME type in database record.")
        log.info(f"[TASK:{task_id}] Successfully downloaded {len(file_content)} bytes from GCS.")

        # 3. Call Google Document AI (Use downloaded bytes)
        log.info(f"[TASK:{task_id}] Calling Google Document AI for doc ID {doc_id_str}")
        doc_ai_result_document = gcp_docai_service.process_document_online(
             file_content=file_content, # Pass downloaded bytes
             mime_type=stored_mime_type
        ) # Errors handled/raised by service

        # 4. Parse & Format Document AI Result
        log.info(f"[TASK:{task_id}] Parsing/Formatting Document AI output...")
        if not doc_ai_result_document: raise ValueError("Document AI returned no result.")
        enhanced_text = _parse_docai_response(doc_ai_result_document)

        if not enhanced_text:
            log.warning(f"[TASK FAILED:{task_id}] No text after parsing. Marking FAILED.")
            db_doc = crud_document.update_document_status(db=db, db_doc=db_doc, status=DocumentStatus.FAILED, detail="No text content after AI parsing.")
            final_status_data = {"doc_id": doc_id_str, "status": "FAILED", "detail": "No text content after AI parsing."}
            return final_status_data

        # 5. Chunk Enhanced Text
        log.info(f"[TASK:{task_id}] Chunking enhanced text ({len(enhanced_text)} chars)...")
        chunks = embedding_service.split_text_into_chunks(enhanced_text)
        if not chunks:
             log.warning(f"[TASK FAILED:{task_id}] No chunks generated. Marking FAILED.")
             db_doc = crud_document.update_document_status(db=db, db_doc=db_doc, status=DocumentStatus.FAILED, detail="No indexable chunks from enhanced text.")
             final_status_data = {"doc_id": doc_id_str, "status": "FAILED", "detail": "No indexable chunks from enhanced text."}
             return final_status_data

        # 6. Get Embeddings
        log.info(f"[TASK:{task_id}] Generating embeddings for {len(chunks)} chunks...")
        embeddings = embedding_service.get_google_embeddings(chunks)
        if len(embeddings) != len(chunks): raise RuntimeError("Embedding generation failed.")

        # 7. Prepare for Indexing (Use string user_id for metadata)
        metadatas = [{"doc_id": doc_id_str, "user_id": user_id, "original_filename": db_doc.original_filename, "chunk_index": i} for i in range(len(chunks))]
        chunk_ids = [f"{doc_id_str}_chunk_{i}" for i in range(len(chunks))]

        # 8. Index in Vector DB
        log.info(f"[TASK:{task_id}] Indexing {len(chunks)} chunks in ChromaDB...")
        try:
            local_chroma_client = chromadb.PersistentClient(path=settings.VECTOR_STORE_PATH)
            local_vector_collection = local_chroma_client.get_or_create_collection(name=settings.CHROMA_COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
            local_vector_collection.add(embeddings=embeddings, documents=chunks, metadatas=metadatas, ids=chunk_ids)
            log.info(f"[TASK:{task_id}] Successfully added {len(chunks)} chunks to ChromaDB.")
        except Exception as chroma_e: raise RuntimeError("Failed to index document chunks.") from chroma_e

        # 9. Final Status Update -> READY
        log.info(f"[TASK:{task_id}] Updating status to READY...")
        db_doc = crud_document.update_document_status(db=db, db_doc=db_doc, status=DocumentStatus.READY)
        log.info(f"[TASK SUCCEEDED:{task_id}] Successfully processed doc ID {doc_id_str}")
        # Set final status data for publishing on success
        final_status_data = {"doc_id": doc_id_str, "status": "READY", "detail": None}
        return final_status_data

    except (Ignore, Reject) as celery_exc:
        log.warning(f"[TASK:{task_id}] Task ignored or rejected for doc ID {doc_id_str}: {celery_exc}")
        final_status_data = None # Do not publish
        raise

    except Exception as e:
        log.error(f"[TASK FAILED:{task_id}] Unhandled exception for doc ID {doc_id_str}: {e}", exc_info=True)
        error_detail = f"Processing failed: {str(e)[:500]}"
        # Set final status data for publishing on failure
        final_status_data = {"doc_id": doc_id_str, "status": "FAILED", "detail": error_detail}
        if db and db_doc:
            try:
                db.refresh(db_doc)
                if db_doc.status != DocumentStatus.FAILED:
                     crud_document.update_document_status(db=db, db_doc=db_doc, status=DocumentStatus.FAILED, detail=error_detail)
                     log.info(f"Set status to FAILED for doc ID {doc_id_str} after error in task.")
            except Exception as update_e:
                log.error(f"Nested Error: Failed to update status to FAILED: {update_e}", exc_info=True)
        # Raise the original exception for Celery's retry mechanism
        raise e

    finally:
        # --- Publish Status Update to Redis (if status was determined) ---
        log.debug(f"[TASK:{task_id}] Entering finally block. Attempting to publish: {final_status_data}")
        if final_status_data and redis_publisher_client:
             channel = f"doc_status:{user_id}" # Use user_id received by task (string)
             message = json.dumps(final_status_data)
             log.info(f"[TASK:{task_id}] Preparing to publish to channel='{channel}'")
             log.info(f"[TASK:{task_id}] Message payload (JSON): {message}")
             try:
                  log.info(f"[TASK:{task_id}] Publishing status update to Redis channel '{channel}'...")
                  clients_received = redis_publisher_client.publish(channel, message)
                  log.info(f"[TASK:{task_id}] Redis publish command sent to {clients_received} clients.")
             except Exception as pub_e:
                  log.error(f"[TASK:{task_id}] Failed to publish status update to Redis for doc {doc_id_str}: {pub_e}", exc_info=True)
        elif not final_status_data:
             log.warning(f"[TASK:{task_id}] No final status data determined (task ignored/rejected?), skipping Redis publish.")
        elif not redis_publisher_client:
             log.error(f"[TASK:{task_id}] Redis publisher client not available, skipping publish.")

        # --- Ensure DB Session is Closed ---
        if db:
            try:
                db.close()
                log.debug(f"[TASK:{task_id}] Database session closed.")
            except Exception as close_e:
                 log.error(f"Error closing DB session for task {task_id}: {close_e}", exc_info=True)