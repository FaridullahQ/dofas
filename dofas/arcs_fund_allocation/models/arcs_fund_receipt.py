from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsFundReceipt(models.Model):
    _inherit = "arcs.fund.receipt"

    allocation_ids = fields.One2many(
        "arcs.fund.receipt.allocation", "fund_receipt_id",
        string="Program Allocation",
        help="Auto-generated snapshot of every Program, Project and Activity related "
             "to this receipt's Grant, each with its own Planned Cost - not typed in "
             "by hand. Regenerated automatically when the Grant is set/changed; use "
             "'Refresh Program Allocation' below to re-sync if the underlying plan "
             "has changed since.")
    program_planned_total = fields.Monetary(
        string="Total Planned (this Grant)", currency_field="currency_id",
        compute="_compute_program_planned_total",
        help="Sum of the Planned Cost of every top-level Program shown below - not "
             "a sum of every row (a Program's own figure already includes its "
             "Projects', which already include their Activities', so summing every "
             "row would count the same money several times over).")

    @api.depends("allocation_ids.amount", "allocation_ids.level")
    def _compute_program_planned_total(self):
        for r in self:
            r.program_planned_total = sum(
                r.allocation_ids.filtered(lambda l: l.level == "program").mapped("amount"))

    # ---------------- auto-generation: Program -> Project -> Activity ----------------
    def _build_allocation_vals(self, grant):
        """Every Program related to `grant` (has at least one Project under
        it, or its own Budget Line belongs to it), each of its Projects
        under that grant, and each of THEIR Activities - one plain dict per
        row (no fund_receipt_id/id), in correct nesting order via
        `sequence`. Shared between the interactive onchange (wrapped as
        (0, 0, vals) commands - nothing is written to the database) and
        the real regenerate action (given a fund_receipt_id and passed to
        .create())."""
        self.ensure_one()
        if not grant:
            return []
        programs = self.env["arcs.program"].search([
            "|",
            ("project_ids.grant_id", "=", grant.id),
            ("budget_line_id.grant_id", "=", grant.id),
        ])
        vals_list = []
        seq = 0
        for program in programs:
            seq += 10
            vals_list.append({
                "level": "program", "sequence": seq,
                "program_id": program.id, "amount": program.planned_cost,
            })
            projects = program.project_ids.filtered(lambda p: p.grant_id == grant)
            for project in projects:
                seq += 10
                vals_list.append({
                    "level": "project", "sequence": seq,
                    "program_id": program.id, "project_id": project.id,
                    "amount": project.planned_cost,
                })
                for activity in project.activity_ids:
                    seq += 10
                    vals_list.append({
                        "level": "activity", "sequence": seq,
                        "program_id": program.id, "project_id": project.id,
                        "activity_id": activity.id, "amount": activity.planned_cost,
                    })
        return vals_list

    @api.onchange("grant_id")
    def _onchange_grant_id_allocation(self):
        """Picking (or changing) the Grant immediately rebuilds the
        Program Allocation from that grant's own Program -> Project ->
        Activity plan - the client's own ask: the breakdown should fill in
        by itself, not be typed in line by line."""
        vals_list = self._build_allocation_vals(self.grant_id)
        self.allocation_ids = [(5, 0, 0)] + [(0, 0, v) for v in vals_list]

    def action_refresh_program_allocation(self):
        """Manual re-sync for anything the onchange above wouldn't have
        caught: a receipt created without going through the form (import,
        API, demo data), or the underlying plan (a Program's Planned Cost,
        a newly-added Project/Activity) changing after the receipt already
        has its allocation. Wipes and rebuilds from scratch - draft only,
        same as every other structural edit on this receipt.

        Unlinking is scoped to sudo() deliberately narrowly here (only
        this method, only this model, only the rows already tied to a
        receipt the calling user could already open) rather than granting
        Finance Officer/Manager blanket unlink rights on the allocation
        model in the ACLs - which would let them delete rows through any
        other path too, a bigger permission expansion than this single
        regenerate action actually needs."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_(
                "Only draft receipts can have their Program Allocation refreshed."))
        self.allocation_ids.sudo().unlink()
        vals_list = self._build_allocation_vals(self.grant_id)
        for v in vals_list:
            v["fund_receipt_id"] = self.id
        if vals_list:
            self.env["arcs.fund.receipt.allocation"].sudo().create(vals_list)

    # ---------------- donor acknowledgement email: allocation section ----------------
    def _allocation_rows_total(self):
        """Non-duplicating total of whatever is currently in Program
        Allocation, at whatever granularity each branch has been pruned to.
        A row only counts if its own parent branch isn't ALSO present in
        the same list - a Project row is skipped if its Program row is
        still there, an Activity row is skipped if its own Project row is
        still there. So an untouched, full Program -> Project -> Activity
        hierarchy correctly reduces to just the Program-level figure
        (same number as program_planned_total above), while a branch
        that's been pruned down to just its Project or Activity row(s)
        correctly counts THOSE instead - with nothing left over to
        double-count. This is NOT the same as the tree's own native
        'sum' column footer, which adds every row up literally and so
        double-counts a kept parent+child pair (e.g. a Project row and
        its own child Activity row both left in place, as in this
        receipt) - that footer is a raw arithmetic check, this is the
        real total intended for anything donor-facing."""
        self.ensure_one()
        lines = self.allocation_ids
        programs_shown = set(
            lines.filtered(lambda l: l.level == "program").mapped("program_id").ids)
        projects_shown = set(
            lines.filtered(lambda l: l.level == "project").mapped("project_id").ids)
        total = 0.0
        for line in lines:
            if line.level == "project" and line.program_id.id in programs_shown:
                continue
            if line.level == "activity" and line.project_id.id in projects_shown:
                continue
            total += line.amount
        return total

    def _allocation_email_html(self):
        """HTML fragment listing the Program -> Project -> Activity
        breakdown, hierarchically indented, for splicing into the donor
        acknowledgement email body. Empty string if nothing to show."""
        self.ensure_one()
        if not self.allocation_ids:
            return ""
        currency = self.currency_id.name or ""
        rows = []
        indent_by_level = {"program": 0, "project": 20, "activity": 40}
        weight_by_level = {"program": "bold", "project": "600", "activity": "normal"}
        for line in self.allocation_ids:
            label = {
                "program": line.program_id.display_name,
                "project": line.project_id.display_name,
                "activity": line.activity_id.display_name,
            }.get(line.level, "")
            amount = "{:,.2f} {}".format(line.amount or 0.0, currency)
            rows.append(
                "<tr>"
                "<td style=\"padding:4px 8px;border-bottom:1px solid #e0e0e0;"
                "padding-left:%(indent)spx;font-weight:%(weight)s;\">%(label)s</td>"
                "<td style=\"padding:4px 8px;border-bottom:1px solid #e0e0e0;"
                "text-align:right;\">%(amount)s</td>"
                "</tr>" % {
                    "indent": 8 + indent_by_level.get(line.level, 0),
                    "weight": weight_by_level.get(line.level, "normal"),
                    "label": label, "amount": amount,
                }
            )
        return (
            "<p>%(intro)s</p>"
            "<table style=\"width:100%%;border-collapse:collapse;font-size:13px;margin:8px 0;\">"
            "%(rows)s"
            "<tr>"
            "<td style=\"padding:6px 8px;border-top:2px solid #1F3A5F;font-weight:bold;\">%(total_label)s</td>"
            "<td style=\"padding:6px 8px;border-top:2px solid #1F3A5F;text-align:right;font-weight:bold;\">%(total_amount)s</td>"
            "</tr>"
            "</table>"
        ) % {
            "intro": _(
                "Your contribution is being directed to the following programs, "
                "projects and activities under this grant:"
            ),
            "rows": "".join(rows),
            "total_label": _("Total Planned Cost"),
            "total_amount": "{:,.2f} {}".format(self._allocation_rows_total(), currency),
        }
