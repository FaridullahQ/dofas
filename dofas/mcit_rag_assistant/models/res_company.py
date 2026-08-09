from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    mcit_rag_enabled = fields.Boolean(
        string="Enable Ask DoFAS Assistant", default=True)
    mcit_rag_ollama_url = fields.Char(
        string="Ollama Base URL", default="http://localhost:11434",
        help="Base URL of your self-hosted Ollama server. Must be reachable "
             "from the Odoo server itself.")
    mcit_rag_ollama_model = fields.Char(
        string="Ollama Chat Model", default="llama3.1:8b",
        help="Any open model you've pulled with 'ollama pull <model>', e.g. "
             "llama3.1:8b, qwen2.5:7b, mistral:7b.")
    mcit_rag_embedding_model = fields.Char(
        string="Embedding Model", default="BAAI/bge-small-en-v1.5",
        help="A sentence-transformers model id from Hugging Face. Changing "
             "this after records are already indexed requires a full "
             "reindex (Settings > Technical > Ask DoFAS > Reindex All), and "
             "if the new model's vector size differs from 384 dimensions "
             "the embedding column must be altered manually first - see "
             "README.md.")
    mcit_rag_top_k = fields.Integer(
        string="Chunks Retrieved per Question", default=5,
        help="How many of the most relevant record snippets are given to "
             "the model as context for each question.")
