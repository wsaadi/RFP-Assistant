"""Vector database service using pgvector (PostgreSQL) for document indexing and search.

Replaces the previous ChromaDB/SQLite implementation with pgvector, which:
- Handles concurrent writes natively (no file locking needed)
- Uses the existing PostgreSQL instance (no separate service)
- Is production-grade and scales with the database
"""
import logging
import uuid
from typing import List, Optional, Dict

import psycopg
from psycopg.rows import dict_row
from sentence_transformers import SentenceTransformer

from ..config import settings

logger = logging.getLogger(__name__)

# Max sequence length supported by multilingual-e5-base
_MODEL_MAX_SEQ_LENGTH = 512

# Batch size for embedding computation (memory-bounded)
_EMBED_BATCH_SIZE = 64


def _build_sync_dsn() -> str:
    """Build a synchronous PostgreSQL DSN from the async database_url.

    Converts ``postgresql+asyncpg://user:pass@host/db``
    to ``postgresql://user:pass@host/db`` (libpq format).
    """
    url = settings.database_url
    # Remove SQLAlchemy async driver prefix
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    # Already a sync URL or other format
    return url.replace("postgres://", "postgresql://", 1)


class VectorService:
    """Service for managing vector embeddings with pgvector (PostgreSQL)."""

    _embedding_model: Optional[SentenceTransformer] = None

    @classmethod
    def get_embedding_function(cls) -> SentenceTransformer:
        """Get or create the embedding model (singleton)."""
        if cls._embedding_model is None:
            cls._embedding_model = SentenceTransformer(settings.embedding_model)
            cls._embedding_model.max_seq_length = _MODEL_MAX_SEQ_LENGTH
            logger.info("Embedding model loaded: %s", settings.embedding_model)
        return cls._embedding_model

    @classmethod
    def _get_connection(cls) -> psycopg.Connection:
        """Open a synchronous PostgreSQL connection with pgvector support."""
        conn = psycopg.connect(_build_sync_dsn(), row_factory=dict_row)
        # Register pgvector type for transparent numpy array <-> vector conversion
        conn.execute("SET statement_timeout = '300s'")
        return conn

    @classmethod
    def _embed_texts(cls, texts: List[str]) -> list:
        """Compute embeddings for a list of texts using the SentenceTransformer model."""
        model = cls.get_embedding_function()
        embeddings = model.encode(
            texts, normalize_embeddings=True,
            batch_size=_EMBED_BATCH_SIZE, show_progress_bar=False,
        )
        return embeddings.tolist()

    # ── Indexing ──

    @classmethod
    def index_chunks(
        cls,
        project_id: str,
        chunks: List[Dict],
    ) -> List[str]:
        """Index document chunks into pgvector.

        Computes embeddings and inserts them into the document_embeddings table.
        PostgreSQL handles concurrent writes natively — no file locking needed.

        Args:
            project_id: The project UUID
            chunks: List of dicts with keys: id, content, document_id, etc.

        Returns:
            List of chunk IDs that were indexed
        """
        if not chunks:
            return []

        # Prepare data
        ids = []
        texts = []
        rows = []

        for chunk in chunks:
            chunk_id = str(chunk.get("id", uuid.uuid4()))
            ids.append(chunk_id)
            text = f"passage: {chunk['content']}"
            texts.append(text)
            rows.append({
                "id": chunk_id,
                "project_id": project_id,
                "document_id": str(chunk.get("document_id", "")),
                "content": text,
                "document_name": chunk.get("document_name", ""),
                "category": chunk.get("category", ""),
                "page_number": chunk.get("page_number", 0),
                "section_title": chunk.get("section_title", ""),
                "chunk_index": chunk.get("chunk_index", 0),
            })

        # Compute embeddings (CPU-bound, can run concurrently)
        logger.info("Computing embeddings for %d chunks...", len(texts))
        all_embeddings = cls._embed_texts(texts)

        # Insert into PostgreSQL (pgvector)
        conn = cls._get_connection()
        try:
            with conn.cursor() as cur:
                for i, row in enumerate(rows):
                    embedding_str = "[" + ",".join(str(v) for v in all_embeddings[i]) + "]"
                    cur.execute(
                        """
                        INSERT INTO document_embeddings
                            (id, project_id, document_id, chunk_id, content, embedding,
                             document_name, category, page_number, section_title, chunk_index)
                        VALUES (%s, %s, %s, %s, %s, %s::vector,
                                %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (
                            row["id"], row["project_id"], row["document_id"],
                            row["id"], row["content"], embedding_str,
                            row["document_name"], row["category"],
                            row["page_number"], row["section_title"],
                            row["chunk_index"],
                        ),
                    )
            conn.commit()
            logger.info("Indexed %d chunks into pgvector for project %s", len(rows), project_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return ids

    # ── Search ──

    @classmethod
    def search(
        cls,
        project_id: str,
        query: str,
        top_k: int = 10,
        category_filter: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
    ) -> List[Dict]:
        """Search for similar chunks using pgvector cosine similarity.

        Args:
            project_id: The project UUID
            query: Search query text
            top_k: Number of results to return
            category_filter: Optional filter by document category
            document_ids: Optional list of document UUIDs to restrict search scope

        Returns:
            List of search results with content, metadata, and similarity score
        """
        # Compute query embedding
        query_embedding = cls._embed_texts([f"query: {query}"])[0]
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        # Build query with optional filters
        conditions = ["project_id = %s"]
        params: list = [project_id]

        if category_filter:
            conditions.append("category = %s")
            params.append(category_filter)

        if document_ids:
            if len(document_ids) == 1:
                conditions.append("document_id = %s")
                params.append(document_ids[0])
            else:
                placeholders = ",".join(["%s"] * len(document_ids))
                conditions.append(f"document_id IN ({placeholders})")
                params.extend(document_ids)

        where_clause = " AND ".join(conditions)
        params.append(embedding_str)
        params.append(top_k)

        sql = f"""
            SELECT id, chunk_id, content, document_id, document_name,
                   category, page_number, section_title, chunk_index,
                   1 - (embedding <=> %s::vector) AS score
            FROM document_embeddings
            WHERE {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        # Need embedding twice: once for score, once for ORDER BY
        params_final = params[:-2] + [embedding_str, embedding_str, top_k]

        try:
            conn = cls._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, params_final)
                    rows = cur.fetchall()
            finally:
                conn.close()
        except Exception as e:
            logger.error("pgvector search failed: %s", e)
            return []

        search_results = []
        for row in rows:
            content = row["content"]
            # Remove the "passage: " prefix added during indexing
            if content.startswith("passage: "):
                content = content[9:]

            search_results.append({
                "chunk_id": str(row["chunk_id"]),
                "content": content,
                "document_id": str(row["document_id"]),
                "document_name": row["document_name"],
                "category": row["category"],
                "page_number": row["page_number"],
                "section_title": row["section_title"],
                "chunk_index": row["chunk_index"],
                "score": round(float(row["score"]), 4),
            })

        return search_results

    # ── Counting ──

    @classmethod
    def collection_count(cls, project_id: str) -> int:
        """Return the number of embeddings for a project."""
        try:
            conn = cls._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) AS cnt FROM document_embeddings WHERE project_id = %s",
                        (project_id,),
                    )
                    row = cur.fetchone()
                    return row["cnt"] if row else 0
            finally:
                conn.close()
        except Exception:
            return 0

    # ── Deletion ──

    @classmethod
    def delete_project_data(cls, project_id: str):
        """Delete all vector data for a project."""
        try:
            conn = cls._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM document_embeddings WHERE project_id = %s",
                        (project_id,),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to delete project vectors: %s", e)

    @classmethod
    def delete_document_chunks(cls, project_id: str, document_id: str):
        """Delete all chunks for a specific document from the vector DB."""
        try:
            conn = cls._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM document_embeddings WHERE project_id = %s AND document_id = %s",
                        (project_id, document_id),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to delete document vectors: %s", e)
