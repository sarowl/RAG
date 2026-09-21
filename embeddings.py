"""Shared Ollama embedding configuration for ingestion and retrieval."""

import os

from dotenv import load_dotenv
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)

load_dotenv()

EMBED_MODEL = os.getenv("EMBED_MODEL", "embeddinggemma")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_TIMEOUT = int(os.getenv("OLLAMA_EMBED_TIMEOUT", "120"))


def create_embedding_function() -> OllamaEmbeddingFunction:
    """Use the same Ollama model for document vectors and query vectors."""
    return OllamaEmbeddingFunction(
        url=OLLAMA_BASE_URL,
        model_name=EMBED_MODEL,
        timeout=OLLAMA_EMBED_TIMEOUT,
    )
