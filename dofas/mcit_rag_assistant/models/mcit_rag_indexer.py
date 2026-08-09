import re

from odoo import api, fields, models

_SKIP_FIELDS = {
    "id", "display_name", "create_uid", "create_date", "write_uid",
    "write_date", "__last_update", "activity_ids", "message_ids",
    "message_follower_ids", "message_main_attachment_id",
    "message_partner_ids", "message_channel_ids", "access_url",
    "access_token", "access_warning",
}
_TAG_RE = re.compile(r"<[^>]+>")


class McitRagIndexer(models.AbstractModel):
    _name = "mcit.rag.indexer"
    _description = "DoFAS RAG - Indexing Service"

    @api.model
    def _get_indexable_models(self):
        """Curated allow-list of structured DoFAS models the assistant may
        search over. Deliberately excludes technical/wizard/log models."""
        return [
            ("mcit.donor", "Donor"),
            ("mcit.grant", "Grant"),
            ("mcit.budget", "Budget"),
            ("mcit.budget.line", "Budget Line"),
            ("mcit.compliance.checklist", "Compliance Checklist"),
            ("mcit.donor.report", "Donor Report"),
            ("mcit.department.report", "Department Report"),
            ("mcit.fund.receipt", "Fund Receipt"),
            ("mcit.advance", "Advance"),
            ("mcit.program", "Program"),
            ("mcit.project", "Project"),
        ]

    def _build_text(self, record):
        """Generic field-driven summary: works for any model without a
        hand-written builder per model, and stays correct automatically as
        fields are added or changed."""
        parts = [f"{record._description or record._name}: {record.display_name}"]
        for fname, field in record._fields.items():
            if fname in _SKIP_FIELDS or fname.startswith("_"):
                continue
            try:
                value = record[fname]
            except Exception:
                continue
            if not value:
                continue
            label = field.string or fname
            if field.type in ("char", "text"):
                parts.append(f"{label}: {value}")
            elif field.type == "html":
                parts.append(f"{label}: {_TAG_RE.sub(' ', value).strip()}")
            elif field.type in ("monetary", "integer", "float"):
                parts.append(f"{label}: {value}")
            elif field.type == "many2one":
                parts.append(f"{label}: {value.display_name}")
            elif field.type == "selection":
                selection = field.selection
                if callable(selection):
                    selection = selection(record)
                parts.append(f"{label}: {dict(selection).get(value, value)}")
            elif field.type in ("date", "datetime"):
                parts.append(f"{label}: {value}")
        return "\n".join(parts)

    def reindex_record(self, model_name, res_id):
        Chunk = self.env["mcit.rag.chunk"].sudo()
        record = self.env[model_name].sudo().browse(res_id)
        if not record.exists():
            Chunk.search([
                ("res_model", "=", model_name), ("res_id", "=", res_id),
            ]).unlink()
            return False

        text = self._build_text(record)
        content_hash = Chunk.hash_text(text)
        existing = Chunk.search([
            ("res_model", "=", model_name), ("res_id", "=", res_id),
        ], limit=1)
        if existing and existing.content_hash == content_hash:
            return False  # unchanged - skip the (comparatively expensive) embedding call

        company = getattr(record, "company_id", False) or self.env.company
        vals = {
            "res_model": model_name,
            "res_id": res_id,
            "res_name": record.display_name,
            "company_id": company.id,
            "chunk_text": text,
            "content_hash": content_hash,
            "indexed_date": fields.Datetime.now(),
        }
        chunk = existing or Chunk.create(vals)
        if existing:
            existing.write(vals)

        embed_model = company.mcit_rag_embedding_model or "BAAI/bge-small-en-v1.5"
        vector = self.env["mcit.rag.embedder"].embed_one(text, embed_model)
        self.env.cr.execute(
            "UPDATE mcit_rag_chunk SET embedding = %s::vector WHERE id = %s",
            (str(vector), chunk.id),
        )
        return True

    def reindex_all(self, model_names=None):
        targets = model_names or [m for m, _ in self._get_indexable_models()]
        count = 0
        for model_name in targets:
            if model_name not in self.env:
                continue
            records = self.env[model_name].sudo().with_context(
                active_test=False).search([])
            for record in records:
                if self.reindex_record(model_name, record.id):
                    count += 1
        return count

    def _cron_reindex_changed(self, batch_limit=200):
        """Incremental pass: (re)index only records that changed since they
        were last embedded, plus a light orphan cleanup. Batch-limited so a
        single cron tick never runs unboundedly long."""
        Chunk = self.env["mcit.rag.chunk"].sudo()
        processed = 0
        for model_name, _label in self._get_indexable_models():
            if processed >= batch_limit or model_name not in self.env:
                continue
            records = self.env[model_name].sudo().with_context(
                active_test=False).search([])
            existing_chunks = {
                c.res_id: c for c in Chunk.search([("res_model", "=", model_name)])
            }
            live_ids = set()
            for record in records:
                live_ids.add(record.id)
                if processed >= batch_limit:
                    break
                chunk = existing_chunks.get(record.id)
                if chunk and record.write_date and chunk.indexed_date \
                        and record.write_date <= chunk.indexed_date:
                    continue
                if self.reindex_record(model_name, record.id):
                    processed += 1
            # orphan cleanup: chunks whose source record no longer exists
            stale_ids = set(existing_chunks) - live_ids
            if stale_ids:
                Chunk.search([
                    ("res_model", "=", model_name),
                    ("res_id", "in", list(stale_ids)),
                ]).unlink()
        return processed
