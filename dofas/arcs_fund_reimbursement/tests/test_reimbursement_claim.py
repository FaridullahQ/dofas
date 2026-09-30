import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsReimbursementClaim(TransactionCase):
    """Full lifecycle: compiling -> submit -> donor validation (approve or
    reject+resubmit) -> fund receipt -> final report -> reported. Also
    covers reused infrastructure (the agreement gate and compliance gate
    from arcs_grant_governance) and confirms arcs_advance and other
    funding models are completely unaffected."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.plan = cls.env["account.analytic.plan"].create({"name": "ARCS Grants REIMB"})
        cls.company.arcs_default_analytic_plan_id = cls.plan
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme REIMB", "code": "ARCSRB600", "account_type": "expense"})
        cls.clearing = cls.env["account.account"].create(
            {"name": "Clearing REIMB", "code": "ARCSRB200", "account_type": "liability_current"})
        cls.exp_journal = cls.env["account.journal"].create(
            {"name": "ARCS REIMB", "type": "general", "code": "ARCSRBX", "company_id": cls.company.id})
        cls.company.arcs_expense_journal_id = cls.exp_journal
        cls.company.arcs_expense_clearing_account_id = cls.clearing
        cls.bank_journal = cls.env["account.journal"].create(
            {"name": "ARCS REIMB Bank", "type": "bank", "code": "ARCSRBB", "company_id": cls.company.id})
        cls.income_acc = cls.env["account.account"].create(
            {"name": "Donor Income REIMB", "code": "ARCSRB100", "account_type": "asset_cash"})

        cls.donor = cls.env["arcs.donor"].create(
            {"name": "USAID", "code": "USAID-RB", "donor_type": "government"})

    def _grant(self, funding_model="reimbursement"):
        return self.env["arcs.grant"].create({
            "name": "Health REIMB", "grant_number": "GR-RB-%s" % funding_model,
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

    def _activate_grant(self, grant):
        """A Reimbursement grant is is_restricted, so it needs an active
        Agreement Version (from arcs_grant_governance) before it can be
        approved - reused, not rebuilt."""
        self._budget_line(grant)
        agr = self.env["arcs.grant.agreement"].create({
            "grant_id": grant.id, "signed_date": "2026-01-01"})
        self._attachment("arcs.grant.agreement", agr.id)
        agr.action_activate()
        grant.action_submit()
        self._attachment("arcs.grant", grant.id)
        grant.action_approve()
        grant.action_activate()

    def _expense(self, grant, line, claim, amount):
        return self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": amount, "date": "2026-01-15",
            "reimbursement_claim_id": claim.id,
        })

    # ------------------------------------------------------------------ tests
    def test_full_claim_lifecycle(self):
        grant = self._grant()
        self._activate_grant(grant)
        line = self.env["arcs.budget.line"].search([("budget_id.grant_id", "=", grant.id)], limit=1)

        claim = self.env["arcs.reimbursement.claim"].create({"grant_id": grant.id})
        self.assertTrue(claim.name.startswith("RC-"))
        self.assertEqual(claim.state, "compiling")

        exp = self._expense(grant, line, claim, 400.0)
        with self.assertRaises(UserError):
            claim.action_submit()  # expense not yet approved/posted
        exp.action_submit()
        exp.action_approve()
        claim.invalidate_recordset()
        self.assertAlmostEqual(claim.claimed_amount, 400.0)

        with self.assertRaises(UserError):
            claim.action_submit()  # no proof attachment yet
        self._attachment("arcs.reimbursement.claim", claim.id)
        claim.action_submit()
        self.assertEqual(claim.state, "submitted")

        claim.action_validate_approve()
        self.assertEqual(claim.state, "approved")

        receipt_action = claim.action_open_fund_receipt()
        self.assertEqual(receipt_action["context"]["default_amount"], 400.0)
        receipt = self.env["arcs.fund.receipt"].create({
            "grant_id": grant.id, "currency_id": self.company.currency_id.id,
            "amount": 400.0, "received_date": "2026-02-01",
            "bank_voucher_ref": "VCH-RB-1", "journal_id": self.bank_journal.id,
            "receivable_account_id": self.income_acc.id,
            "reimbursement_claim_id": claim.id,
        })
        self._attachment("arcs.fund.receipt", receipt.id)
        receipt.action_post()
        self.assertEqual(claim.state, "funded")

        report = self.env["arcs.donor.report"].create({
            "grant_id": grant.id, "report_type": "financial",
            "reimbursement_claim_id": claim.id,
        })
        self._attachment("arcs.donor.report", report.id)
        report.action_submit()
        report.action_review()
        report.action_approve()
        self.assertEqual(claim.state, "reported")
        self.assertEqual(claim.donor_report_id, report)

    def test_rejection_and_resubmission(self):
        grant = self._grant()
        self._activate_grant(grant)
        line = self.env["arcs.budget.line"].search([("budget_id.grant_id", "=", grant.id)], limit=1)
        claim = self.env["arcs.reimbursement.claim"].create({"grant_id": grant.id})
        exp = self._expense(grant, line, claim, 250.0)
        exp.action_submit(); exp.action_approve()
        self._attachment("arcs.reimbursement.claim", claim.id)
        claim.action_submit()

        with self.assertRaises(UserError):
            claim.action_validate_reject()  # no reason entered yet
        claim.validation_notes = "Missing original invoice for line item 2"
        claim.action_validate_reject()
        self.assertEqual(claim.state, "rejected")

        claim.action_resubmit()
        self.assertEqual(claim.state, "compiling")
        claim.action_submit()  # same expenses, proof still attached
        self.assertEqual(claim.state, "submitted")

    def test_expense_requires_claim_on_reimbursement_grant(self):
        grant = self._grant()
        self._activate_grant(grant)
        line = self.env["arcs.budget.line"].search([("budget_id.grant_id", "=", grant.id)], limit=1)
        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": 100.0, "date": "2026-01-15"})
        with self.assertRaises(UserError):
            exp.action_submit()

    def test_compliance_gate_blocks_validation_approval(self):
        checklist = self.env["arcs.compliance.checklist"].create(
            {"name": "USAID Reimbursement Requirements", "donor_id": self.donor.id})
        gate_line = self.env["arcs.compliance.checklist.line"].create({
            "checklist_id": checklist.id, "name": "Original invoices verified",
            "verification_trigger": "reimbursement_claim_submission", "enforcement": "gate",
        })
        grant = self._grant()
        self._activate_grant(grant)
        line = self.env["arcs.budget.line"].search([("budget_id.grant_id", "=", grant.id)], limit=1)
        claim = self.env["arcs.reimbursement.claim"].create({"grant_id": grant.id})
        exp = self._expense(grant, line, claim, 300.0)
        exp.action_submit(); exp.action_approve()
        self._attachment("arcs.reimbursement.claim", claim.id)
        claim.action_submit()  # raising the gate item must not itself be blocked

        with self.assertRaises(UserError):
            claim.action_validate_approve()
        self.assertEqual(claim.state, "submitted")

        verif = self.env["arcs.compliance.verification"].search([
            ("grant_id", "=", grant.id), ("checklist_line_id", "=", gate_line.id)])
        verif.action_pass()
        claim.action_validate_approve()
        self.assertEqual(claim.state, "approved")

    def test_closure_blocked_while_claim_open(self):
        grant = self._grant()
        self._activate_grant(grant)
        line = self.env["arcs.budget.line"].search([("budget_id.grant_id", "=", grant.id)], limit=1)
        self.env["arcs.reimbursement.claim"].create({"grant_id": grant.id})
        with self.assertRaises(UserError):
            grant.action_close()

    def test_cancel_blocked_once_expenses_linked(self):
        grant = self._grant()
        self._activate_grant(grant)
        line = self.env["arcs.budget.line"].search([("budget_id.grant_id", "=", grant.id)], limit=1)
        claim = self.env["arcs.reimbursement.claim"].create({"grant_id": grant.id})
        exp = self._expense(grant, line, claim, 150.0)
        exp.action_submit(); exp.action_approve()
        with self.assertRaises(UserError):
            claim.action_cancel()

    def test_other_funding_models_unaffected(self):
        grant2 = self.env["arcs.grant"].create({
            "name": "Health GB2", "grant_number": "GR-RB-GB", "donor_id": self.donor.id,
            "currency_id": self.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 1000.0})
        line = self._budget_line(grant2)
        agr = self.env["arcs.grant.agreement"].create({
            "grant_id": grant2.id, "signed_date": "2026-01-01"})
        self._attachment("arcs.grant.agreement", agr.id)
        agr.action_activate()
        grant2.action_submit()
        self._attachment("arcs.grant", grant2.id)
        grant2.action_approve(); grant2.action_activate()

        exp = self.env["arcs.expense"].create({
            "grant_id": grant2.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": 100.0, "date": "2026-01-15"})
        exp.action_submit()  # must NOT require a reimbursement_claim_id
        exp.action_approve()
        self.assertEqual(exp.state, "approved")
        grant2.action_close()  # must NOT be blocked by the reimbursement hook
        self.assertEqual(grant2.state, "closed")

    def test_arcs_advance_unaffected(self):
        """Smoke test: the pre-existing internal-advance mechanism this
        module deliberately does NOT touch still works exactly as before,
        independent of any reimbursement claim."""
        zone = self.env["arcs.zone"].create({"name": "Kabul Zone REIMB"})
        adv_journal = self.env["account.journal"].create(
            {"name": "ARCS Advance", "type": "general", "code": "ARCSADV", "company_id": self.company.id})
        adv_acc = self.env["account.account"].create(
            {"name": "Advance Receivable", "code": "ARCSADV1", "account_type": "asset_receivable"})
        payable_acc = self.env["account.account"].create(
            {"name": "Advance Payable", "code": "ARCSADV2", "account_type": "liability_current"})
        cash_acc = self.env["account.account"].create(
            {"name": "Advance Cash", "code": "ARCSADV3", "account_type": "asset_cash"})
        self.company.write({
            "arcs_advance_journal_id": adv_journal.id,
            "arcs_advance_account_id": adv_acc.id,
            "arcs_advance_payable_account_id": payable_acc.id,
            "arcs_advance_cash_account_id": cash_acc.id,
        })
        advance = self.env["arcs.advance"].create({
            "advance_type": "zone", "zone_id": zone.id, "amount": 500.0,
            "date": "2026-01-05",
        })
        advance.action_lock()
        self.assertEqual(advance.state, "locked")
        advance.action_issue()
        self.assertEqual(advance.state, "issued")
