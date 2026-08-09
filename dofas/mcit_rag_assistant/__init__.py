import logging

from . import models

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Best-effort: enable pgvector and add the embedding column + ANN index
    on the chunk table. If the DB role lacks CREATE EXTENSION rights, or
    pgvector isn't compiled in at all, this logs a clear, actionable
    warning instead of failing the install - the module still installs,
    but indexing/querying will raise a friendly UserError until pgvector is
    available and 'CREATE EXTENSION vector;' has been run manually.

    IMPORTANT: the failed CREATE EXTENSION is wrapped in its own savepoint.
    A bare cr.rollback() here would roll back the *entire* install
    transaction - including the columns and table this module's own
    _auto_init already created earlier in the same transaction - leaving
    the ORM's in-memory registry out of sync with the database and causing
    an UndefinedColumn error on the very next query.
    """
    cr = env.cr
    try:
        with cr.savepoint():
            cr.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception:
        _logger.warning(
            "mcit_rag_assistant: could not enable the pgvector extension "
            "(either insufficient database privileges, or pgvector isn't "
            "installed on this PostgreSQL server at all - the latter is "
            "common on Windows). See README.md for how to install it. "
            "Once available, ask your DBA to run, once, as a Postgres "
            "superuser:\n"
            "    CREATE EXTENSION vector;\n"
            "on the DoFAS database, then run this module's 'Reindex All "
            "Now' from Settings > General Settings > Ask DoFAS. The "
            "module is installed, but indexing and the Ask DoFAS "
            "assistant will not work until that command has been run."
        )
        return

    dim = env["mcit.rag.chunk"]._embedding_dim()
    cr.execute(
        "ALTER TABLE mcit_rag_chunk ADD COLUMN IF NOT EXISTS "
        "embedding vector(%s)" % dim
    )
    cr.execute(
        "CREATE INDEX IF NOT EXISTS mcit_rag_chunk_embedding_idx "
        "ON mcit_rag_chunk USING hnsw (embedding vector_cosine_ops)"
    )
