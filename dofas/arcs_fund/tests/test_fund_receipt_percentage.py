from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsFundReceiptPercentage(TransactionCase):
    """% of Grant and Amount stay in sync both ways: typing a percentage
    calculates Amount from the Grant's Approved Amount, and typing an
    Amount directly instead keeps the percentage showing what it actually
    represents."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-PCT", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-PCT-1", "donor_id": cls.donor.id,
            "currency_id": cls.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 40000.0})
        cls.other_grant = cls.env["arcs.grant"].create({
            "name": "Other", "grant_number": "GR-PCT-2", "donor_id": cls.donor.id,
            "currency_id": cls.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 10000.0})

    def test_entering_percentage_calculates_amount(self):
        form = Form(self.env["arcs.fund.receipt"])
        form.grant_id = self.grant
        form.amount_percentage = 0.25  # 25%
        self.assertEqual(form.amount, 10000.0)

    def test_entering_amount_calculates_percentage(self):
        form = Form(self.env["arcs.fund.receipt"])
        form.grant_id = self.grant
        form.amount = 20000.0
        self.assertAlmostEqual(form.amount_percentage, 0.5, places=4)

    def test_switching_grant_recalculates_amount_from_existing_percentage(self):
        form = Form(self.env["arcs.fund.receipt"])
        form.grant_id = self.grant
        form.amount_percentage = 0.1  # 10% of 40,000 = 4,000
        self.assertEqual(form.amount, 4000.0)

        form.grant_id = self.other_grant  # 10% of 10,000 = 1,000
        self.assertEqual(form.amount, 1000.0)

    def test_percentage_left_at_zero_does_not_override_a_typed_amount(self):
        """Picking a grant without ever touching % of Grant must not zero
        out an amount the user is in the middle of typing by hand."""
        form = Form(self.env["arcs.fund.receipt"])
        form.grant_id = self.grant
        form.amount = 15000.0
        self.assertEqual(form.amount, 15000.0)
        self.assertAlmostEqual(form.amount_percentage, 0.375, places=4)

    def test_round_trip_does_not_drift_or_loop(self):
        """Setting percentage -> amount recalculates percentage back from
        that amount - and the two must land on the same value, not drift
        or bounce indefinitely between the two onchange handlers."""
        form = Form(self.env["arcs.fund.receipt"])
        form.grant_id = self.grant
        form.amount_percentage = 0.3333
        receipt = form.save()
        self.assertAlmostEqual(receipt.amount_percentage, 0.3333, places=4)
        self.assertAlmostEqual(receipt.amount, 40000.0 * 0.3333, places=2)
