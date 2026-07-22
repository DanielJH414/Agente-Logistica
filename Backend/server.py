from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from Indexacion.BaseVectores import ChromaVectorStore
from RAG.Camada import RAGService

static_dir = backend_dir.parent / "Frontend"
vector_store_dir = backend_dir / "chroma_store"

vector_store = ChromaVectorStore(persist_directory=vector_store_dir)
if vector_store.count() == 0:
    print("Vector store vacío. Generando índice a partir de Documentos Nexus...")
    embeddings_module_path = backend_dir / "Indexacion" / "Con Embeddings" / "Embeddings.py"
    spec = importlib.util.spec_from_file_location("embeddings_module", str(embeddings_module_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar el módulo de embeddings desde {embeddings_module_path}")
    embeddings_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(embeddings_module)
    try:
        summary = embeddings_module.run_embedding_pipeline()
        print(f"Índice generado: {summary}")
    except FileNotFoundError as exc:
        print(f"No se pudo generar el índice automático: {exc}")

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
        else:
            self.send_error(404, "Endpoint no encontrado")

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
            try:
                print(f"[API] result type: {type(result)}, sources: {len(result.sources) if getattr(result, 'sources', None) is not None else 0}")
            except Exception:
                print("[API] No se pudo inspeccionar result.sources")
            sources = []
            for idx, source in enumerate(result.sources or [], start=1):
                metadata = source.get("metadata", {}) or {}
                label = (
                    metadata.get("source_file")
                    or metadata.get("relative_path")
                    or metadata.get("id")
                    or f"Fuente {idx}"
                )
                caption = (
                    metadata.get("area")
                    or metadata.get("department")
                    or metadata.get("categoria")
                    or ""
                )
                sources.append({"label": label, "link": "#", "caption": caption})

            self.send_json(
                {
                    "question": question,
                    "answer": result.answer,
                    "sources": sources,
                    "used_fallback": result.used_fallback,
                    "used_generation": getattr(result, "used_generation", False),
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
