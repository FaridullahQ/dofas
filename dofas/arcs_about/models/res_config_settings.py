from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    group_arcs_show_about = fields.Boolean(
        string="Show the About & Help menu",
        implied_group="arcs_about.group_arcs_about",
        help="When enabled, an 'About & Help' menu (company info, the overall "
             "process flow and a glossary of terms) is shown to all users.")
