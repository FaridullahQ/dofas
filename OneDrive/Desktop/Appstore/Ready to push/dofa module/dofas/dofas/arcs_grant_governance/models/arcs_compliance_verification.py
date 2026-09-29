from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsComplianceVerification(models.Model):
    """Turns a static checklist item into an auditable, per-transaction check
    (SRS 4.5). Records are created automatically at the trigger point the
    checklist line specifies (expense approval or report submission) so
    nothing is forgotten, then a compliance officer marks each one Passed,
    Flagged, or Waived. A Flagged item never blocks the expense or report
    that raised it - SRS 4.5 says 'flag... for review', not 'block' - but an
    unresolved Flagged item DOES block that grant's closure verification
    (see arcs.project.closure override), so nothing can be quietly ignored
    forever."""

    _name = "arcs.compliance.verification"
    _description = "Compliance Verification"
    _inherit = ["mail.thread"]
    _order = "grant_id, create_date desc"

    grant_id = fields.Many2one("arcs.grant", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="grant_id.company_id", store=True)
    checklist_line_id = fields.Many2one(
        "arcs.compliance.checklist.line", string="Requirement", required=True, ondelete="restrict")
    requirement_name = fields.Char(related="checklist_line_id.name", string="Requirement Name")
    trigger = fields.Selection(related="checklist_line_id.verification_trigger", store=True)
    source_res_model = fields.Char(string="Source Document Model")
    source_res_id = fields.Integer(string="Source Document ID")
    source_display_name = fields.Char(
        compute="_compute_source_display_name", string="Source Document")

    state = fields.Selection(
        [("pending", "Pending"), ("passed", "Passed"),
         ("flagged", "Flagged"), ("rejected", "Rejected"), ("waived", "Waived")],
        default="pending", required=True, tracking=True, copy=False)
    flagged_reason = fields.Text()
    rejected_reason = fields.Text()
    waived_reason = fields.Text()
    verified_by = fields.Many2one("res.users", readonly=True, copy=False)
    verified_date = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [
        ("source_uniq", "unique(grant_id, checklist_line_id, source_res_model, source_res_id)",
         "This requirement has already been raised for this specific document."),
    ]

    def _compute_source_display_name(self):
        for v in self:
            v.source_display_name = False
            if v.source_res_model and v.source_res_id and v.source_res_model in self.env:
                rec = self.env[v.source_res_model].browse(v.source_res_id)
                if rec.exists():
                    v.source_display_name = rec.display_name

    @api.model
    def _cleared_states(self):
        """States that count as 'resolved' for Gate-enforcement purposes. A
        Rejected item still blocks - rejecting is a verdict on the
        underlying transaction, not a resolution of the compliance item
        itself; only Passing it (compliance confirmed) or Waiving it
        (an authorized, justified override) clears a Gate."""
        return ("passed", "waived")

    def action_pass(self):
        for v in self:
            if v.state == "waived":
                raise UserError(_("A waived item cannot be re-passed; unwaive it first."))
        return self.write({
            "state": "passed", "verified_by": self.env.user.id,
            "verified_date": fields.Datetime.now(),
        })

    def action_flag(self):
        for v in self:
            if v.state == "waived":
                raise UserError(_("A waived item cannot be flagged; unwaive it first."))
            if not v.flagged_reason or not v.flagged_reason.strip():
                raise UserError(_(
                    "Enter the Flagged Reason before marking this item Flagged."))
        return self.write({
            "state": "flagged", "verified_by": self.env.user.id,
            "verified_date": fields.Datetime.now(),
        })

    def action_reject(self):
        for v in self:
            if v.state == "waived":
                raise UserError(_("A waived item cannot be rejected; unwaive it first."))
            if not v.rejected_reason or not v.rejected_reason.strip():
                raise UserError(_(
                    "Enter the Rejected Reason before marking this item Rejected."))
        return self.write({
            "state": "rejected", "verified_by": self.env.user.id,
            "verified_date": fields.Datetime.now(),
        })

    def action_waive(self):
        for v in self:
            if not v.waived_reason or not v.waived_reason.strip():
                raise UserError(_(
                    "Enter the Waived Reason before waiving this compliance requirement."))
        return self.write({
            "state": "waived", "verified_by": self.env.user.id,
            "verified_date": fields.Datetime.now(),
        })
