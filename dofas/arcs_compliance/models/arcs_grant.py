from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsGrant(models.Model):
    _inherit = "arcs.grant"

    # --- compliance indicators shown on the Compliance tab ---
    attachment_count = fields.Integer(
        string="Attached documents", compute="_compute_compliance_state")
    agreement_attached = fields.Boolean(
        string="Signed agreement attached", compute="_compute_compliance_state",
        search="_search_agreement_attached")
    donor_checklist_line_ids = fields.Many2many(
        "arcs.compliance.checklist.line", string="Donor compliance requirements",
        compute="_compute_donor_checklist",
        help="Requirements taken from the donor's active compliance checklist(s).")

    def _attachment_count(self):
        self.ensure_one()
        if not isinstance(self.id, int):
            return 0
        return self.env["ir.attachment"].search_count(
            [("res_model", "=", "arcs.grant"), ("res_id", "=", self.id)])

    def _compute_compliance_state(self):
        for g in self:
            cnt = g._attachment_count()
            g.attachment_count = cnt
            g.agreement_attached = cnt > 0

    def _search_agreement_attached(self, operator, value):
        """Makes the non-stored `agreement_attached` field usable in search
        filters/domains (e.g. the Compliance Reports 'Missing Signed
        Agreement' filter) without having to store it - it stays computed
        fresh on every read everywhere else, matching every other
        attachment-count field in this suite (mcit_fund's voucher_attached,
        mcit_request's bank_receipt_attached, etc.), all of which are
        deliberately left non-stored so they can never go stale between an
        attachment being added/removed and the field being read."""
        if operator not in ("=", "!="):
            raise UserError(_("'agreement_attached' only supports the = and != operators."))
        want_true = (operator == "=") == bool(value)
        attached_grant_ids = self.env["ir.attachment"].sudo().search([
            ("res_model", "=", "arcs.grant"), ("res_id", "!=", False),
        ]).mapped("res_id")
        attached_grant_ids = list(set(attached_grant_ids))
        if want_true:
            return [("id", "in", attached_grant_ids)]
        return [("id", "not in", attached_grant_ids)]

    @api.depends("donor_id")
    def _compute_donor_checklist(self):
        Checklist = self.env["arcs.compliance.checklist"]
        Line = self.env["arcs.compliance.checklist.line"]
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
