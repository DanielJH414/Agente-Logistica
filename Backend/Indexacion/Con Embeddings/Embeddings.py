from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from BaseVectores import ChromaVectorStore


def load_processor_module() -> Any:
    """Carga el módulo de procesamiento desde la carpeta de procesamiento."""
    processor_path = Path(__file__).resolve().parent.parent / "Procesar Documentos" / "Procesamiento.py"
    spec = importlib.util.spec_from_file_location("procesamiento_module", processor_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar el módulo de procesamiento desde {processor_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_index_documents(processed_documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convierte los resultados del pipeline en documentos listos para indexar."""
    index_documents: List[Dict[str, Any]] = []

    for document in processed_documents:
        chunk_records = document.get("chunk_records") or []
        if not chunk_records:
            chunk_records = [{"chunk_id": f"{document['file_name']}_chunk_1", "text": document.get("preview", ""), "metadata": document.get("metadata", {})}]

        for chunk in chunk_records:
            metadata = dict(chunk.get("metadata", {}))
            metadata.update(
                {
                    "source_file": document.get("file_name", ""),
                    "relative_path": document.get("relative_path", ""),
                    "extension": document.get("extension", ""),
                    "chunk_count": document.get("chunk_count", 0),
                }
            )

            index_documents.append(
                {
                    "id": chunk.get("chunk_id") or f"{document['file_name']}_chunk_{len(index_documents) + 1}",
                    "text": chunk.get("text", ""),
                    "metadata": metadata,
                }
            )

    return index_documents


def create_vector_index(processed_documents: List[Dict[str, Any]], persist_directory: Path | None = None) -> ChromaVectorStore:
    """Crea o reutiliza una colección Chroma y carga los documentos procesados."""
    if persist_directory is None:
        persist_directory = Path(__file__).resolve().parent.parent / "chroma_store"

    persist_directory.mkdir(parents=True, exist_ok=True)
    vector_store = ChromaVectorStore(persist_directory=persist_directory, collection_name="nexus_documents")
    index_documents = build_index_documents(processed_documents)

    if index_documents:
        vector_store.add_documents(index_documents)

    return vector_store


def run_embedding_pipeline() -> Dict[str, Any]:
    """Ejecuta el pipeline completo: procesamiento -> embeddings -> indexación."""
    base_dir = Path(__file__).resolve().parent.parent
    documents_dir = base_dir / "Documentos Nexus"

    if not documents_dir.exists():
        raise FileNotFoundError(f"No se encontró la carpeta de documentos: {documents_dir}")

    processing_module = load_processor_module()
    processed_documents = processing_module.process_documents(documents_dir)
    vector_store = create_vector_index(processed_documents)

    summary = {
        "documents_processed": len(processed_documents),
        "chunks_indexed": vector_store.count(),
        "collection_name": vector_store.collection_name,
        "persist_directory": str(vector_store.persist_directory),
    }

    return summary


if __name__ == "__main__":
    summary = run_embedding_pipeline()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
