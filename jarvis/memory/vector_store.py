"""
VectorStore — semantic long-term memory using ChromaDB + sentence-transformers.

Falls back gracefully to an empty no-op store if the heavy dependencies
(chromadb / sentence_transformers) are not installed, so JARVIS stays
functional in lightweight environments.
"""
from __future__ import annotations
import logging
import os
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ── Attempt to import heavy dependencies ──────────────────────────────────────

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from sentence_transformers import SentenceTransformer
    _DEPS_AVAILABLE = True
    logger.info("VectorStore: chromadb + sentence-transformers available ✓")
except ImportError:
    _DEPS_AVAILABLE = False
    logger.warning(
        "VectorStore: chromadb or sentence-transformers not installed. "
        "Semantic memory disabled — falling back to recency-only memory."
    )


# ── VectorStore ───────────────────────────────────────────────────────────────

class VectorStore:
    """
    Embeds conversation turns and stores them in ChromaDB for semantic recall.

    Usage:
        store = VectorStore()
        store.add("user", "I'm studying for my physics exam next week")
        results = store.search("what was I working on?", n=5)
    """

    EMBED_MODEL = "all-MiniLM-L6-v2"   # ~80 MB, fast, good quality
    DB_DIR      = ".jarvis/chroma"

    def __init__(self):
        self._enabled = False
        self._embedder = None
        self._collection = None

        if not _DEPS_AVAILABLE:
            return

        try:
            os.makedirs(self.DB_DIR, exist_ok=True)
            self._embedder = SentenceTransformer(self.EMBED_MODEL)
            chroma_client = chromadb.PersistentClient(
                path=self.DB_DIR,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = chroma_client.get_or_create_collection(
                name="jarvis_memory",
                metadata={"hnsw:space": "cosine"},
            )
            self._enabled = True
            logger.info(
                "VectorStore: initialised (collection has "
                f"{self._collection.count()} documents)"
            )
        except Exception as exc:
            logger.error(f"VectorStore init failed: {exc}")

    # ── Public API ────────────────────────────────────────────────────────────

    def add(self, role: str, content: str, doc_id: Optional[str] = None) -> None:
        """Embed and persist a single conversation turn."""
        if not self._enabled:
            return
        if not content.strip():
            return
        try:
            import uuid
            uid = doc_id or str(uuid.uuid4())
            embedding = self._embedder.encode(content).tolist()
            self._collection.upsert(
                documents=[content],
                embeddings=[embedding],
                metadatas=[{"role": role}],
                ids=[uid],
            )
        except Exception as exc:
            logger.error(f"VectorStore.add error: {exc}")

    def search(self, query: str, n: int = 5) -> List[Dict[str, str]]:
        """
        Return the top-N semantically similar past turns.

        Returns:
            List of {"role": ..., "content": ...} dicts, ordered by relevance.
        """
        if not self._enabled or not query.strip():
            return []
        try:
            count = self._collection.count()
            if count == 0:
                return []
            n = min(n, count)
            embedding = self._embedder.encode(query).tolist()
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=n,
                include=["documents", "metadatas", "distances"],
            )
            items = []
            docs  = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances",  [[]])[0]
            for doc, meta, dist in zip(docs, metas, dists):
                # Filter out very dissimilar results (cosine distance > 0.7)
                if dist < 0.7:
                    items.append({"role": meta.get("role", "user"), "content": doc})
            return items
        except Exception as exc:
            logger.error(f"VectorStore.search error: {exc}")
            return []

    def format_context(self, results: List[Dict[str, str]]) -> str:
        """Format search results as a readable memory block for the LLM."""
        if not results:
            return ""
        lines = ["[Relevant past context retrieved from long-term memory:]"]
        for r in results:
            label = "You said" if r["role"] == "user" else "JARVIS replied"
            lines.append(f"  • {label}: {r['content'][:200]}")
        return "\n".join(lines)

    @property
    def enabled(self) -> bool:
        return self._enabled
