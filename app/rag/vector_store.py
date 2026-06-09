"""
Vector Store — builds and persists a FAISS index from compliance documents.

Called ONCE at startup (or manually) to index all .txt files in
app/rag/compliance_docs/.

The index is saved to disk so repeated restarts don't re-embed documents.

Dependencies:
    pip install langchain langchain-community langchain-openai faiss-cpu openai
"""

from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from app.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DOCS_DIR = Path(__file__).parent / "compliance_docs"
INDEX_DIR = Path(__file__).parent / "faiss_index"


def _load_documents():
    """Load all .txt files from the compliance_docs directory."""
    docs = []
    for txt_file in sorted(DOCS_DIR.glob("*.txt")):
        logger.info(f"Loading compliance doc: {txt_file.name}")
        loader = TextLoader(str(txt_file), encoding="utf-8")
        docs.extend(loader.load())
    if not docs:
        raise FileNotFoundError(f"No .txt files found in {DOCS_DIR}")
    logger.info(f"Loaded {len(docs)} document(s) from compliance_docs/")
    return docs


def _split_documents(docs):
    """
    Split documents into overlapping chunks for better retrieval.
    Smaller chunks → more precise retrieval; overlap preserves context.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,       # ~200 tokens per chunk
        chunk_overlap=100,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(docs)
    logger.info(f"Split into {len(chunks)} chunks for embedding")
    return chunks


def build_vector_store() -> FAISS:
    """
    Build and save a FAISS vector store from compliance documents.
    Returns the FAISS store object.
    """
    logger.info("Building FAISS vector store from compliance documents…")
    embeddings = OpenAIEmbeddings()

    docs = _load_documents()
    chunks = _split_documents(docs)

    store = FAISS.from_documents(chunks, embeddings)

    # Persist to disk
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    store.save_local(str(INDEX_DIR))
    logger.info(f"FAISS index saved to: {INDEX_DIR}")

    return store


def load_vector_store() -> FAISS:
    """
    Load a previously saved FAISS index from disk.
    Falls back to building a new one if the index doesn't exist.
    """
    embeddings = OpenAIEmbeddings()

    if INDEX_DIR.exists() and any(INDEX_DIR.iterdir()):
        logger.info(f"Loading existing FAISS index from: {INDEX_DIR}")
        return FAISS.load_local(
            str(INDEX_DIR),
            embeddings,
            allow_dangerous_deserialization=True,  # Required by LangChain >=0.1.0
        )

    logger.warning("No existing FAISS index found — building now…")
    return build_vector_store()
