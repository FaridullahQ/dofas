from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    mcit_donor_ids = fields.Many2many(
        "mcit.donor", "mcit_res_users_donor_rel", "user_id", "donor_id",
        string="Managed Donors",
        help="Donor(s) this user can access when scoped by the Donor Officer "
             "role (Grants, Budgets, Compliance, Reporting, Advances, Fund "
             "Receipts for these donors only). Leave empty to grant no donor "
             "access at all under that role. Ignored for System "
             "Administrators, who always see every donor.")
