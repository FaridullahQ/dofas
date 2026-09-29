from odoo import fields, models


class ArcsExpense(models.Model):
    _inherit = "arcs.expense"

    shared_cost_id = fields.Many2one(
        "arcs.multi.donor.shared.cost", string="Multi-Donor Shared Cost",
        readonly=True, copy=False,
        help="If this expense was generated from a Multi-Donor shared cost "
             "split, this is that record - purely informational, for "
             "traceability back to the original shared cost and its other "
             "donors' shares.")
