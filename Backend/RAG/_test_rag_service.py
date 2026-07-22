import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.append(str(root))

sys.modules.setdefault("sentence_transformers", SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: object()))

from RAG.Camada import RAGService


class FakeVectorStore:
    def __init__(self, candidates):
        self.candidates = candidates

    def query(self, query_text, top_k=5, metadata_filter=None):
        return list(self.candidates[:top_k])


class RAGServiceTests(unittest.TestCase):
    def make_service(self, candidates):
        with patch("RAG.Camada.SentenceTransformer", return_value=SimpleNamespace(encode=lambda texts, normalize_embeddings=True: [[0.0, 1.0] for _ in texts])):
            return RAGService(vector_store=FakeVectorStore(candidates))

    def test_returns_structured_answer_with_sources_when_context_is_relevant(self):
        candidates = [
            {
                "document": "Para reportar un incidente de logística, abra un ticket y notifique al equipo de logística.",
                "metadata": {"source_file": "procedimiento_logistica.pdf", "area": "Logística"},
                "distance": 0.1,
            }
        ]
        service = self.make_service(candidates)
        service.generate_answer = lambda question, context, max_tokens=512, temperature=0.0: (
            "Para reportar un incidente de logística, abra un ticket y notifique al equipo de logística."
        )

        result = service.answer_question("¿Cómo reporto un incidente?", top_k=1, rerank_top_n=1)

        self.assertFalse(result.used_fallback)
        self.assertIn("Referencias:", result.answer)
        self.assertIn("procedimiento_logistica.pdf", result.answer)
        self.assertIn("Logística", result.answer)

    def test_falls_back_when_relevance_is_below_threshold(self):
        candidates = [
            {
                "document": "Texto irrelevante para la pregunta del usuario.",
                "metadata": {"source_file": "documento.pdf", "area": "Operaciones"},
                "distance": 3.0,
            }
        ]
        service = self.make_service(candidates)

        result = service.answer_question("¿Cómo reporto un incidente?", top_k=1, rerank_top_n=1)

        self.assertTrue(result.used_fallback)
        self.assertIn("No tengo suficiente información", result.answer)

    def test_rejects_answers_without_context_support(self):
        candidates = [
            {
                "document": "El procedimiento es abrir un ticket para reportar un incidente de logística.",
                "metadata": {"source_file": "procedimiento.pdf", "area": "Logística"},
                "distance": 0.2,
            }
        ]
        service = self.make_service(candidates)
        service.generate_answer = lambda question, context, max_tokens=512, temperature=0.0: (
            "La respuesta correcta es que el sistema no tiene ningún proceso definido."
        )

        result = service.answer_question("¿Cómo reporto un incidente?", top_k=1, rerank_top_n=1)

        self.assertTrue(result.used_fallback)
        self.assertIn("No tengo suficiente información", result.answer)


if __name__ == "__main__":
    unittest.main()
