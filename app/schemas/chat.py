# app/schemas/chat.py
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid # Keep if used in other schemas maybe

class ChatRequest(BaseModel):
    query: str

# Final response model
class ChatResponse(BaseModel):
    answer: str
    # Optional: Add source information later
    # source_documents: List[str] = []
    # source_chunks: List[Dict[str, Any]] = []

# --- Debug schemas below can be removed or commented out ---
# class RetrievedChunk(BaseModel):
#     id: str
#     content: Optional[str] = None
#     metadata: Optional[Dict[str, Any]] = None
#     distance: Optional[float] = None
#
# class ChatResponseDebug(BaseModel):
#     retrieved_chunks: List[RetrievedChunk]
#     message: str = "Retrieved relevant chunks."