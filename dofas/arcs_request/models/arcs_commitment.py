from odoo import api, fields, models


class ArcsCommitment(models.Model):
    _inherit = "arcs.commitment"

    # Kept alongside `source_ref` (which stays the generic, module-agnostic
    # pointer used for display/search across all commitment sources) rather
    # than replacing it: a real Many2one lets arcs.spend.request expose a
    # clean `commitment_ids` One2many (multiple reserves per acquisition,
    # one per budget line, when the amount was split) without arcs.commitment
    # having to parse `source_ref` back out. ondelete=cascade because a
    # commitment tied to a request has no independent meaning once the
    # request itself is deleted (drafts only - real requests are
    # cancelled/rejected, not deleted).
    spend_request_id = fields.Many2one(
        "arcs.spend.request", string="Acquisition", ondelete="cascade",
        index=True, copy=False)

    @api.model
    def _selection_source(self):
        """Allow a spend request to be the source document of a reserve."""
        res = super()._selection_source()
        names = [m for m, _ in res]
        if "arcs.spend.request" not in names and "arcs.spend.request" in self.env:
            res.append(("arcs.spend.request", self.env["arcs.spend.request"]._description))
        return res
