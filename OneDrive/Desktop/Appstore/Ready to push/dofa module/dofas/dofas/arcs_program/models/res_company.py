from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    arcs_enforce_program_ceilings = fields.Boolean(
        string="Enforce Program/Project/Activity Ceilings", default=False,
        help="When enabled, Commit & Reserve on an acquisition linked to an Activity also "
             "checks that Activity's (and its Project's and Program's) own Planned Cost "
             "ceiling, not just the Budget Line - and blocks with the same Insufficient "
             "Funds recovery options if it's short. Off by default: existing Activities "
             "with no Planned Cost set (0 by default) would otherwise block every "
             "acquisition linked to them the moment this ships. Turn this on once your "
             "Program/Project/Activity Planned Cost figures are actually filled in.")
