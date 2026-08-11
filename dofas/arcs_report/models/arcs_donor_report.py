from datetime import timedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsDonorReport(models.Model):
    _name = "arcs.donor.report"
    _description = "Donor Report"
    _inherit = ["arcs.approval.mixin", "mail.thread"]
    _order = "due_date, id"

    name = fields.Char(required=True, default=lambda s: _("New"), copy=False)
    grant_id = fields.Many2one("arcs.grant", required=True)
    donor_id = fields.Many2one(related="grant_id.donor_id", store=True)
    company_id = fields.Many2one(related="grant_id.company_id", store=True)
    currency_id = fields.Many2one(related="grant_id.currency_id", store=True)
    report_type = fields.Selection(
        [("financial", "Financial"), ("narrative", "Narrative"), ("compliance", "Compliance"),
         ("asset", "Asset"), ("procurement", "Procurement"), ("variance", "Variance"),
         ("fund_utilization", "Fund Utilization")], string="Report Type",
        required=True, default="financial")
    template_id = fields.Many2one("arcs.report.template", string="Template")
    period = fields.Char(string="Reporting Period")
    due_date = fields.Date(string="Due Date")
    is_overdue = fields.Boolean(compute="_compute_overdue", store=True)
    total_actual = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    date_report = fields.Date(default=fields.Date.context_today)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("reviewed", "Reviewed"),
         ("approved", "Approved")], default="draft", required=True, tracking=True, copy=False)

    @api.depends("due_date", "state")
    def _compute_overdue(self):
        today = fields.Date.context_today(self)
        for r in self:
            r.is_overdue = bool(r.due_date and r.due_date < today and r.state != "approved")

    def _compute_totals(self):
        AAL = self.env["account.analytic.line"]
        for r in self:
            total = 0.0
            if r.grant_id.analytic_account_id:
                rows = AAL._read_group(
                    [("account_id", "=", r.grant_id.analytic_account_id.id)], [], ["amount:sum"])
                total = -(rows[0][0] if rows and rows[0][0] else 0.0)
            r.total_actual = total

    @api.onchange("grant_id", "report_type")
    def _onchange_pick_template(self):
        """Auto-select the donor's template that matches the report type."""
        donor = self.grant_id.donor_id
        if not self.report_type:
            return
        Tmpl = self.env["arcs.report.template"]
        tmpl = (Tmpl.search([("report_type", "=", self.report_type),
                             ("donor_id", "=", donor.id)], limit=1)
                or Tmpl.search([("report_type", "=", self.report_type),
                                ("donor_id", "=", False)], limit=1))
        if tmpl:
            self.template_id = tmpl.id

    def _require_financial_narrative(self):
        for r in self:
            count = self.env["ir.attachment"].search_count(
                [("res_model", "=", "arcs.donor.report"), ("res_id", "=", r.id)])
            if count < 1:
                raise UserError(_(
                    "Attach the financial and narrative reports before submitting."))

    def action_submit(self):
        self._require_financial_narrative()
        return self._transition("submitted", "submit")

    def action_review(self):
        return self._transition("reviewed", "review")

    def action_approve(self):
        return self._transition("approved", "approve")

    @api.model
    def _cron_flag_overdue(self):
        self.search([("state", "!=", "approved"),
                     ("due_date", "<", fields.Date.context_today(self))])._compute_overdue()

    # ----------------------------------------------------------------- #
    #  Report rendering helpers (consumed by the QWeb donor report)      #
    # ----------------------------------------------------------------- #
    def report_flags(self):
        self.ensure_one()
        t = self.template_id
        if t:
            return {"budget": t.show_budget, "narrative": t.show_narrative,
                    "compliance": t.show_compliance, "procurement": t.show_procurement,
                    "asset": t.show_asset, "fx": t.show_fx, "signature": t.show_signature}
        rt = self.report_type
        return {"budget": rt in ("financial", "variance", "fund_utilization"),
                "narrative": rt == "narrative", "compliance": rt == "compliance",
                "procurement": rt == "procurement", "asset": rt == "asset",
                "fx": True, "signature": True}

    def report_title(self):
        self.ensure_one()
        if self.template_id and self.template_id.title:
            return self.template_id.title
        return dict(self._fields["report_type"].selection).get(self.report_type, "Donor") + " Report"

    def report_header_note(self):
        return self.template_id.header_note if self.template_id else False

    def report_footer_note(self):
        return self.template_id.footer_note if self.template_id else False

    def report_fx_info(self):
        self.ensure_one()
        comp = self.company_id or self.env.company
        policy = ""
        if "arcs_currency_rate_policy" in comp._fields:
            policy = dict(comp._fields["arcs_currency_rate_policy"].selection).get(
                comp.arcs_currency_rate_policy, comp.arcs_currency_rate_policy or "")
        gc = self.currency_id.name or ""
        cc = comp.currency_id.name or ""
        if gc and cc and gc != cc:
            return _("Grant currency %s; functional currency %s. Conversion policy: %s.") % (
                gc, cc, policy or _("transaction date"))
        return _("Currency: %s.") % (gc or cc)

    def report_budget_rows(self):
        self.ensure_one()
        Line = self.env["arcs.budget.line"]
        sel = dict(Line._fields["category"].selection) if "category" in Line._fields else {}
        rows = []
        for g in Line.read_group(
                [("grant_id", "=", self.grant_id.id)],
                ["planned_amount:sum", "committed_amount:sum",
                 "actual_amount:sum", "available_amount:sum"], ["category"]):
            planned = g.get("planned_amount") or 0.0
            committed = g.get("committed_amount") or 0.0
            actual = g.get("actual_amount") or 0.0
            available = g.get("available_amount") or 0.0
            util = (100.0 * (committed + actual) / planned) if planned else 0.0
            rows.append({"category": sel.get(g.get("category"), "Uncategorised"),
                         "planned": planned, "committed": committed, "actual": actual,
                         "available": available, "utilization": util})
        return rows

    def report_budget_totals(self):
        tot = {"planned": 0.0, "committed": 0.0, "actual": 0.0, "available": 0.0}
        for r in self.report_budget_rows():
            for k in tot:
                tot[k] += r[k]
        tot["utilization"] = (100.0 * (tot["committed"] + tot["actual"]) / tot["planned"]) if tot["planned"] else 0.0
        tot["approved"] = self.grant_id.approved_amount or 0.0
        return tot

    def report_narrative(self):
        self.ensure_one()
        out = []
        for d in self.env["arcs.department.report"].search([("grant_id", "=", self.grant_id.id)]):
            out.append({"period": d.period or "", "achievements": d.achievements or "",
                        "challenges": d.challenges or "", "lessons": d.lessons_learned or "",
                        "outputs": d.outputs or "", "outcomes": d.outcomes or ""})
        return out

    def report_compliance(self):
        self.ensure_one()
        data = {"items": [], "agreement_attached": False, "attachment_count": 0}
        if "arcs.compliance.checklist" in self.env:
            lists = self.env["arcs.compliance.checklist"].sudo().search(
                [("donor_id", "=", self.donor_id.id), ("active", "=", True)])
            data["items"] = [{"name": l.name, "required": l.required} for l in lists.line_ids]
        cnt = self.env["ir.attachment"].search_count(
            [("res_model", "=", "arcs.grant"), ("res_id", "=", self.grant_id.id)])
        data["agreement_attached"] = cnt > 0
        data["attachment_count"] = cnt
        return data

    def report_commitments(self):
        self.ensure_one()
        out = []
        if "arcs.commitment" in self.env:
            for c in self.env["arcs.commitment"].search([("grant_id", "=", self.grant_id.id)]):
                out.append({"ref": c.source_ref or c.display_name, "amount": c.amount,
                            "state": dict(c._fields["state"].selection).get(c.state, c.state)})
        return out

    def report_assets(self):
        self.ensure_one()
        out = []
        if "arcs.asset" in self.env:
            Asset = self.env["arcs.asset"]
            cat = dict(Asset._fields["category"].selection)
            st = dict(Asset._fields["state"].selection)
            for a in Asset.search([("grant_id", "=", self.grant_id.id)]):
                out.append({
                    "code": a.code, "name": a.name,
                    "category": cat.get(a.category, a.category),
                    "date": a.acquisition_date and a.acquisition_date.strftime("%d %b %Y") or "",
                    "cost": a.acquisition_cost, "custodian": a.custodian_id.name or "",
                    "state": st.get(a.state, a.state)})
        return out
