import logging

import requests

from odoo import models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the DoFAS assistant. Answer the question using ONLY the DoFAS "
    "record excerpts given as context below. If the answer isn't in the "
    "context, say plainly that you don't have that information in DoFAS - "
    "never guess or use outside knowledge. Be concise. When useful, mention "
    "which record(s) the answer came from by name."
)


class McitRagQuery(models.AbstractModel):
    _name = "mcit.rag.query"
    _description = "DoFAS RAG - Ask DoFAS Query Service"

    def ask(self, question):
        company = self.env.company
        if not company.mcit_rag_enabled:
            raise UserError(
                "The Ask DoFAS assistant is turned off for this company "
                "(Settings > General Settings > Ask DoFAS).")
        question = (question or "").strip()
        if not question:
            raise UserError("Please type a question.")

        embed_model = company.mcit_rag_embedding_model or "BAAI/bge-small-en-v1.5"
        q_vector = self.env["mcit.rag.embedder"].embed_one(question, embed_model)

        top_k = company.mcit_rag_top_k or 5
        overfetch = max(top_k * 4, 20)

        try:
            self.env.cr.execute(
                "SELECT res_model, res_id, res_name, chunk_text, "
                "embedding <=> %s::vector AS distance "
                "FROM mcit_rag_chunk WHERE company_id = %s "
                "AND embedding IS NOT NULL "
                "ORDER BY distance ASC LIMIT %s",
                (str(q_vector), company.id, overfetch),
            )
        except Exception:
            self.env.cr.rollback()
            raise UserError(
                "The DoFAS search index isn't ready yet. This usually means "
                "the pgvector extension wasn't enabled during install - ask "
                "your DBA to run 'CREATE EXTENSION vector;' on the database "
                "(see README.md), then reindex from Settings > Technical > "
                "Ask DoFAS > Reindex All."
            )
        candidates = self.env.cr.dictfetchall()

        # CRITICAL: re-check each candidate under the ASKING user's own
        # access rights and record rules (donor scoping included). The
        # index itself covers every donor; an individual user must never
        # see context pulled from a record they couldn't open directly.
        accessible = []
        for row in candidates:
            if len(accessible) >= top_k:
                break
            if row["res_model"] not in self.env:
                continue
            record = self.env[row["res_model"]].browse(row["res_id"])
            try:
                record.check_access_rights("read")
                record.check_access_rule("read")
            except AccessError:
                continue
            if not record.exists():
                continue
            accessible.append(row)

        if not accessible:
            return {
                "answer": "I couldn't find anything in DoFAS you have access "
                          "to that's relevant to that question.",
                "sources": [],
            }

        context_block = "\n\n---\n\n".join(
            "[%s #%s] %s\n%s" % (r["res_model"], r["res_id"], r["res_name"], r["chunk_text"])
            for r in accessible
        )
        answer = self._generate(company, question, context_block)
        sources = [
            {"model": r["res_model"], "res_id": r["res_id"], "name": r["res_name"]}
            for r in accessible
        ]
        return {"answer": answer, "sources": sources}

    def _generate(self, company, question, context_block):
        url = (company.mcit_rag_ollama_url or "http://localhost:11434").rstrip("/") + "/api/chat"
        model = company.mcit_rag_ollama_model or "llama3.1:8b"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Context:\n%s\n\nQuestion: %s" % (context_block, question)},
            ],
            "stream": False,
        }
        try:
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            _logger.error("mcit_rag_assistant: Ollama call failed: %s", e)
            raise UserError(
                "Could not reach the Ollama server at %s. Make sure Ollama "
                "is running there and the model has been pulled "
                "(run: ollama pull %s)." % (company.mcit_rag_ollama_url, model)
            )
        data = resp.json()
        content = (data.get("message") or {}).get("content", "").strip()
        return content or "The model returned an empty answer."
