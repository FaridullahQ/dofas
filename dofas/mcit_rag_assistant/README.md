# DoFAS RAG Assistant — Setup

This module gives you an "Ask DoFAS" chat assistant that answers questions
grounded in your own Grant, Budget, Compliance, Report, Advance, and Fund
Receipt records. Everything runs on infrastructure you own — no external
API keys, no per-question cost.

Because it's fully self-hosted, three things need to be done **once** on
the server before it works. None of these can be bundled inside an Odoo
module zip — they're server-level setup, not Odoo data.

## 1. Python dependency (embeddings)

```bash
pip install sentence-transformers --break-system-packages
```

The first time the module actually embeds something, it will download the
default model (`BAAI/bge-small-en-v1.5`, ~130MB) from Hugging Face. That
needs outbound internet access once; after that it's cached locally and
runs fully offline.

## 2. Ollama (answer generation)

Install Ollama (https://ollama.com) on the server that will run it — this
can be the Odoo server itself or another machine on the same network — then
pull a model:

```bash
ollama pull llama3.1:8b
```

Other good open options: `qwen2.5:7b`, `mistral:7b`. Bigger models answer
better but need more RAM; 8B-class models are a reasonable default on a
machine with 16GB+ RAM.

If Ollama runs on a different host than Odoo, update **Settings > General
Settings > Ask DoFAS > Ollama Base URL** accordingly (default assumes
`http://localhost:11434`).

## 3. pgvector (search index storage)

The module tries to run `CREATE EXTENSION vector;` automatically on
install. If it can't - either due to privileges, or because pgvector isn't
compiled into your PostgreSQL server at all - installation still succeeds,
but indexing and querying will raise a clear error until it's resolved.

**On Linux**, this is usually just:
```bash
sudo apt install postgresql-16-pgvector   # match your PostgreSQL version
```
then, once, as a Postgres superuser on the DoFAS database:
```sql
CREATE EXTENSION vector;
```

**On Windows**, pgvector is not bundled with the standard EnterpriseDB
installer, and "extension is not available" means the extension files
genuinely aren't present yet - a permission grant alone won't fix it.
Two options:

- **Prebuilt binaries**: search for a prebuilt `pgvector` Windows release
  matching your exact PostgreSQL major version (check with
  `SELECT version();` in psql). Community-maintained Windows builds exist
  on GitHub; drop the resulting `vector.dll` into your PostgreSQL `lib`
  folder and the `vector.control` / `vector--*.sql` files into `share/extension`,
  then restart PostgreSQL and run `CREATE EXTENSION vector;`.
- **Build from source**: requires Visual Studio Build Tools (the C++
  workload) and the PostgreSQL dev headers; see the "Windows" section of
  https://github.com/pgvector/pgvector for the exact `nmake` steps.

If neither is practical in your environment right now, this module can
also run on a pure-Python cosine-similarity fallback that needs no
PostgreSQL extension at all - slower once you have many thousands of
indexed records, but zero extra infrastructure. Ask for that build if you'd
rather not fight a Windows C-extension build right now.

## After setup

1. Install `mcit_rag_assistant` from Apps.
2. Go to **Settings > General Settings > Ask DoFAS** and confirm the
   defaults, or point at a different Ollama host/model.
3. Click **Reindex All Now** to build the initial search index over your
   existing records. After that, a background job keeps it current every
   15 minutes automatically.
4. Open **Dashboards > Ask DoFAS** and start asking questions.

## What gets indexed

Donor, Grant, Budget, Budget Line, Compliance Checklist, Donor Report,
Department Report, Fund Receipt, Advance, Program, and Project — the
structured records, not file attachments.

## Security note

Every answer is filtered through the asking user's own Odoo access rights
and record rules before it reaches the AI model — including donor scoping.
A Donor Officer scoped to one donor will never get an answer grounded in
another donor's data, even though the underlying index covers every donor.
