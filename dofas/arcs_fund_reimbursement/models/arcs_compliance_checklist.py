from odoo import fields, models


class ArcsComplianceChecklistLine(models.Model):
    _inherit = "arcs.compliance.checklist.line"

    verification_trigger = fields.Selection(
        selection_add=[("reimbursement_claim_submission", "On Reimbursement Claim Submission")],
        ondelete={"reimbursement_claim_submission": "set default"},
    )
