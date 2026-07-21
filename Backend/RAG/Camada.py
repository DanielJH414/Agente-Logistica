from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import re

try:
    from sentence_transformers import SentenceTransformer
except ImportError as exc:
    raise ImportError("sentence-transformers is required for RAG embeddings. Install it before using Camada.py") from exc

try:
    import cohere
except ImportError:  # pragma: no cover
    cohere = None  # type: ignore[assignment]

try:
    import groq
except ImportError:  # pragma: no cover
    groq = None  # type: ignore[assignment]

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from Indexacion.BaseVectores import ChromaVectorStore
from modelos.my_keys import COHERE_API_KEY, GROQ_API_KEY
from modelos.my_models import COHERE_RERANK_MULTILINGUAL, GROQ_LLAMA3_8B


@dataclass
class RAGResult:
    query: str
    context: str
    answer: str
    sources: List[Dict[str, Any]]
    candidates: List[Dict[str, Any]]
    used_fallback: bool


class RAGService:
    def __init__(
        self,
        vector_store: ChromaVectorStore,
        embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        rerank_model: str = COHERE_RERANK_MULTILINGUAL,
        groq_model: str = GROQ_LLAMA3_8B,
        cohere_api_key: Optional[str] = COHERE_API_KEY,
        groq_api_key: Optional[str] = GROQ_API_KEY,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_model_name = embedding_model_name
        self.embedding_model = SentenceTransformer(self.embedding_model_name)
        self.rerank_model = rerank_model
        self.groq_model = groq_model
        self.cohere_api_key = cohere_api_key
        self.groq_api_key = groq_api_key
        self.cohere_client = self._build_cohere_client()
        self.groq_client = self._build_groq_client()

    def _build_cohere_client(self) -> Optional[Any]:
        if not cohere:
            return None
        if not self.cohere_api_key:
            return None
        return cohere.Client(api_key=self.cohere_api_key)

    def _build_groq_client(self) -> Optional[Any]:
        if not groq or not self.groq_api_key:
            return None
        try:
            return groq.Client(api_key=self.groq_api_key)
        except Exception:
            return None

    def embed_query(self, query: str) -> List[float]:
        """Convierte una pregunta en un vector de embedding usando sentence-transformers."""
        embedding = self.embedding_model.encode([query], normalize_embeddings=True)[0]
        return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Recupera los chunks más relevantes desde la base vectorial y aplica un filtro de metadatos."""
        return self.vector_store.query(query_text=query, top_k=top_k, metadata_filter=metadata_filter)

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Reordena los candidatos usando Cohere Rerank."""
        if not self.cohere_client or not candidates:
            return candidates

        top_n = top_n or len(candidates)
        documents = []
        for candidate in candidates:
            documents.append({"text": candidate["document"]})

        response = self.cohere_client.rerank(
            query=query,
            documents=documents,
            model=self.rerank_model,
            top_n=top_n,
            return_documents=False,
        )

        reranked: List[Dict[str, Any]] = []
        if hasattr(response, "results"):
            for result in response.results:
                index = getattr(result, "index", None)
                relevance = getattr(result, "relevance", None)
                if index is None:
                    continue
                candidate = candidates[int(index)]
                candidate = {**candidate, "relevance": relevance}
                reranked.append(candidate)
        else:
            reranked = candidates[:top_n]

        return reranked[:top_n]

    def assemble_context(
        self,
        reranked_candidates: Iterable[Dict[str, Any]],
        max_chars: int = 3000,
        include_metadata_keys: Optional[List[str]] = None,
    ) -> str:
        """Construye el contexto final que se utilizará para la generación."""
        parts: List[str] = []
        total_chars = 0

        for candidate in reranked_candidates:
            metadata = candidate.get("metadata", {}) or {}
            document_text = str(candidate.get("document", "")).strip()
            source = metadata.get("source_file") or metadata.get("relative_path") or metadata.get("id") or "sin fuente"

            header_parts = [f"Fuente: {source}"]
            if include_metadata_keys:
                for key in include_metadata_keys:
                    if key in metadata and metadata[key] is not None:
                        header_parts.append(f"{key}: {metadata[key]}")

            block = "\n".join(header_parts) + "\n" + document_text
            if total_chars + len(block) > max_chars:
                break

            parts.append(block)
            total_chars += len(block)

        return "\n\n---\n\n".join(parts)

    def _build_answer_prompt(self, question: str, context: str) -> str:
        return (
            "Responde la pregunta usando únicamente la información proporcionada en el contexto. "
            "No inventes información. Si no hay una respuesta clara y respaldada por el contexto, responde exactamente: "
            "No tengo suficiente información en los documentos recuperados para responder con certeza.\n\n"
            f"Contexto:\n{context}\n\nPregunta: {question}\nRespuesta:"
        )

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    def _score_context_support(self, question: str, generated_answer: str, context: str) -> tuple[bool, float]:
        if not generated_answer or not context:
            return False, 0.0

        normalized_question = self._normalize_text(question)
        normalized_answer = self._normalize_text(generated_answer)
        normalized_context = self._normalize_text(context)

        overlap_words = set(normalized_question.split()) | set(normalized_answer.split())
        context_terms = set(normalized_context.split())
        shared_terms = overlap_words & context_terms
        support_score = len(shared_terms) / max(1, len(overlap_words))

        answer_has_context_keywords = any(term in normalized_context for term in normalized_answer.split() if len(term) > 4)
        if normalized_answer.startswith("no tengo suficiente información"):
            return False, 0.0

        return (answer_has_context_keywords or support_score >= 0.1), min(1.0, support_score + (0.2 if answer_has_context_keywords else 0.0))

    def _format_answer_with_sources(self, answer: str, sources: List[Dict[str, Any]]) -> str:
        if not answer:
            return "No tengo suficiente información en los documentos recuperados para responder con certeza."

        lines = [answer.strip(), "", "Referencias:"]
        for i, source in enumerate(sources, start=1):
            metadata = source.get("metadata", {}) or {}
            source_name = metadata.get("source_file") or metadata.get("relative_path") or metadata.get("id") or f"Fuente {i}"
            area = metadata.get("area") or metadata.get("department") or metadata.get("categoria") or "Sin área"
            lines.append(f"{i}. {source_name} — Área: {area}")

        return "\n".join(lines)

    def generate_answer(
        self,
        question: str,
        context: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> str:
        """Genera una respuesta final con Groq usando el contexto ensamblado."""
        if not self.groq_client:
            raise RuntimeError(
                "Groq client no disponible. Instala el paquete groq y configura GROQ_API_KEY."
            )

        prompt = self._build_answer_prompt(question, context)
        try:
            if hasattr(self.groq_client, "generate"):
                response = self.groq_client.generate(
                    model=self.groq_model,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return str(response)

            if hasattr(self.groq_client, "completion"):
                response = self.groq_client.completion.create(
                    model=self.groq_model,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return response.choices[0].text

            raise RuntimeError("No se reconoce la interfaz del cliente Groq.")
        except Exception as exc:
            raise RuntimeError(f"Error generando respuesta con Groq: {exc}") from exc

    def answer_question(
        self,
        question: str,
        top_k: int = 10,
        metadata_filter: Optional[Dict[str, Any]] = None,
        rerank_top_n: int = 5,
        context_max_chars: int = 3000,
        include_metadata_keys: Optional[List[str]] = None,
        confidence_threshold: float = 0.25,
    ) -> RAGResult:
        """Ejecuta el flujo completo RAG: recuperación, reranking, ensamblaje, validación y generación."""
        candidates = self.retrieve(query=question, top_k=top_k, metadata_filter=metadata_filter)
        reranked = self.rerank(query=question, candidates=candidates, top_n=rerank_top_n)

        if not reranked:
            fallback = "No tengo suficiente información en los documentos recuperados para responder con certeza."
            return RAGResult(
                query=question,
                context="",
                answer=fallback,
                sources=[],
                candidates=[],
                used_fallback=True,
            )

        best_candidate = reranked[0]
        best_distance = best_candidate.get("distance")
        if best_distance is not None and best_distance > 1.5:
            fallback = "No tengo suficiente información en los documentos recuperados para responder con certeza."
            return RAGResult(
                query=question,
                context=self.assemble_context(reranked, max_chars=context_max_chars, include_metadata_keys=include_metadata_keys),
                answer=fallback,
                sources=[{"metadata": candidate.get("metadata", {}), "distance": candidate.get("distance")} for candidate in reranked],
                candidates=reranked,
                used_fallback=True,
            )

        context = self.assemble_context(reranked, max_chars=context_max_chars, include_metadata_keys=include_metadata_keys)
        answer = self.generate_answer(question=question, context=context)
        is_supported, support_score = self._score_context_support(question=question, generated_answer=answer, context=context)

        if not is_supported or support_score < confidence_threshold:
            fallback = "No tengo suficiente información en los documentos recuperados para responder con certeza."
            return RAGResult(
                query=question,
                context=context,
                answer=self._format_answer_with_sources(fallback, [{"metadata": candidate.get("metadata", {}), "distance": candidate.get("distance")} for candidate in reranked]),
                sources=[{"metadata": candidate.get("metadata", {}), "distance": candidate.get("distance")} for candidate in reranked],
                candidates=reranked,
                used_fallback=True,
            )

        return RAGResult(
            query=question,
            context=context,
            answer=self._format_answer_with_sources(answer, [{"metadata": candidate.get("metadata", {}), "distance": candidate.get("distance")} for candidate in reranked]),
            sources=[{"metadata": candidate.get("metadata", {}), "distance": candidate.get("distance")} for candidate in reranked],
            candidates=reranked,
            used_fallback=False,
        )


if __name__ == "__main__":
    from Indexacion.BaseVectores import ChromaVectorStore

    store = ChromaVectorStore(persist_directory=Path(__file__).resolve().parent.parent / "chroma_store")
    service = RAGService(vector_store=store)

    print("Ejecutando prueba de respuesta RAG sobre rastreo de pedidos...\n")
    question = "¿Cómo puedo rastrear el estado de un pedido?"
    result = service.answer_question(
        question=question,
        top_k=8,
        metadata_filter={"extension": "pdf"},
        rerank_top_n=5,
        include_metadata_keys=["source_file", "extension", "area"],
    )
    print(result.answer)
    print(f"\nFallback utilizado: {'Sí' if result.used_fallback else 'No'}")
