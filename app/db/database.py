# app/db/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
import logging

log = logging.getLogger(__name__)

try:
    # The pool_pre_ping checks connections for validity before use
    engine = create_engine(str(settings.DATABASE_URL), pool_pre_ping=True) # Cast DSN to string
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    log.info("Database engine and session created successfully.")
except Exception as e:
    log.error(f"Failed to create database engine or session: {e}", exc_info=True)
    # Handle error appropriately - maybe exit or raise?
    engine = None
    SessionLocal = None

# Dependency for FastAPI (to get a DB session in route handlers)
def get_db():
    if SessionLocal is None:
        raise RuntimeError("Database session not initialized.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()