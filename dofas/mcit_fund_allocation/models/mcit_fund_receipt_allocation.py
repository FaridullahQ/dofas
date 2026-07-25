from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class McitFundReceiptAllocation(models.Model):
    """One line of a Fund Receipt's Program Allocation table: how much of
    the received amount is earmarked for a given Program, optionally
    narrowed to one of that Program's Projects under the same Grant as the
    receipt."""

    _name = "mcit.fund.receipt.allocation"
    _description = "Fund Receipt Program Allocation"
    _order = "id"

    fund_receipt_id = fields.Many2one(
        "mcit.fund.receipt", string="Fund Receipt", required=True,
        ondelete="cascade", index=True)
    receipt_state = fields.Selection(related="fund_receipt_id.state", store=True)
    grant_id = fields.Many2one(related="fund_receipt_id.grant_id", store=True)
    company_id = fields.Many2one(related="fund_receipt_id.company_id", store=True)
    currency_id = fields.Many2one(related="fund_receipt_id.currency_id", store=True)

    program_id = fields.Many2one("mcit.program", string="Program", required=True)
    project_id = fields.Many2one(
        "mcit.project", string="Project",
        domain="[('program_id', '=', program_id), ('grant_id', '=', grant_id)]",
        help="Optional. Leave blank to fund the Program generally rather "
             "than one specific Project.")
    amount = fields.Monetary(string="Amount", currency_field="currency_id", required=True)

    _sql_constraints = [
        ("amount_positive", "CHECK(amount > 0)",
         "The allocated amount must be greater than zero."),
    ]

    @api.constrains("project_id", "program_id", "grant_id")
    def _check_project_matches_program_and_grant(self):
        for line in self:
            if line.project_id and line.project_id.program_id != line.program_id:
                raise ValidationError(_(
                    "Project '%(project)s' does not belong to Program '%(program)s'.",
                    project=line.project_id.display_name, program=line.program_id.display_name))
            if line.project_id and line.grant_id and line.project_id.grant_id != line.grant_id:
                raise ValidationError(_(
                    "Project '%(project)s' belongs to a different Grant than this "
                    "receipt (%(grant)s).", project=line.project_id.display_name,
                    grant=line.grant_id.display_name))
