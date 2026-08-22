from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    arcs_enforce_program_ceilings = fields.Boolean(
        related="company_id.arcs_enforce_program_ceilings", readonly=False)
