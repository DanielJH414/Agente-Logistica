from __future__ import annotations

import json
import mimetypes
import os
import sys
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from app_service import (  # noqa: E402
    ask_question,
    build_document_folders,
    get_document_payload,
    get_documents_dir,
    get_runtime,
    get_static_dir,
    submit_feedback,
)

static_dir = get_static_dir()
documents_dir = get_documents_dir()

runtime = get_runtime()


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
        if parsed.path == "/api/documents":
            try:
                self.send_json(get_document_payload())
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
            print(f"[API] Pregunta recibida: {question}")
            print("[API] Llamando a ask_question()...")
            try:
                payload = ask_question(question, top_k=8, rerank_top_n=5)
            except Exception as inner_exc:
                print("[API] Excepción en ask_question():", inner_exc)
                try:
                    with open(backend_dir / "backend_debug.log", "a", encoding="utf-8") as fh:
                        fh.write("RAG CALL ERROR---\n")
                        fh.write(f"Pregunta: {question}\n")
                        fh.write(traceback.format_exc())
                        fh.write("\n")
                except Exception:
                    print("[API] No se pudo escribir backend_debug.log dentro del inner-except")
                raise
            print("[API] ask_question respondió correctamente")
            self.send_json(payload)
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
            payload = submit_feedback(log_id, rating, str(comment) if comment is not None else None)
            self.send_json(payload)
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


def run(server_address: tuple[str, int] | None = None) -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    resolved_address = server_address or (host, port)
    print(f"Iniciando servidor en http://{resolved_address[0]}:{resolved_address[1]}")
    print(f"Sirviendo archivos estáticos desde: {static_dir}")
    print("Usando el endpoint POST /api/ask para consultar al agente IA.")
    server = ThreadingHTTPServer(resolved_address, BackendHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
