from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsGrantAgreement(models.Model):
    """A signed version of a grant's agreement/MoU (SRS 4.1: 'Store signed
    agreements with version control and reference ID'). Only one version per
    grant is ever Active; activating a new one automatically supersedes
    whichever was active before, so there is always a single, unambiguous
    answer to 'what are we currently bound by'."""

    _name = "arcs.grant.agreement"
    _description = "Grant Agreement Version"
    _inherit = ["mail.thread"]
    _order = "grant_id, version desc"

    grant_id = fields.Many2one("arcs.grant", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="grant_id.company_id", store=True)
    version = fields.Integer(readonly=True, copy=False)
    reference = fields.Char(
        string="Reference", help="The signed agreement's own reference, e.g. an "
                                 "addendum number. Defaults to the grant's Agreement Number.")
    signed_date = fields.Date(string="Signed Date")
    effective_date = fields.Date(string="Effective Date")
    notes = fields.Text(string="Notes")
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("superseded", "Superseded")],
        default="draft", required=True, tracking=True, copy=False)
    attachment_count = fields.Integer(compute="_compute_attachment_count")

    _sql_constraints = [
        ("version_uniq", "unique(grant_id, version)",
         "Agreement versions must be numbered uniquely per grant."),
    ]

    def _compute_attachment_count(self):
        for a in self:
            a.attachment_count = self.env["ir.attachment"].search_count(
                [("res_model", "=", "arcs.grant.agreement"), ("res_id", "=", a.id)])

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("grant_id") and not vals.get("version"):
                vals["version"] = self.search_count(
                    [("grant_id", "=", vals["grant_id"])]) + 1
            if vals.get("grant_id") and not vals.get("reference"):
                grant = self.env["arcs.grant"].browse(vals["grant_id"])
                vals["reference"] = grant.agreement_number or False
        return super().create(vals_list)

    def action_activate(self):
        for a in self:
            if a.state != "draft":
                raise UserError(_("Only a draft agreement version can be activated."))
            if not a.signed_date:
                raise UserError(_("Enter the Signed Date before activating this version."))
            if not a.attachment_count:
                raise UserError(_(
                    "Attach the signed document before activating this agreement version."))
            others = self.search([
                ("grant_id", "=", a.grant_id.id), ("state", "=", "active"),
                ("id", "!=", a.id)])
            others.write({"state": "superseded"})
            a.write({"state": "active"})
        return True

    def action_reset_draft(self):
        for a in self:
            if a.state == "active":
                raise UserError(_(
                    "Activate a replacement version first - don't leave the grant "
                    "with no active agreement."))
            a.write({"state": "draft"})
        return True
