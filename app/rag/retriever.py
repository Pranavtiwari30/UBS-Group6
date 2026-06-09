"""
Retriever — thin wrapper around the FAISS vector store.

Provides a clean interface for the Compliance Agent to call:
    relevant_docs = get_relevant_docs(query_text, k=4)

Singleton pattern: the vector store is loaded once per process lifetime.
"""

from typing import List
from langchain_core.documents import Document
from app.rag.vector_store import load_vector_store
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level singleton — loaded once, reused across all requests
# ---------------------------------------------------------------------------
_vector_store = None


def _get_store():
    """Lazy-initialise the vector store on first call."""
    global _vector_store
    if _vector_store is None:
        logger.info("Initialising compliance document retriever…")
        _vector_store = load_vector_store()
    return _vector_store


def get_relevant_docs(query: str, k: int = 4) -> List[Document]:
    """
    Retrieve the top-k most relevant compliance document chunks for a query.

    Args:
        query: Natural language description of the transaction concern.
        k:     Number of document chunks to return.

    Returns:
        List of LangChain Document objects with .page_content and .metadata.
    """
    store = _get_store()
    docs = store.similarity_search(query, k=k)
    logger.debug(f"Retrieved {len(docs)} chunks for query: '{query[:80]}…'")
    return docs


def get_relevant_docs_with_scores(query: str, k: int = 4):
    """
    Same as get_relevant_docs but also returns similarity scores.
    Useful for debugging retrieval quality in the demo.

    Returns:
        List of (Document, score) tuples — lower score = more similar.
    """
    store = _get_store()
    results = store.similarity_search_with_score(query, k=k)
    logger.debug(f"Retrieved {len(results)} scored chunks for query: '{query[:80]}…'")
    return results


def format_docs_for_prompt(docs: List[Document]) -> str:
    """
    Join retrieved document chunks into a single context string
    suitable for inclusion in an LLM prompt.
    """
    sections = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "compliance_doc")
        source_name = source.split("\\")[-1].split("/")[-1]  # basename only
        sections.append(f"[Document {i} — {source_name}]\n{doc.page_content.strip()}")
    return "\n\n---\n\n".join(sections)
