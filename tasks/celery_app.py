# tasks/celery_app.py
from celery import Celery
import os
import sys
from pathlib import Path
import logging

# --- Path Setup ---
# Add project root to sys.path so Celery can find 'app' modules
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
    logging.info(f"Added project root to sys.path for Celery: {project_root}")

# --- Import Settings ---
# Should now work because project root is in path
try:
    from app.core.config import settings
    logging.info("Successfully imported settings for Celery.")
except ImportError as e:
    logging.error(f"Error importing settings in celery_app.py: {e}. Check sys.path.", exc_info=True)
    # Critical error, Celery cannot configure without settings
    raise RuntimeError("Could not load settings for Celery configuration.") from e
except Exception as e:
    logging.error(f"Unexpected error loading settings in celery_app.py: {e}", exc_info=True)
    raise RuntimeError("Could not load settings for Celery configuration.") from e


# --- Define Celery Application ---
celery_app = Celery(
    "knowledge_hub_tasks", # Application name
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=['tasks.document_tasks'] # Module(s) where tasks are defined
)

# --- Celery Configuration (Optional Updates) ---
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    broker_connection_retry_on_startup=True, # Recommended for robustness
    # Optional: Task tracking settings
    # task_track_started=True,
    # task_send_sent_event=True,
)

# Optional: Print loaded config for debugging worker startup
# print(f"Celery App Configured: Broker={celery_app.conf.broker_url}, Backend={celery_app.conf.result_backend}")

if __name__ == '__main__':
    # This is for running celery directly using "python -m tasks.celery_app ..."
    # Usually run via "celery -A tasks.celery_app.celery_app worker ..." command
    celery_app.start()