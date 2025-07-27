# app/schemas/token.py
from pydantic import BaseModel
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    # 'sub' (subject) is standard claim for user identifier
    sub: Optional[str] = None