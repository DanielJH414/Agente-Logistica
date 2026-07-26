from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

database_dir = backend_dir / "Base de datos"
if str(database_dir) not in sys.path:
    sys.path.append(str(database_dir))

oracle_cloud_dir = backend_dir / "Oracle cloud"
if str(oracle_cloud_dir) not in sys.path:
    sys.path.append(str(oracle_cloud_dir))

STATIC_DIR = backend_dir.parent / "Frontend"
VECTOR_STORE_DIR = backend_dir / "chroma_store"
DOCUMENTS_DIR = backend_dir / "Documentos Nexus"


def _load_pipeline_module() -> Any:
    pipeline_path = database_dir / "pipeline_sync.py"
    pipeline_spec = importlib.util.spec_from_file_location("pipeline_sync", pipeline_path)
    if pipeline_spec is None or pipeline_spec.loader is None:
        raise ImportError(f"No se pudo cargar el sincronizador desde {pipeline_path}")
    pipeline_module = importlib.util.module_from_spec(pipeline_spec)
    pipeline_spec.loader.exec_module(pipeline_module)
    return pipeline_module


@lru_cache(maxsize=1)
def get_runtime() -> Dict[str, Any]:
    from Indexacion.BaseVectores import ChromaVectorStore
    from RAG.Camada import RAGService
    from database import create_chat_log, get_connection, init_db, save_feedback
    from documentos_oci import sync_object_storage

    vector_store = ChromaVectorStore(persist_directory=VECTOR_STORE_DIR)

    init_error: Exception | None = None
    try:
        init_db()
    except Exception as exc:  # pragma: no cover - se usa para fallbacks en entorno local sin Oracle
        init_error = exc
        print(f"No se pudo inicializar Oracle DB: {exc}")

    pipeline_module = _load_pipeline_module()

    try:
        sync_summary = sync_object_storage(DOCUMENTS_DIR)
        print(f"Sincronización desde OCI: {sync_summary}")
    except Exception as exc:
        print(f"No se pudo sincronizar el caché local desde OCI: {exc}")
        sync_summary = {"error": str(exc)}

    try:
        with get_connection() as startup_conn:
            registered_count = startup_conn.execute("SELECT COUNT(*) FROM file_registry").fetchone()[0]
        if registered_count == 0 and vector_store.count() > 0:
            existing_ids = vector_store.collection.get(include=[]).get("ids", [])
            if existing_ids:
                vector_store.collection.delete(ids=existing_ids)
    except Exception as exc:  # pragma: no cover - depende de la configuración Oracle
        print(f"No se pudo validar el registro inicial de documentos: {exc}")

    try:
        print(f"Sincronización inicial: {pipeline_module.check_local_files(DOCUMENTS_DIR, vector_store)}")
    except FileNotFoundError as exc:
        print(f"No se pudo sincronizar Documentos Nexus: {exc}")
    except Exception as exc:
        print(f"No se pudo ejecutar la sincronización inicial: {exc}")

    try:
        rag_service = RAGService(vector_store=vector_store)
    except Exception as exc:
        print(f"Error inicializando el servicio RAG: {exc}")
        rag_service = None

    return {
        "vector_store": vector_store,
        "rag_service": rag_service,
        "pipeline_module": pipeline_module,
        "documents_dir": DOCUMENTS_DIR,
        "static_dir": STATIC_DIR,
        "sync_summary": sync_summary,
        "init_error": init_error,
    }


def build_document_folders(base_dir: Path | str | None = None) -> Dict[str, Any]:
    base = Path(base_dir or DOCUMENTS_DIR).resolve()
    docs: List[Dict[str, Any]] = []
    for path in sorted(base.rglob("*")):
        if path.is_file():
            rel = path.relative_to(base)
            parts = rel.parts
            top = parts[0] if parts else ""
            docs.append(
                {
                    "top": top,
                    "name": path.name,
                    "relative_path": str(rel).replace("\\", "/"),
                }
            )

    folders: Dict[str, List[Dict[str, Any]]] = {}
    for entry in docs:
        top = entry["top"] or "root"
        if top == "Responsables":
            continue
        folders.setdefault(top, []).append(
            {"name": entry["name"], "relative_path": entry["relative_path"]}
        )

    return {"folders": [{"id": i + 1, "title": k, "source": k, "files": v} for i, (k, v) in enumerate(sorted(folders.items()))]}


def build_sources_payload(result: Any, documents_dir: Path | None = None) -> List[Dict[str, Any]]:
    documents_root = Path(documents_dir or DOCUMENTS_DIR).resolve()
    sources: List[Dict[str, Any]] = []
    seen_paths: set[str] = set()

    for source in result.sources or []:
        metadata = source.get("metadata", {}) or {}
        caption = (
            metadata.get("area")
            or metadata.get("department")
            or metadata.get("categoria")
            or ""
        )

        rel_candidate = metadata.get("relative_path") or metadata.get("source_file") or metadata.get("id")
        resolved_path = None
        if rel_candidate:
            try:
                rel_norm = str(rel_candidate).replace("\\", "/").lstrip("/")
                candidate = documents_root / Path(rel_norm)
                if candidate.exists():
                    resolved = candidate.resolve()
                    if str(resolved).startswith(str(documents_root)):
                        resolved_path = resolved
                else:
                    name_only = Path(rel_norm).name
                    matches = list(documents_root.rglob(name_only))
                    if matches:
                        resolved_path = matches[0].resolve()
            except Exception:
                resolved_path = None

        if not resolved_path:
            continue

        real_key = str(resolved_path)
        if real_key in seen_paths:
            continue
        seen_paths.add(real_key)

        label = resolved_path.name
        rel = resolved_path.relative_to(documents_root)
        parts = [quote(part) for part in rel.parts if part]
        link = f"/documentos/{'/'.join(parts)}"
        sources.append({"label": label, "link": link, "caption": caption})

    return sources


def ask_question(question: str, top_k: int = 8, rerank_top_n: int = 5) -> Dict[str, Any]:
    if not question.strip():
        raise ValueError("La pregunta no puede estar vacía.")

    from database import create_chat_log

    runtime = get_runtime()
    rag_service = runtime.get("rag_service")
    if rag_service is None:
        raise RuntimeError("No fue posible inicializar el servicio RAG")

    pipeline_module = runtime.get("pipeline_module")
    documents_dir = runtime.get("documents_dir")
    vector_store = runtime.get("vector_store")

    sync_summary = pipeline_module.check_local_files(documents_dir, vector_store)
    if sync_summary.get("created") or sync_summary.get("updated") or sync_summary.get("deleted"):
        print(f"Documentos sincronizados antes de la consulta: {sync_summary}")

    result = rag_service.answer_question(
        question=question,
        top_k=top_k,
        rerank_top_n=rerank_top_n,
        include_metadata_keys=["source_file", "relative_path", "area", "department", "categoria"],
    )

    try:
        log_id = create_chat_log(question, result.answer)
    except Exception as exc:  # pragma: no cover - depende de Oracle
        print(f"No se pudo registrar la interacción en Oracle: {exc}")
        log_id = None

    return {
        "question": question,
        "answer": result.answer,
        "sources": build_sources_payload(result, documents_dir),
        "used_fallback": result.used_fallback,
        "used_generation": getattr(result, "used_generation", False),
        "log_id": log_id,
        "sync_summary": sync_summary,
    }


def submit_feedback(log_id: int, rating: int, comment: str | None = None) -> Dict[str, Any]:
    from database import save_feedback

    save_feedback(log_id, rating, comment)
    return {"ok": True, "log_id": log_id, "rating": rating}


def get_document_payload() -> Dict[str, Any]:
    return build_document_folders(DOCUMENTS_DIR)


def get_documents_dir() -> Path:
    return DOCUMENTS_DIR


def get_static_dir() -> Path:
    return STATIC_DIR
