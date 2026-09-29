from odoo import fields, models


class ArcsDonor(models.Model):
    _inherit = "arcs.donor"

    grant_ids = fields.One2many("arcs.grant", "donor_id", string="Grants")
    grant_count = fields.Integer(compute="_compute_grant_count")

    def _compute_grant_count(self):
        data = self.env["arcs.grant"]._read_group(
            [("donor_id", "in", self.ids)], ["donor_id"], ["__count"])
        mapping = {donor.id: count for donor, count in data}
        for d in self:
            d.grant_count = mapping.get(d.id, 0)
