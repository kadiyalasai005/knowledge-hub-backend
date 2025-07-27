# app/api/v1/endpoints/status_sse.py
import asyncio
import logging
import json
import uuid
from fastapi import APIRouter, Depends, Request, HTTPException, status
from sse_starlette.sse import EventSourceResponse, ServerSentEvent # For sending SSE events
import redis.asyncio as redis # Use the official redis library's async features
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError # Import specific redis errors
from contextlib import suppress # For cleaner exception handling on close

# Import settings for Redis connection details
from app.core.config import settings
from app.api import deps # Import authentication dependency
from app.db.models import user as user_models

log = logging.getLogger(__name__)
router = APIRouter()

async def redis_event_stream(user_id: str, request: Request):
    """
    Async generator function that connects to Redis Pub/Sub, listens for messages
    on a user-specific channel, and yields Server-Sent Events.
    """
    redis_client = None
    pubsub = None
    # Define the channel name based on user ID (matches publisher in Celery task)
    channel_name = f"doc_status:{user_id}"
    log.info(f"SSE stream opening for user '{user_id}' on channel '{channel_name}'")
    is_subscribed = False # Track subscription status for cleanup

    try:
        # Create async Redis client connection using details from settings
        log.debug(f"Attempting to connect to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT} for SSE...")
        redis_client = await redis.from_url(
             f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0", # Use DB 0 (or match publisher)
             encoding="utf-8",
             decode_responses=True # Important for getting string data
        )
        await redis_client.ping() # Verify connection asynchronously
        log.info(f"Async Redis client connected successfully for SSE channel '{channel_name}'.")

        # Set up Pub/Sub listener
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel_name)
        is_subscribed = True
        log.info(f"SSE stream subscribed to Redis channel '{channel_name}'")

        # Send an initial confirmation event to the client (optional)
        yield ServerSentEvent(event="connected", data=json.dumps({"message": "Status stream connected"}))

        # Main loop to listen for messages
        while True:
            # 1. Check if client disconnected first
            log.debug(f"SSE loop: Checking client connection for '{channel_name}'")
            if await request.is_disconnected():
                log.info(f"SSE client disconnected for user '{user_id}'. Breaking SSE loop.")
                break # Exit the loop if client is gone

            # 2. Wait for a message from Redis Pub/Sub
            log.debug(f"SSE loop: Waiting for message on '{channel_name}' (timeout=10s)...")
            message = None # Reset message
            try:
                # Use get_message with a timeout to prevent blocking indefinitely
                # and allow checking for client disconnect periodically.
                # Returns None if timeout occurs.
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=10.0)
                log.debug(f"SSE loop: pubsub.get_message returned: {message}") # Log raw message or None

            # Handle specific potential errors during get_message
            except asyncio.TimeoutError:
                 log.debug(f"SSE loop: asyncio.TimeoutError encountered on get_message for '{channel_name}'.")
                 message = None # Treat as timeout
            except RedisConnectionError as conn_err:
                 log.error(f"SSE loop: Redis connection error during get_message for user '{user_id}': {conn_err}", exc_info=False) # Log less verbosely
                 # Try to send error to client and break
                 try: yield ServerSentEvent(event="error", data=json.dumps({"message": "Stream connection to status update lost."}))
                 except: pass
                 await asyncio.sleep(1) # Short delay before breaking
                 break
            except Exception as listen_err:
                 log.error(f"SSE loop: Unexpected error during pubsub.get_message for user '{user_id}': {listen_err}", exc_info=True)
                 # Send error and break on unknown errors
                 try: yield ServerSentEvent(event="error", data=json.dumps({"message": "Error processing status updates."}))
                 except: pass
                 await asyncio.sleep(1)
                 break

            # 3. Process the received message (if any)
            if message and message.get("type") == "message":
                message_data = message.get("data") # Data should be a JSON string
                log.info(f"SSE loop: Received valid 'message' type on '{channel_name}'. Data: {message_data}. Yielding 'status_update' event.")
                try:
                    # Yield the event to the connected client
                    # Ensure data is a string. JSON stringify already done by publisher.
                    yield ServerSentEvent(event="status_update", data=str(message_data))
                    log.debug(f"SSE loop: Yielded 'status_update' event successfully.")
                except Exception as yield_err:
                     # This usually means the client disconnected while we tried to yield
                     log.warning(f"SSE loop: Error yielding event (client likely disconnected): {yield_err}", exc_info=False)
                     break # Exit loop if we can't send to client

            elif message is None:
                # Timeout occurred on get_message - send a keep-alive comment/event
                log.debug(f"SSE loop: Timeout on '{channel_name}', sending SSE ping comment.")
                try:
                     # Sending a comment `yield ": keepalive\n\n"` is also valid SSE
                     yield ServerSentEvent(event="ping", data="keepalive", comment="keepalive")
                except Exception as yield_err:
                     log.warning(f"SSE loop: Error yielding ping (client likely disconnected): {yield_err}", exc_info=False)
                     break
            # else: Ignore other message types ('subscribe', 'unsubscribe', etc.)

    except RedisConnectionError as conn_err:
         # Error during initial connection/ping/subscribe
         log.error(f"Initial Redis connection/subscription failed for SSE stream (User: {user_id}): {conn_err}", exc_info=True)
         with suppress(Exception): # Avoid raising error while yielding error
             yield ServerSentEvent(event="error", data=json.dumps({"message": "Could not connect to status update service."}))
    except Exception as e:
        # Catch any other unexpected errors during setup or the loop
        log.error(f"Unhandled SSE stream error for user '{user_id}': {e}", exc_info=True)
        with suppress(Exception):
             yield ServerSentEvent(event="error", data=json.dumps({"message": "Stream error occurred."}))
    finally:
        # --- Cleanup ---
        log.info(f"SSE stream closing for user '{user_id}', channel '{channel_name}'")
        if pubsub and is_subscribed:
            try:
                await pubsub.unsubscribe(channel_name)
                log.debug(f"Unsubscribed from Redis channel: {channel_name}")
            except Exception as unsub_e:
                log.error(f"Error unsubscribing from {channel_name}: {unsub_e}")
        if pubsub:
             try:
                 await pubsub.close()
                 log.debug("Closed Redis pubsub client.")
             except Exception as psclose_e: log.error(f"Error closing pubsub: {psclose_e}")
        if redis_client:
            try:
                await redis_client.close() # Close the main connection
                await redis_client.connection_pool.disconnect() # Ensure pool disconnects
                log.debug("Closed Redis async client connection.")
            except Exception as close_e:
                log.error(f"Error closing Redis async client: {close_e}")


# --- API Endpoint Definition ---
@router.get(
    "/stream",
    summary="Stream Document Status Updates",
    description="Establishes a Server-Sent Events connection to receive real-time document processing status updates for the current user.",
    responses={
        200: {"description": "Event stream successfully established.", "content": {"text/event-stream": {}}},
        500: {"description": "Internal server error establishing stream."},
        503: {"description": "Status update service unavailable (e.g., Redis connection failed)."}
    }
)
async def status_stream(
    request: Request, # Inject FastAPI Request object to check disconnect status
    current_user: user_models.User = Depends(deps.get_current_user) # Use real authenticated user
):
    """
    Endpoint that initiates the Server-Sent Event stream for status updates.
    """
    # Use the authenticated user's ID
    user_id = str(current_user.id)

    # Return the EventSourceResponse, passing the async generator function
    return EventSourceResponse(redis_event_stream(user_id=user_id, request=request))