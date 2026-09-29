from odoo import api, models


class ArcsCommitment(models.Model):
    _inherit = "arcs.commitment"

    @api.model
    def _selection_source(self):
        res = super()._selection_source()
        if "purchase.order" in self.env:
            res.append(("purchase.order", self.env["purchase.order"]._description))
        return res
