from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class ArcsFundReceipt(models.Model):
    _inherit = "arcs.fund.receipt"

    allocation_ids = fields.One2many(
        "arcs.fund.receipt.allocation", "fund_receipt_id",
        string="Program Allocation")
    allocated_amount = fields.Monetary(
        string="Allocated", currency_field="currency_id",
        compute="_compute_allocation_totals", store=True)
    unallocated_amount = fields.Monetary(
        string="Unallocated", currency_field="currency_id",
        compute="_compute_allocation_totals", store=True)
    is_fully_allocated = fields.Boolean(
        string="Fully Allocated", compute="_compute_allocation_totals", store=True)

    @api.depends("amount", "allocation_ids.amount")
    def _compute_allocation_totals(self):
        for r in self:
            allocated = sum(r.allocation_ids.mapped("amount"))
            r.allocated_amount = allocated
            r.unallocated_amount = (r.amount or 0.0) - allocated
            precision = r.currency_id.rounding if r.currency_id else 0.01
            r.is_fully_allocated = float_compare(
                allocated, r.amount or 0.0, precision_rounding=precision) == 0

    @api.constrains("amount", "allocation_ids.amount")
    def _check_allocation_not_over_amount(self):
        for r in self:
            if not r.allocation_ids:
                continue
            allocated = sum(r.allocation_ids.mapped("amount"))
            precision = r.currency_id.rounding if r.currency_id else 0.01
            if float_compare(allocated, r.amount or 0.0, precision_rounding=precision) > 0:
                raise ValidationError(_(
                    "The Program Allocation total (%(allocated)s) cannot exceed the "
                    "receipt amount (%(amount)s).",
                    allocated=allocated, amount=r.amount))

    # ---------------- donor acknowledgement email: allocation section ----------------
    def _allocation_email_html(self):
        """HTML fragment listing the Program Allocation, for splicing into the
        donor acknowledgement email body. Empty string if nothing to show."""
        self.ensure_one()
        if not self.allocation_ids:
            return ""
        rows = []
        for line in self.allocation_ids:
            label = line.program_id.display_name
            if line.project_id:
                label = "%s &#8212; %s" % (label, line.project_id.display_name)
            amount = "{:,.2f} {}".format(line.amount or 0.0, self.currency_id.name or "")
            rows.append(
                "<tr>"
                "<td style=\"padding:4px 8px;border-bottom:1px solid #e0e0e0;\">%s</td>"
                "<td style=\"padding:4px 8px;border-bottom:1px solid #e0e0e0;text-align:right;\">%s</td>"
                "</tr>" % (label, amount)
            )
        return (
            "<p>%s</p>"
            "<table style=\"width:100%%;border-collapse:collapse;font-size:13px;margin:8px 0;\">"
            "%s"
            "</table>"
        ) % (_("Your contribution is being directed to the following programs:"), "".join(rows))
