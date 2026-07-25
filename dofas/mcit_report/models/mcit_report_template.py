from odoo import api, fields, models

REPORT_TYPES = [
    ("financial", "Financial"), ("narrative", "Narrative"), ("compliance", "Compliance"),
    ("asset", "Asset"), ("procurement", "Procurement"), ("variance", "Variance"),
    ("fund_utilization", "Fund Utilization"),
]


class McitReportTemplate(models.Model):
    _name = "mcit.report.template"
    _description = "Donor Report Template"
    _inherit = ["mcit.approval.mixin", "mail.thread"]
    _order = "create_date desc"

    name = fields.Char(required=True)
    donor_id = fields.Many2one("mcit.donor", string="Donor")
    report_type = fields.Selection(REPORT_TYPES, string="Report Type", required=True, default="financial")
    title = fields.Char(string="Printed Title",
                        help="Heading printed at the top of the report. Defaults to the report type.")
    header_note = fields.Text(string="Header Note",
                              help="Printed under the title (e.g. donor reference or instructions).")
    footer_note = fields.Text(string="Footer Note",
                              help="Printed at the bottom (e.g. a donor disclaimer).")
    note = fields.Text(string="Layout Notes", help="Internal notes about this donor's format.")
    # Sections the PDF will include
    show_budget = fields.Boolean(string="Budget vs Actual table", default=True)
    show_narrative = fields.Boolean(string="Narrative section", default=False)
    show_compliance = fields.Boolean(string="Compliance section", default=False)
    show_procurement = fields.Boolean(string="Commitments / Procurement", default=False)
    show_asset = fields.Boolean(string="Asset register section", default=False)
    show_fx = fields.Boolean(string="Exchange-rate disclosure", default=True)
    show_signature = fields.Boolean(string="Signature block", default=True)
    active = fields.Boolean(default=True)

    @api.onchange("report_type")
    def _onchange_report_type(self):
        t = self.report_type
        self.show_budget = t in ("financial", "variance", "fund_utilization")
        self.show_narrative = (t == "narrative")
        self.show_compliance = (t == "compliance")
        self.show_procurement = (t == "procurement")
        self.show_asset = (t == "asset")
        if not self.title:
            self.title = (dict(REPORT_TYPES).get(t, "") + " Report") if t else ""
