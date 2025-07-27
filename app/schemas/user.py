# app/schemas/user.py
from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
import uuid
from datetime import datetime

# Shared properties
class UserBase(BaseModel):
    email: EmailStr

# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str

# Properties stored in DB but not always returned (password)
class UserInDBBase(UserBase):
    id: uuid.UUID
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
    # Pydantic V2 uses model_config, V1 uses class Config
    model_config = ConfigDict(from_attributes=True)
    # class Config:
    #     orm_mode = True

# Properties to return to client
class UserRead(UserInDBBase):
    pass # Inherits all needed fields from UserInDBBase

# Properties stored in DB
class UserInDB(UserInDBBase):
    hashed_password: str