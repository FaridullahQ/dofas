from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ArcsGrantReleaseScheduleLine(models.Model):
    """A planned donor installment (SRS 4.2: 'Capture donor approved budget
    lines and fund release schedule'). Purely a forecasting/tracking layer -
    it never gates or alters how arcs.fund.receipt posts; Finance links the
    actual receipt once it arrives so Pending/Received/Overdue status is
    visible without touching the accounting flow at all."""

    _name = "arcs.grant.release.schedule.line"
    _description = "Grant Fund Release Schedule Line"
    _order = "grant_id, sequence, id"

    grant_id = fields.Many2one("arcs.grant", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="grant_id.company_id", store=True)
    currency_id = fields.Many2one(related="grant_id.currency_id", store=True)
    sequence = fields.Integer(default=10)
    installment_no = fields.Integer(string="Installment #", readonly=True, copy=False)
    planned_date = fields.Date(string="Planned Date", required=True)
    planned_amount = fields.Monetary(
        string="Planned Amount", currency_field="currency_id", required=True)
    notes = fields.Char()
    fund_receipt_id = fields.Many2one(
        "arcs.fund.receipt", string="Matched Receipt", copy=False,
        domain="[('grant_id', '=', grant_id)]",
        help="Link the actual fund receipt once this installment arrives.")
    received_amount = fields.Monetary(
        compute="_compute_received", store=True, currency_field="currency_id")
    status = fields.Selection(
        [("pending", "Pending"), ("received", "Received"), ("overdue", "Overdue")],
        compute="_compute_received", store=True)

    _sql_constraints = [
        ("planned_amount_positive", "CHECK(planned_amount > 0)",
         "The planned amount must be greater than zero."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("grant_id") and not vals.get("installment_no"):
                vals["installment_no"] = self.search_count(
                    [("grant_id", "=", vals["grant_id"])]) + 1
        return super().create(vals_list)

    @api.constrains("fund_receipt_id")
    def _check_receipt_same_grant(self):
        for line in self.filtered("fund_receipt_id"):
            if line.fund_receipt_id.grant_id != line.grant_id:
                raise ValidationError(_(
                    "The matched receipt must belong to the same grant as this "
                    "release schedule line."))

    @api.depends("fund_receipt_id.amount", "fund_receipt_id.state", "planned_date")
    def _compute_received(self):
        today = fields.Date.context_today(self)
        for line in self:
            received = (line.fund_receipt_id.amount
                       if line.fund_receipt_id and line.fund_receipt_id.state == "posted"
                       else 0.0)
            line.received_amount = received
            if received:
                line.status = "received"
            elif line.planned_date and line.planned_date < today:
                line.status = "overdue"
            else:
                line.status = "pending"
