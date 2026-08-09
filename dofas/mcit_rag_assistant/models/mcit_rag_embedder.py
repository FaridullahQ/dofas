import logging

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Process-wide cache: {model_name: loaded SentenceTransformer instance}.
# Loading a model takes real time (disk + memory), so this must not happen
# on every call - it happens once per Odoo worker process, on first use.
_MODEL_CACHE = {}


class McitRagEmbedder(models.AbstractModel):
    _name = "mcit.rag.embedder"
    _description = "DoFAS RAG - Local Embedding Service"

    # def _get_model(self, model_name):
    #     if model_name in _MODEL_CACHE:
    #         return _MODEL_CACHE[model_name]
    #     try:
    #         from sentence_transformers import SentenceTransformer
    #     except ImportError:
    #         raise UserError(
    #             "The 'sentence-transformers' Python package isn't "
    #             "installed on this server. Ask your system administrator "
    #             "to run:\n\n"
    #             "    pip install sentence-transformers --break-system-packages\n\n"
    #             "then restart Odoo."
    #         )
    #     _logger.info("mcit_rag_assistant: loading embedding model %s "
    #                  "(first use in this worker - may take a moment)",
    #                  model_name)
    #     instance = SentenceTransformer(model_name)
    #     _MODEL_CACHE[model_name] = instance
    #     return instance

    def _get_model(self, model_name):
        if model_name in _MODEL_CACHE:
            return _MODEL_CACHE[model_name]
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise UserError(
                "The 'sentence-transformers' Python package isn't "
                "installed on this server. Ask your system administrator "
                "to run:\n\n"
                "    pip install sentence-transformers --break-system-packages\n\n"
                "then restart Odoo."
            )
        _logger.info("mcit_rag_assistant: loading embedding model %s "
                     "(first use in this worker - may take a moment)",
                     model_name)
        # Force CPU mode to avoid DLL errors
        instance = SentenceTransformer(model_name, device="cpu")
        _MODEL_CACHE[model_name] = instance
        return instance

    def embed(self, texts, model_name):
        """texts: list[str] -> list[list[float]], same order."""
        if not texts:
            return []
        model = self._get_model(model_name)
        vectors = model.encode(list(texts), normalize_embeddings=True)
        return [v.tolist() for v in vectors]

    def embed_one(self, text, model_name):
        return self.embed([text], model_name)[0]
