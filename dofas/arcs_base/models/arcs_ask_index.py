from odoo import fields, models


class ArcsAskIndex(models.TransientModel):
    """Placeholder for a planned natural-language search/assistant feature
    ('Ask DoFAS') that would let a user ask a question in plain language
    (e.g. 'how much is left on the Health grant?') and get an answer drawn
    from live data across the suite. Nothing about the retrieval/indexing
    engine, data sources, or scope has been specified yet, so this page
    intentionally does not simulate functionality that doesn't exist -
    it explains what's planned and links to where configuration would live
    once it is built, instead of a broken or misleading feature."""

    _name = "arcs.ask.index"
    _description = "Ask DoFAS Index (Planned)"

    note = fields.Text(
        readonly=True,
        default=lambda s: (
            "Ask DoFAS is planned: a natural-language search assistant over this "
            "suite's data (grants, budgets, acquisitions, advances, reports), "
            "answering questions like 'how much is left on the Health grant?' "
            "directly from live records.\n\n"
            "This screen is a placeholder only - the indexing engine, data "
            "sources, and access scope have not been specified yet. No search "
            "or Q&A functionality exists here. Once specified, this menu will "
            "host the indexing/configuration screen for that feature."
        ),
    )
