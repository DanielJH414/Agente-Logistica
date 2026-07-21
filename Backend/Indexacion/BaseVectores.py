from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


def normalize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Convierte los metadatos a un formato serializable y compatible con Chroma."""
    normalized: Dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            normalized[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        else:
            normalized[key] = json.dumps(value, ensure_ascii=False)
    return normalized


class ChromaVectorStore:
    """Wrapper simple para interactuar con ChromaDB como almacén vectorial local."""

    def __init__(self, persist_directory: Path | str, collection_name: str = "nexus_documents") -> None:
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(path=str(self.persist_directory), settings=Settings(allow_reset=True))
        self.embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.embedding_model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def add_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Agrega documentos con texto, IDs y metadatos a la colección Chroma."""
        if not documents:
            return

        ids = [doc["id"] for doc in documents]
        texts = [doc["text"] for doc in documents]
        metadatas = [normalize_metadata(doc.get("metadata", {})) for doc in documents]
        embeddings = self._embed_texts(texts)

        self.collection.add(
            embeddings=embeddings,
            metadatas=metadatas,
            documents=texts,
            ids=ids,
        )

    def count(self) -> int:
        return self.collection.count()

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        metadata_filter: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """Busca los chunks más similares a una consulta.

        Se puede aplicar un filtro de metadatos para reducir los resultados.
        """
        embedding = self._embed_texts([query_text])[0]

        query_kwargs: Dict[str, Any] = {}
        if metadata_filter:
            query_kwargs["where"] = normalize_metadata(metadata_filter)

        try:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
                **query_kwargs,
            )
        except TypeError:
            # Chroma older versions may no soportar el argumento `where`.
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

        matches: List[Dict[str, Any]] = []
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for i in range(len(documents)):
            if metadata_filter:
                normalized = normalize_metadata(metadatas[i])
                if not all(normalized.get(key) == value for key, value in normalize_metadata(metadata_filter).items()):
                    continue

            matches.append(
                {
                    "document": documents[i],
                    "metadata": metadatas[i],
                    "distance": distances[i],
                }
            )

        return matches[:top_k]

    def save_snapshot(self, output_path: Path | str) -> None:
        """Guarda una instantánea de la colección en un JSON simple para inspección."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        all_items = self.collection.get(include=["documents", "metadatas", "embeddings"])
        payload = {
            "collection_name": self.collection_name,
            "count": len(all_items["ids"]),
            "items": [
                {
                    "id": item_id,
                    "document": document,
                    "metadata": metadata,
                    "embedding_dim": len(embedding) if embedding is not None else 0,
                }
                for item_id, document, metadata, embedding in zip(
                    all_items["ids"],
                    all_items["documents"],
                    all_items["metadatas"],
                    all_items["embeddings"],
                )
            ],
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
