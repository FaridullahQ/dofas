from odoo import _, api, fields, models
from odoo.exceptions import UserError


class McitGrant(models.Model):
    _inherit = "mcit.grant"

    # --- compliance indicators shown on the Compliance tab ---
    attachment_count = fields.Integer(
        string="Attached documents", compute="_compute_compliance_state")
    agreement_attached = fields.Boolean(
        string="Signed agreement attached", compute="_compute_compliance_state")
    donor_checklist_line_ids = fields.Many2many(
        "mcit.compliance.checklist.line", string="Donor compliance requirements",
        compute="_compute_donor_checklist",
        help="Requirements taken from the donor's active compliance checklist(s).")

    def _attachment_count(self):
        self.ensure_one()
        if not isinstance(self.id, int):
            return 0
        return self.env["ir.attachment"].search_count(
            [("res_model", "=", "mcit.grant"), ("res_id", "=", self.id)])

    def _compute_compliance_state(self):
        for g in self:
            cnt = g._attachment_count()
            g.attachment_count = cnt
            g.agreement_attached = cnt > 0

    @api.depends("donor_id")
    def _compute_donor_checklist(self):
        Checklist = self.env["mcit.compliance.checklist"]
        Line = self.env["mcit.compliance.checklist.line"]
        for g in self:
            lines = Line
            if g.donor_id:
                lists = Checklist.sudo().search(
                    [("donor_id", "=", g.donor_id.id), ("active", "=", True)])
                lines = lists.line_ids
            g.donor_checklist_line_ids = lines

    def action_approve(self):
        # Gate: a signed agreement attachment is required before approval.
        for g in self:
            if g.state == "review" and not g._attachment_count():
                raise UserError(_(
                    "Attach the signed agreement before approving grant '%s'.", g.name))
        return super().action_approve()
