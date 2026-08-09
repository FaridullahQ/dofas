from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mcit_rag_enabled = fields.Boolean(
        related="company_id.mcit_rag_enabled", readonly=False)
    mcit_rag_ollama_url = fields.Char(
        related="company_id.mcit_rag_ollama_url", readonly=False)
    mcit_rag_ollama_model = fields.Char(
        related="company_id.mcit_rag_ollama_model", readonly=False)
    mcit_rag_embedding_model = fields.Char(
        related="company_id.mcit_rag_embedding_model", readonly=False)
    mcit_rag_top_k = fields.Integer(
        related="company_id.mcit_rag_top_k", readonly=False)

    def action_mcit_rag_reindex_all(self):
        count = self.env["mcit.rag.indexer"].reindex_all()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "DoFAS RAG Reindex",
                "message": "%s record(s) (re)indexed." % count,
                "type": "success",
                "sticky": False,
            },
        }
