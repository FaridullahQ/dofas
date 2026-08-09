import hashlib

from odoo import api, fields, models


class McitRagChunk(models.Model):
    """One indexed, embeddable snippet of a DoFAS record. The actual
    'embedding' vector column is NOT declared as an Odoo field - Odoo has no
    native pgvector field type - it is added directly via SQL in
    post_init_hook() and is only ever read/written through raw SQL in
    mcit.rag.indexer / mcit.rag.query. Keeping it out of the ORM's own
    field list avoids the ORM trying to manage a column type it doesn't
    understand.
    """

    _name = "mcit.rag.chunk"
    _description = "DoFAS RAG Index Chunk"
    _rec_name = "res_name"

    res_model = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    res_name = fields.Char(help="Display name snapshot, for citations.")
    company_id = fields.Many2one("res.company", required=True, index=True)
    chunk_text = fields.Text(required=True)
    content_hash = fields.Char(
        required=True, index=True,
        help="MD5 of chunk_text - lets reindexing skip records whose "
             "summarized text hasn't actually changed, even if the record "
             "was written for an unrelated reason.")
    indexed_date = fields.Datetime(default=fields.Datetime.now)

    _sql_constraints = [
        ("res_model_id_uniq", "unique(res_model, res_id)",
         "Only one chunk is kept per source record (the record's full "
         "summary is one chunk, not split further, given DoFAS record "
         "sizes)."),
    ]

    @api.model
    def _embedding_dim(self):
        """Fixed at 384 to match the default embedding model
        (BAAI/bge-small-en-v1.5). If you switch to a model with a different
        output size, the embedding column must be altered manually - see
        README.md - a config field alone cannot safely resize a live
        pgvector column."""
        return 384

    @staticmethod
    def hash_text(text):
        return hashlib.md5((text or "").encode("utf-8")).hexdigest()
