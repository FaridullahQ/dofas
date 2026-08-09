from odoo import fields, models


class McitAdvance(models.Model):
    _inherit = "mcit.advance"

    # Kept as a plain back-reference (not the other way around only) so both
    # directions are directly navigable: the acquisition already holds its
    # own advance_id forward-reference (see mcit_spend_request.py), and this
    # lets a Finance user land on an advance record (e.g. from the Employee
    # Advances register) and immediately see which acquisition it came from,
    # without mcit_advance itself needing to know acquisitions exist.
    spend_request_id = fields.Many2one(
        "mcit.spend.request", string="Acquisition", readonly=True, copy=False, index=True)
