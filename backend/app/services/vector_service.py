"""Vector database service using ChromaDB for document indexing and search."""
import uuid
from typing import List, Optional, Dict

import chromadb
from chromadb.utils import embedding_functions

from ..config import settings


class VectorService:
    """Service for managing vector embeddings with ChromaDB."""

    _client = None
    _embedding_fn = None

    @classmethod
    def get_client(cls) -> chromadb.ClientAPI:
        """Get or create ChromaDB client (singleton)."""
        if cls._client is None:
            cls._client = chromadb.PersistentClient(
                path=settings.chroma_persist_dir,
            )
        return cls._client

    @classmethod
    def get_embedding_function(cls):
        """Get or create the embedding function (singleton)."""
        if cls._embedding_fn is None:
            cls._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=settings.embedding_model,
            )
        return cls._embedding_fn

    @classmethod
    def get_collection(cls, project_id: str) -> chromadb.Collection:
        """Get or create a collection for a project."""
        client = cls.get_client()
        return client.get_or_create_collection(
            name=f"project_{project_id}",
            metadata={"hnsw:space": "cosine"},
            embedding_function=cls.get_embedding_function(),
        )

    @classmethod
    def index_chunks(
        cls,
        project_id: str,
        chunks: List[Dict],
    ) -> List[str]:
        """Index document chunks into ChromaDB.

        Args:
            project_id: The project UUID
            chunks: List of dicts with keys: id, content, metadata

        Returns:
            List of embedding IDs
        """
        collection = cls.get_collection(project_id)

        ids = []
        documents = []
        metadatas = []

        for chunk in chunks:
            chunk_id = str(chunk.get("id", uuid.uuid4()))
            ids.append(chunk_id)
            documents.append(f"passage: {chunk['content']}")
            metadatas.append({
                "document_id": str(chunk.get("document_id", "")),
                "document_name": chunk.get("document_name", ""),
                "category": chunk.get("category", ""),
                "page_number": chunk.get("page_number", 0),
                "section_title": chunk.get("section_title", ""),
                "chunk_index": chunk.get("chunk_index", 0),
            })

        if ids:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )

        return ids

    @classmethod
    def search(
        cls,
        project_id: str,
        query: str,
        top_k: int = 10,
        category_filter: Optional[str] = None,
    ) -> List[Dict]:
        """Search for similar chunks in the vector database.

        Args:
            project_id: The project UUID
            query: Search query text
            top_k: Number of results to return
            category_filter: Optional filter by document category

        Returns:
            List of search results with content, metadata, and score
        """
        collection = cls.get_collection(project_id)

        where_filter = None
        if category_filter:
            where_filter = {"category": category_filter}

        try:
            results = collection.query(
                query_texts=[f"query: {query}"],
                n_results=top_k,
                where=where_filter,
            )
        except Exception:
            return []

        search_results = []
        if results and results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0
                score = 1 - distance  # Convert distance to similarity score

                search_results.append({
                    "chunk_id": results["ids"][0][i],
                    "content": doc,
                    "document_name": metadata.get("document_name", ""),
                    "category": metadata.get("category", ""),
                    "page_number": metadata.get("page_number", 0),
                    "section_title": metadata.get("section_title", ""),
                    "score": round(score, 4),
                })

        return search_results

    @classmethod
    def delete_project_data(cls, project_id: str):
        """Delete all vector data for a project."""
        client = cls.get_client()
        collection_name = f"project_{project_id}"
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

    @classmethod
    def delete_document_chunks(cls, project_id: str, document_id: str):
        """Delete all chunks for a specific document from the vector DB."""
        collection = cls.get_collection(project_id)
        try:
            # Get all chunk IDs for this document
            results = collection.get(
                where={"document_id": document_id},
            )
            if results and results["ids"]:
                collection.delete(ids=results["ids"])
        except Exception:
            pass
