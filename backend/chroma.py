"""
Shared ChromaDB client singleton.
Both agents.py and processor.py import from here so there is exactly ONE
PersistentClient instance per process, with consistent settings.
This prevents the 'An instance of Chroma already exists with different settings'
crash on uvicorn --reload.
"""
import os
from typing import Optional
import chromadb
from chromadb.config import Settings

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")

_client: Optional[chromadb.PersistentClient] = None


def get_chroma_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client
