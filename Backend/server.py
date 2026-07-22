from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, quote, unquote
import mimetypes

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))
database_dir = backend_dir / "Base de datos"
if str(database_dir) not in sys.path:
    sys.path.append(str(database_dir))

from Indexacion.BaseVectores import ChromaVectorStore
from RAG.Camada import RAGService
from database import create_chat_log, get_connection, init_db, save_feedback

static_dir = backend_dir.parent / "Frontend"
vector_store_dir = backend_dir / "chroma_store"
documents_dir = backend_dir / "Documentos Nexus"

vector_store = ChromaVectorStore(persist_directory=vector_store_dir)

init_db()
pipeline_path = database_dir / "pipeline_sync.py"
pipeline_spec = importlib.util.spec_from_file_location("pipeline_sync", pipeline_path)
if pipeline_spec is None or pipeline_spec.loader is None:
    raise ImportError(f"No se pudo cargar el sincronizador desde {pipeline_path}")
pipeline_module = importlib.util.module_from_spec(pipeline_spec)
pipeline_spec.loader.exec_module(pipeline_module)

with get_connection() as startup_conn:
    registered_count = startup_conn.execute("SELECT COUNT(*) FROM file_registry").fetchone()[0]
if registered_count == 0 and vector_store.count() > 0:
    existing_ids = vector_store.collection.get(include=[]).get("ids", [])
    if existing_ids:
        vector_store.collection.delete(ids=existing_ids)

try:
    print(f"Sincronización inicial: {pipeline_module.check_local_files(documents_dir, vector_store)}")
except FileNotFoundError as exc:
    print(f"No se pudo sincronizar Documentos Nexus: {exc}")

try:
    rag_service = RAGService(vector_store=vector_store)
except Exception as exc:
    print(f"Error inicializando el servicio RAG: {exc}")
    raise


class BackendHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | Path | None = None, **kwargs):
        super().__init__(*args, directory=str(static_dir), **kwargs)

    def end_headers(self) -> None:
        self.send_cors_headers()
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/ask":
            self.handle_ask()
        elif parsed.path == "/api/feedback":
            self.handle_feedback()
        else:
            self.send_error(404, "Endpoint no encontrado")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        # API endpoint returning the Documentos Nexus structure
        if parsed.path == "/api/documents":
            try:
                docs = []
                base = documents_dir.resolve()
                for p in sorted(base.rglob('*')):
                    if p.is_file():
                        rel = p.relative_to(base)
                        parts = rel.parts
                        top = parts[0] if parts else ''
                        docs.append({
                            'top': top,
                            'name': p.name,
                            'relative_path': str(rel).replace('\\', '/'),
                        })
                # Group by top-level folder and exclude internal folders like 'Responsables'
                folders = {}
                for entry in docs:
                    top = entry['top'] or 'root'
                    if top == 'Responsables':
                        continue
                    folders.setdefault(top, []).append({'name': entry['name'], 'relative_path': entry['relative_path']})
                resp = [{'id': i+1, 'title': k, 'source': k, 'files': v} for i, (k, v) in enumerate(sorted(folders.items()))]
                self.send_json({'folders': resp})
            except Exception as exc:
                print('Error building /api/documents:', exc)
                self.send_json({'error': 'No se pudo listar documentos'}, status=500)
            return

        # Serve document files under /documentos/... mapped to Backend/Documentos Nexus
        if parsed.path.startswith("/documentos/"):
            # URL-decode the requested path segments so filesystem lookup matches
            rel_path = unquote(parsed.path[len("/documentos/"):])
            # Prevent directory traversal
            target = (documents_dir / Path(rel_path)).resolve()
            try:
                if not str(target).startswith(str(documents_dir.resolve())) or not target.exists():
                    self.send_error(404, "Documento no encontrado")
                    return
                # Guess mime type
                ctype, _ = mimetypes.guess_type(str(target))
                if ctype is None:
                    ctype = "application/octet-stream"
                with open(target, "rb") as fh:
                    data = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as exc:
                print(f"Error sirviendo documento {target}: {exc}")
                self.send_error(500, "Error interno al servir documento")
                return
            # Fallback to normal static handling (Frontend)
        return super().do_GET()

    def handle_ask(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length)
            body = json.loads(raw_body.decode("utf-8"))
            question = str(body.get("question", "")).strip()
            if not question:
                raise ValueError("La pregunta no puede estar vacía.")
        except Exception as exc:
            self.send_json({"error": "Solicitud inválida", "details": str(exc)}, status=400)
            return

        try:
            sync_summary = pipeline_module.check_local_files(documents_dir, vector_store)
            if sync_summary["created"] or sync_summary["updated"] or sync_summary["deleted"]:
                print(f"Documentos sincronizados antes de la consulta: {sync_summary}")
            print(f"[API] Pregunta recibida: {question}")
            print("[API] Llamando a rag_service.answer_question()...")
            try:
                result = rag_service.answer_question(
                    question=question,
                    top_k=8,
                    rerank_top_n=5,
                    include_metadata_keys=["source_file", "relative_path", "area", "department", "categoria"],
                )
            except Exception as inner_exc:
                print("[API] Excepción en rag_service.answer_question():", inner_exc)
                try:
                    with open(backend_dir / "backend_debug.log", "a", encoding="utf-8") as fh:
                        fh.write("RAG CALL ERROR---\n")
                        fh.write(f"Pregunta: {question}\n")
                        import traceback as _tb

                        fh.write(_tb.format_exc())
                        fh.write("\n")
                except Exception:
                    print("[API] No se pudo escribir backend_debug.log dentro del inner-except")
                raise
            print("[API] rag_service respondió correctamente")
            log_id = create_chat_log(question, result.answer)
            try:
                print(f"[API] result type: {type(result)}, sources: {len(result.sources) if getattr(result, 'sources', None) is not None else 0}")
            except Exception:
                print("[API] No se pudo inspeccionar result.sources")
            sources = []
            seen_paths = set()
            for idx, source in enumerate(result.sources or [], start=1):
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
                        rel_norm = str(rel_candidate).replace('\\', '/').lstrip('/')
                        candidate = (documents_dir / Path(rel_norm))
                        if candidate.exists():
                            resolved = candidate.resolve()
                            # Ensure it's inside documents_dir
                            if str(resolved).startswith(str(documents_dir.resolve())):
                                resolved_path = resolved
                        else:
                            # Try to find by filename anywhere under documents_dir
                            name_only = Path(rel_norm).name
                            matches = list(documents_dir.rglob(name_only))
                            if matches:
                                resolved_path = matches[0].resolve()
                    except Exception:
                        resolved_path = None

                if not resolved_path:
                    # skip sources without an actual file
                    continue

                # Deduplicate by real path
                real_key = str(resolved_path)
                if real_key in seen_paths:
                    continue
                seen_paths.add(real_key)

                # label shown to user: use filename
                label = resolved_path.name

                # Build link using URL-encoded path relative to documents_dir
                rel = resolved_path.relative_to(documents_dir.resolve())
                parts = [quote(p) for p in rel.parts if p]
                link = f"/documentos/{'/'.join(parts)}"

                sources.append({"label": label, "link": link, "caption": caption})

            self.send_json(
                {
                    "question": question,
                    "answer": result.answer,
                    "sources": sources,
                    "used_fallback": result.used_fallback,
                    "used_generation": getattr(result, "used_generation", False),
                    "log_id": log_id,
                }
            )
        except Exception as exc:
            # Imprimir traza y además guardarla en un archivo de debugging para revisar fuera del terminal
            traceback.print_exc()
            print(f"[API] Error interno al procesar pregunta: {exc}")
            try:
                with open(backend_dir / "backend_debug.log", "a", encoding="utf-8") as fh:
                    fh.write("---\n")
                    fh.write(f"Pregunta: {question}\n")
                    fh.write(traceback.format_exc())
                    fh.write("\n")
            except Exception:
                print("[API] No se pudo escribir backend_debug.log")
            self.send_json(
                {"error": "Error interno del servidor", "details": str(exc)},
                status=500,
            )

    def handle_feedback(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            log_id = int(body.get("log_id"))
            rating = int(body.get("rating"))
            comment = body.get("comment")
            save_feedback(log_id, rating, str(comment) if comment is not None else None)
            self.send_json({"ok": True, "log_id": log_id, "rating": rating})
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": "Feedback inválido", "details": str(exc)}, status=400)

    def send_json(self, body: dict, status: int = 200) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def run(server_address: tuple[str, int] = ("127.0.0.1", 8000)) -> None:
    print(f"Iniciando servidor en http://{server_address[0]}:{server_address[1]}")
    print(f"Sirviendo archivos estáticos desde: {static_dir}")
    print("Usando el endpoint POST /api/ask para consultar al agente IA.")
    server = ThreadingHTTPServer(server_address, BackendHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
