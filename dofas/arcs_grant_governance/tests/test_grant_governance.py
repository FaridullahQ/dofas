import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsGrantGovernance(TransactionCase):
    """Covers agreement version control, the fund release schedule, the
    auto-raised compliance verification workflow (flag-not-block, but
    blocking at closure if unresolved), and the donor-feedback-gated
    closure - plus a regression check that an Unrestricted grant sees none
    of this."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.plan = cls.env["account.analytic.plan"].create({"name": "ARCS Grants GOV"})
        cls.company.arcs_default_analytic_plan_id = cls.plan
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme GOV", "code": "ARCSGV600", "account_type": "expense"})
        cls.clearing = cls.env["account.account"].create(
            {"name": "Clearing GOV", "code": "ARCSGV200", "account_type": "liability_current"})
        cls.exp_journal = cls.env["account.journal"].create(
            {"name": "ARCS GOV", "type": "general", "code": "ARCSGVX", "company_id": cls.company.id})
        cls.company.arcs_expense_journal_id = cls.exp_journal
        cls.company.arcs_expense_clearing_account_id = cls.clearing
        cls.bank_journal = cls.env["account.journal"].create(
            {"name": "ARCS GOV Bank", "type": "bank", "code": "ARCSGVB", "company_id": cls.company.id})
        cls.income_acc = cls.env["account.account"].create(
            {"name": "Donor Income GOV", "code": "ARCSGV100", "account_type": "asset_cash"})

        cls.donor = cls.env["arcs.donor"].create(
            {"name": "ECHO", "code": "ECHO-GOV", "donor_type": "government"})

        # A checklist with both auto-raise triggers, so we can exercise both.
        cls.checklist = cls.env["arcs.compliance.checklist"].create({
            "name": "ECHO Standard Requirements", "donor_id": cls.donor.id,
        })
        cls.line_expense = cls.env["arcs.compliance.checklist.line"].create({
            "checklist_id": cls.checklist.id, "name": "Receipt attached for expenses over 500",
            "verification_trigger": "expense_approval",
        })
        cls.line_report = cls.env["arcs.compliance.checklist.line"].create({
            "checklist_id": cls.checklist.id, "name": "Narrative section completed",
            "verification_trigger": "report_submission",
        })
        cls.line_manual = cls.env["arcs.compliance.checklist.line"].create({
            "checklist_id": cls.checklist.id, "name": "General donor policy on file",
            "verification_trigger": "manual",
        })

    def _grant(self, funding_model="grant_based"):
        return self.env["arcs.grant"].create({
            "name": "Health GOV", "grant_number": "GR-GOV-%s" % funding_model,
            "donor_id": self.donor.id, "currency_id": self.company.currency_id.id,
            "funding_model": funding_model, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "approved_amount": 1000.0})

    def _budget_line(self, grant):
        budget = self.env["arcs.budget"].create({"grant_id": grant.id})
        line = self.env["arcs.budget.line"].create({
            "budget_id": budget.id, "name": "Activities",
            "account_ids": [(6, 0, self.exp_acc.ids)], "planned_amount": 1000.0})
        budget.action_approve()
        return line

    def _attachment(self, res_model, res_id):
        return self.env["ir.attachment"].create({
            "name": "doc.pdf", "datas": base64.b64encode(b"dummy"),
            "res_model": res_model, "res_id": res_id,
        })

    def _agreement(self, grant, signed=True, attach=True):
        agr = self.env["arcs.grant.agreement"].create({
            "grant_id": grant.id, "signed_date": "2026-01-01" if signed else False,
        })
        if attach:
            self._attachment("arcs.grant.agreement", agr.id)
        return agr

    def _submit_grant(self, grant):
        grant.action_submit()

    # ------------------------------------------------------------------ tests
    def test_restricted_grant_requires_active_agreement_to_approve(self):
        grant = self._grant("grant_based")
        self._budget_line(grant)
        self._submit_grant(grant)
        self._attachment("arcs.grant", grant.id)  # satisfies arcs_compliance's own generic gate
        with self.assertRaises(UserError):
            grant.action_approve()

        agr = self._agreement(grant)
        agr.action_activate()
        self.assertEqual(agr.state, "active")
        grant.action_approve()
        self.assertEqual(grant.state, "approved")
        self.assertEqual(grant.current_agreement_id, agr)

    def test_agreement_activation_supersedes_previous_version(self):
        grant = self._grant("grant_based")
        agr1 = self._agreement(grant)
        agr1.action_activate()
        agr2 = self._agreement(grant)
        agr2.action_activate()
        self.assertEqual(agr1.state, "superseded")
        self.assertEqual(agr2.state, "active")
        self.assertEqual(grant.current_agreement_id, agr2)
        self.assertEqual(agr2.version, 2)

    def test_release_schedule_status_transitions(self):
        grant = self._grant("grant_based")
        line = self.env["arcs.grant.release.schedule.line"].create({
            "grant_id": grant.id, "planned_date": "2020-01-01", "planned_amount": 500.0,
        })
        self.assertEqual(line.status, "overdue")  # past date, nothing received yet

        receipt = self.env["arcs.fund.receipt"].create({
            "grant_id": grant.id, "currency_id": self.company.currency_id.id,
            "amount": 500.0, "received_date": "2026-01-10",
            "bank_voucher_ref": "VCH-GOV-1", "journal_id": self.bank_journal.id,
            "receivable_account_id": self.income_acc.id,
        })
        self._attachment("arcs.fund.receipt", receipt.id)
        receipt.action_post()
        line.fund_receipt_id = receipt.id
        self.assertEqual(line.status, "received")
        self.assertEqual(line.received_amount, 500.0)

    def test_compliance_verification_raised_on_expense_submit_flags_not_blocks(self):
        grant = self._grant("grant_based")
        line = self._budget_line(grant)
        agr = self._agreement(grant); agr.action_activate()
        self._submit_grant(grant)
        self._attachment("arcs.grant", grant.id)
        grant.action_approve(); grant.action_activate()

        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": 600.0, "date": "2026-01-15"})
        exp.action_submit()  # must NOT raise, even though a compliance item is now open
        self.assertEqual(exp.state, "submitted")

        verif = self.env["arcs.compliance.verification"].search([
            ("grant_id", "=", grant.id), ("checklist_line_id", "=", self.line_expense.id),
            ("source_res_model", "=", "arcs.expense"), ("source_res_id", "=", exp.id)])
        self.assertEqual(len(verif), 1)
        self.assertEqual(verif.state, "pending")

        # Approving the expense is completely unaffected by the open verification.
        exp.action_approve()
        self.assertEqual(exp.state, "approved")

        # Flagging it, then trying to verify closure, must block.
        verif.flagged_reason = "Missing receipt copy"
        verif.action_flag()
        self.assertEqual(verif.state, "flagged")
        closure = self.env["arcs.project.closure"].create({"grant_id": grant.id})
        with self.assertRaises(UserError):
            closure.action_verify()

        # Waiving it (with a reason) unblocks closure verification.
        verif.waived_reason = "Receipt on file at field office, confirmed by phone"
        verif.action_waive()
        self.assertEqual(verif.state, "waived")
        closure.action_verify()  # no longer blocked by the (now-resolved) item
        self.assertEqual(closure.state, "verified")

    def test_donor_feedback_gates_closure_approval(self):
        grant = self._grant("grant_based")
        line = self._budget_line(grant)
        agr = self._agreement(grant); agr.action_activate()
        self._submit_grant(grant)
        self._attachment("arcs.grant", grant.id)
        grant.action_approve(); grant.action_activate()

        report = self.env["arcs.donor.report"].create({
            "grant_id": grant.id, "report_type": "financial"})
        self._attachment("arcs.donor.report", report.id)
        report.action_submit()  # also raises the report_submission verification, unblocked
        report.action_review()
        report.action_approve()

        closure = self.env["arcs.project.closure"].create({"grant_id": grant.id})
        closure.action_verify()

        with self.assertRaises(UserError):
            closure.action_approve()  # no final_report_id yet

        closure.final_report_id = report.id
        with self.assertRaises(UserError):
            closure.action_approve()  # donor_feedback_state still 'pending'

        report.donor_feedback_state = "approved"
        closure.action_approve()
        self.assertEqual(closure.state, "approved")
        self.assertEqual(grant.state, "closed")

    def test_unrestricted_grant_skips_restricted_gates_but_still_gets_compliance(self):
        """Agreement version control, the release schedule, and donor-feedback
        -gated closure remain is_restricted-only and are correctly skipped.
        But compliance verification is now universal (checklist
        applicability was always donor-driven, never restriction-driven) -
        so an Unrestricted grant from a donor who HAS a checklist (ECHO,
        here) still gets that checklist enforced, per the Unrestricted
        Donation Workflow SRS ('ARCS compliance checklist is mandatory')."""
        grant = self._grant("unrestricted")
        line = self._budget_line(grant)
        self.assertFalse(grant.is_restricted)
        self._submit_grant(grant)
        self._attachment("arcs.grant", grant.id)
        grant.action_approve()  # no agreement version required - is_restricted is False
        grant.action_activate()

        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": 600.0, "date": "2026-01-15"})
        exp.action_submit()
        verif = self.env["arcs.compliance.verification"].search([
            ("grant_id", "=", grant.id), ("checklist_line_id", "=", self.line_expense.id)])
        self.assertEqual(len(verif), 1)  # ECHO's checklist still applies - restriction-independent
        exp.action_approve()  # Advisory by default - never blocks
        self.assertEqual(exp.state, "approved")

        report = self.env["arcs.donor.report"].create({
            "grant_id": grant.id, "report_type": "financial"})
        self._attachment("arcs.donor.report", report.id)
        report.action_submit(); report.action_review(); report.action_approve()

        closure = self.env["arcs.project.closure"].create({"grant_id": grant.id})
        closure.action_verify()
        closure.action_approve()  # no final_report_id / donor feedback required - is_restricted-only
        self.assertEqual(closure.state, "approved")

    def test_general_checklist_applies_regardless_of_donor(self):
        """A general (donor_id=False) checklist's lines apply to every grant,
        even one from a donor with no checklist of their own - this is the
        core fix that makes 'ARCS's own standard checklist' a real, working
        concept rather than dead data-model intent."""
        bare_donor = self.env["arcs.donor"].create(
            {"name": "Anonymous Individual", "code": "ANON-GOV", "donor_type": "individual"})
        general = self.env["arcs.compliance.checklist"].create({"name": "ARCS Baseline"})
        general_line = self.env["arcs.compliance.checklist.line"].create({
            "checklist_id": general.id, "name": "Standard receipt policy",
            "verification_trigger": "expense_approval",
        })
        grant = self.env["arcs.grant"].create({
            "name": "Unrestricted Gift", "grant_number": "GR-GOV-ANON",
            "donor_id": bare_donor.id, "currency_id": self.company.currency_id.id,
            "funding_model": "unrestricted", "date_start": "2026-01-01",
            "date_end": "2026-12-31", "approved_amount": 1000.0})
        self.assertIn(general_line, grant.donor_checklist_line_ids)

        line = self._budget_line(grant)
        self._submit_grant(grant)
        self._attachment("arcs.grant", grant.id)
        grant.action_approve(); grant.action_activate()
        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": 200.0, "date": "2026-01-15"})
        exp.action_submit()
        self.assertTrue(self.env["arcs.compliance.verification"].search([
            ("grant_id", "=", grant.id), ("checklist_line_id", "=", general_line.id)]))

    def test_gate_enforcement_blocks_expense_approval_until_resolved(self):
        """A checklist line with enforcement='gate' must block approval of
        the exact expense it was raised against, until Passed or Waived -
        but never blocks any OTHER expense, and never blocks at submit time
        (which would roll back the very record a reviewer needs to act on)."""
        donor = self.env["arcs.donor"].create(
            {"name": "Gate Donor", "code": "GATE-GOV", "donor_type": "foundation"})
        checklist = self.env["arcs.compliance.checklist"].create(
            {"name": "Gate Donor Requirements", "donor_id": donor.id})
        gate_line = self.env["arcs.compliance.checklist.line"].create({
            "checklist_id": checklist.id, "name": "Mandatory pre-spend sign-off",
            "verification_trigger": "expense_approval", "enforcement": "gate",
        })
        grant = self.env["arcs.grant"].create({
            "name": "Gated Grant", "grant_number": "GR-GOV-GATE", "donor_id": donor.id,
            "currency_id": self.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 1000.0})
        line = self._budget_line(grant)
        agr = self._agreement(grant); agr.action_activate()
        self._submit_grant(grant)
        self._attachment("arcs.grant", grant.id)
        grant.action_approve(); grant.action_activate()

        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": 300.0, "date": "2026-01-15"})
        exp.action_submit()  # raising the Gate item must not itself be blocked
        with self.assertRaises(UserError):
            exp.action_approve()  # the Gate item is still Pending
        self.assertEqual(exp.state, "submitted")  # approval genuinely did not proceed

        verif = self.env["arcs.compliance.verification"].search([
            ("grant_id", "=", grant.id), ("checklist_line_id", "=", gate_line.id)])
        verif.action_pass()
        exp.action_approve()  # now clears - the gate is satisfied
        self.assertEqual(exp.state, "approved")

    def test_gate_enforcement_blocks_report_review_until_resolved(self):
        donor = self.env["arcs.donor"].create(
            {"name": "Gate Donor 2", "code": "GATE-GOV-2", "donor_type": "foundation"})
        checklist = self.env["arcs.compliance.checklist"].create(
            {"name": "Gate Donor 2 Requirements", "donor_id": donor.id})
        self.env["arcs.compliance.checklist.line"].create({
            "checklist_id": checklist.id, "name": "Narrative must be pre-cleared",
            "verification_trigger": "report_submission", "enforcement": "gate",
        })
        grant = self.env["arcs.grant"].create({
            "name": "Gated Report Grant", "grant_number": "GR-GOV-GATE2", "donor_id": donor.id,
            "currency_id": self.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 1000.0})
        self._budget_line(grant)
        agr = self._agreement(grant); agr.action_activate()
        self._submit_grant(grant)
        self._attachment("arcs.grant", grant.id)
        grant.action_approve(); grant.action_activate()

        report = self.env["arcs.donor.report"].create({
            "grant_id": grant.id, "report_type": "financial"})
        self._attachment("arcs.donor.report", report.id)
        report.action_submit()
        with self.assertRaises(UserError):
            report.action_review()
        self.assertEqual(report.state, "submitted")

        verif = self.env["arcs.compliance.verification"].search([("grant_id", "=", grant.id)])
        verif.waived_reason = "Pre-cleared verbally, documentation to follow"
        verif.action_waive()
        report.action_review()
        self.assertEqual(report.state, "reviewed")

    def test_rejected_state_blocks_closure_like_flagged(self):
        grant = self._grant("grant_based")
        line = self._budget_line(grant)
        agr = self._agreement(grant); agr.action_activate()
        self._submit_grant(grant)
        self._attachment("arcs.grant", grant.id)
        grant.action_approve(); grant.action_activate()

        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": 600.0, "date": "2026-01-15"})
        exp.action_submit()
        exp.action_approve()
        verif = self.env["arcs.compliance.verification"].search([
            ("grant_id", "=", grant.id), ("checklist_line_id", "=", self.line_expense.id),
            ("source_res_id", "=", exp.id)])
        verif.rejected_reason = "Receipt does not match the amount claimed"
        verif.action_reject()
        self.assertEqual(grant.compliance_unresolved_count, 1)

        closure = self.env["arcs.project.closure"].create({"grant_id": grant.id})
        with self.assertRaises(UserError):
            closure.action_verify()

        verif.action_pass()  # reversing the verdict after further review
        self.assertEqual(grant.compliance_unresolved_count, 0)
        closure.action_verify()
        self.assertEqual(closure.state, "verified")
