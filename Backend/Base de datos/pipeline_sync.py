import os
import hashlib
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from database import get_connection

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".csv", ".txt", ".md", ".json", ".xml", ".yaml", ".yml"}

def calculate_file_hash(filepath):
    """Calcula el hash SHA-256 de un archivo local."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def _load_processing_module() -> Any:
    backend_dir = Path(__file__).resolve().parent.parent
    processor_path = backend_dir / "Procesar Documentos" / "Procesamiento.py"
    spec = importlib.util.spec_from_file_location("pipeline_processing", processor_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar el procesador desde {processor_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _document_key(path: Path, folder_path: Path) -> str:
    return path.relative_to(folder_path).as_posix()


def _index_document(vector_store: Any, processing_module: Any, path: Path, folder_path: Path) -> int:
    processed = processing_module.process_documents(path.parent)
    document = next(item for item in processed if Path(item["relative_path"]) == Path(path.name))
    relative_path = _document_key(path, folder_path)
    for chunk in document.get("chunk_records", []):
        chunk["chunk_id"] = hashlib.sha256(f"{relative_path}:{chunk['chunk_id']}".encode()).hexdigest()
        chunk.setdefault("metadata", {})["relative_path"] = relative_path
    index_documents = []
    for chunk in document.get("chunk_records", []):
        metadata = dict(chunk.get("metadata", {}))
        metadata.update({"source_file": document["file_name"], "relative_path": relative_path, "extension": document["extension"], "chunk_count": document["chunk_count"]})
        index_documents.append({"id": chunk["chunk_id"], "text": chunk["text"], "metadata": metadata})
    vector_store.add_documents(index_documents)
    return len(index_documents)


def check_local_files(folder_path: str | Path, vector_store: Any) -> Dict[str, int]:
    """Sincroniza altas, cambios y bajas entre los documentos y Chroma."""
    folder = Path(folder_path).resolve()
    processing_module = _load_processing_module()
    current_files = {
        _document_key(path, folder): path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    }
    now = datetime.now()
    summary = {"created": 0, "updated": 0, "deleted": 0, "unchanged": 0, "chunks": 0}

    with get_connection() as conn:
        registered = {row["file_path"]: row for row in conn.execute("SELECT * FROM file_registry")}

        for relative_path, path in current_files.items():
            file_hash = calculate_file_hash(str(path))
            old = registered.get(relative_path)
            if old and old["file_hash"] == file_hash:
                summary["unchanged"] += 1
                continue

            vector_store.collection.delete(where={"relative_path": relative_path})
            chunks = _index_document(vector_store, processing_module, path, folder)
            if old:
                conn.execute(
                    "UPDATE file_registry SET file_hash = :file_hash, last_modified = :last_modified, last_indexed = :last_indexed WHERE file_path = :file_path",
                    {"file_hash": file_hash, "last_modified": now, "last_indexed": now, "file_path": relative_path},
                )
                summary["updated"] += 1
            else:
                conn.execute(
                    "INSERT INTO file_registry (file_path, file_hash, last_modified, last_indexed) VALUES (:file_path, :file_hash, :last_modified, :last_indexed)",
                    {"file_path": relative_path, "file_hash": file_hash, "last_modified": now, "last_indexed": now},
                )
                summary["created"] += 1
            summary["chunks"] += chunks

        for relative_path in set(registered) - set(current_files):
            vector_store.collection.delete(where={"relative_path": relative_path})
            conn.execute("DELETE FROM file_registry WHERE file_path = :file_path", {"file_path": relative_path})
            summary["deleted"] += 1

    return summary