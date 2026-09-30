from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsGrant(models.Model):
    _inherit = "arcs.grant"

    agreement_ids = fields.One2many(
        "arcs.grant.agreement", "grant_id", string="Agreement Versions")
    current_agreement_id = fields.Many2one(
        "arcs.grant.agreement", compute="_compute_current_agreement", store=True,
        string="Active Agreement Version")
    agreement_version_count = fields.Integer(compute="_compute_current_agreement")

    release_schedule_ids = fields.One2many(
        "arcs.grant.release.schedule.line", "grant_id", string="Fund Release Schedule")
    release_schedule_planned_total = fields.Monetary(
        compute="_compute_release_schedule_totals", currency_field="currency_id")
    release_schedule_received_total = fields.Monetary(
        compute="_compute_release_schedule_totals", currency_field="currency_id")
    release_schedule_overdue_count = fields.Integer(compute="_compute_release_schedule_totals")

    compliance_verification_ids = fields.One2many(
        "arcs.compliance.verification", "grant_id", string="Compliance Verifications")
    compliance_unresolved_count = fields.Integer(compute="_compute_compliance_counts",
        help="Flagged or Rejected items - neither is cleared for closure "
             "purposes; only Passed or Waived items are.")
    compliance_pending_count = fields.Integer(compute="_compute_compliance_counts")

    donor_suggestion = fields.Text(
        string="Donor Suggestion", help="A non-binding suggestion from the donor on how "
                                        "funds might be used - informational only, ARCS "
                                        "is not bound by it (relevant mainly to "
                                        "Unrestricted donations).")

    @api.depends("agreement_ids.state")
    def _compute_current_agreement(self):
        for g in self:
            active = g.agreement_ids.filtered(lambda a: a.state == "active")
            g.current_agreement_id = active[:1]
            g.agreement_version_count = len(g.agreement_ids)

    def _compute_release_schedule_totals(self):
        for g in self:
            lines = g.release_schedule_ids
            g.release_schedule_planned_total = sum(lines.mapped("planned_amount"))
            g.release_schedule_received_total = sum(lines.mapped("received_amount"))
            g.release_schedule_overdue_count = len(
                lines.filtered(lambda l: l.status == "overdue"))

    def _compute_compliance_counts(self):
        for g in self:
            verifs = g.compliance_verification_ids
            g.compliance_unresolved_count = len(
                verifs.filtered(lambda v: v.state in ("flagged", "rejected")))
            g.compliance_pending_count = len(verifs.filtered(lambda v: v.state == "pending"))

    def action_view_agreements(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Agreement Versions"),
            "res_model": "arcs.grant.agreement", "view_mode": "tree,form",
            "domain": [("grant_id", "=", self.id)],
            "context": {"default_grant_id": self.id},
        }

    def action_view_compliance_verifications(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Compliance Verifications"),
            "res_model": "arcs.compliance.verification", "view_mode": "tree,form",
            "domain": [("grant_id", "=", self.id)],
        }

    # ---------------------------------------------------- governance helper
    def _governance_create_verifications(self, trigger, source_record):
        """Raise a pending arcs.compliance.verification for every checklist
        requirement (donor-specific OR general/company-wide) whose Auto-Raise
        trigger matches, for this specific expense or donor-report record -
        unless one already exists for that exact (grant, requirement,
        document) combination. Applies to every grant, restricted or not:
        checklist applicability was always donor/requirement-driven, not
        restriction-driven (an Unrestricted grant is still bound by ARCS's
        own general checklist, per the Unrestricted Donation Workflow SRS)."""
        self.ensure_one()
        lines = self.donor_checklist_line_ids.filtered(
            lambda l: l.verification_trigger == trigger)
        if not lines:
            return
        existing = self.env["arcs.compliance.verification"].search([
            ("grant_id", "=", self.id), ("checklist_line_id", "in", lines.ids),
            ("source_res_model", "=", source_record._name),
            ("source_res_id", "=", source_record.id),
        ]).mapped("checklist_line_id")
        to_create = [{
            "grant_id": self.id, "checklist_line_id": line.id,
            "source_res_model": source_record._name, "source_res_id": source_record.id,
        } for line in lines if line not in existing]
        if to_create:
            self.env["arcs.compliance.verification"].create(to_create)

    def _governance_check_gate(self, trigger, source_record):
        """Raise a UserError naming any unresolved Gate-type requirement
        raised against this specific source record at the given trigger.
        Called at the step AFTER the one that raised the verification
        (expense Approval, following Submit's expense_approval trigger;
        report Review, following Submit's report_submission trigger) -
        never at the same moment the item is raised, since blocking
        immediately would roll back the very verification record a
        reviewer needs to see and act on."""
        self.ensure_one()
        Verification = self.env["arcs.compliance.verification"]
        unresolved = Verification.search([
            ("grant_id", "=", self.id), ("trigger", "=", trigger),
            ("source_res_model", "=", source_record._name),
            ("source_res_id", "=", source_record.id),
            ("checklist_line_id.enforcement", "=", "gate"),
            ("state", "not in", list(Verification._cleared_states())),
        ])
        if unresolved:
            names = ", ".join(unresolved.mapped("requirement_name"))
            raise UserError(_(
                "Cannot proceed: the following mandatory compliance "
                "requirement(s) are not yet resolved for grant '%(g)s': "
                "%(names)s. Go to Compliance Reviews and Pass or Waive them "
                "first.", g=self.display_name, names=names))

    # -------------------------------------------- stricter approval gate
    def action_approve(self):
        for g in self:
            if g.state == "review" and g.is_restricted and not g.current_agreement_id:
                raise UserError(_(
                    "Grant '%s' is restricted: activate a signed Agreement Version "
                    "(Compliance tab) before approving it - a loose attachment is "
                    "not enough.") % g.display_name)
        return super().action_approve()
