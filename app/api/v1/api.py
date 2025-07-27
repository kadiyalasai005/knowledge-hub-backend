# app/api/v1/api.py
from fastapi import APIRouter
from .endpoints import documents, chat, status_sse, auth # <-- Import auth

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"]) # <-- Include auth router
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(status_sse.router, prefix="/status", tags=["Status Updates"])