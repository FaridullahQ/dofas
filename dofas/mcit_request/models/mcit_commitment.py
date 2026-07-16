from odoo import api, models


class McitCommitment(models.Model):
    _inherit = "mcit.commitment"

    @api.model
    def _selection_source(self):
        """Allow a spend request to be the source document of a reserve."""
        res = super()._selection_source()
        names = [m for m, _ in res]
        if "mcit.spend.request" not in names and "mcit.spend.request" in self.env:
            res.append(("mcit.spend.request", self.env["mcit.spend.request"]._description))
        return res
