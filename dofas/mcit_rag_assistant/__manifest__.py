{
    "name": "MCIT Donor Mgmt - RAG Assistant",
    "version": "17.0.1.0.0",
    "category": "Accounting/MCIT Donor Management",
    "summary": "Local, fully open-source retrieval-augmented Q&A over DoFAS "
               "records (Grants, Budgets, Compliance, Reports, Advances, "
               "Fund Receipts, Programs, Donors) - no external API keys.",
    "description": """
DoFAS RAG Assistant
====================
Adds an "Ask DoFAS" chat assistant that answers questions grounded in your
own DoFAS data.

Stack (fully free / open, self-hosted - no per-call API cost):
  - Embeddings: sentence-transformers (BAAI/bge-small-en-v1.5 by default),
    running locally inside the Odoo Python process.
  - Vector search: PostgreSQL pgvector extension.
  - Answer generation: Ollama, self-hosted, serving an open model
    (llama3.1:8b by default).

Prerequisites (one-time server setup - NOT installed by this module,
see README.md packaged with the zip):
  1. pip install sentence-transformers --break-system-packages
  2. Install Ollama and run: ollama pull llama3.1:8b
  3. A database role that can run CREATE EXTENSION vector (the module
     attempts this automatically on install and tells you the exact
     command if it can't).

Security: every answer is grounded only in records the ASKING user can
actually read under Odoo's own access rights and record rules (donor
scoping included) - retrieval never leaks another donor's data through
the AI context, even though the underlying index covers everything.
""",
    "author": "MCIT",
    "depends": [
        "mcit_donor", "mcit_grant", "mcit_budget", "mcit_fund",
        "mcit_compliance", "mcit_report", "mcit_advance", "mcit_program",
    ],
    "external_dependencies": {
        "python": ["sentence_transformers", "requests"],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/res_config_settings_views.xml",
        "views/mcit_rag_chunk_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mcit_rag_assistant/static/src/scss/rag_chat.scss",
            "mcit_rag_assistant/static/src/js/rag_chat.js",
            "mcit_rag_assistant/static/src/xml/rag_chat.xml",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
