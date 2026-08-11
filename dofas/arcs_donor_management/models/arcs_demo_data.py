import logging
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEMO_MODULE = "__arcs_demo__"

# Deletion order matters: children before parents, so FK/ondelete constraints
# never block cleanup. arcs.commitment has no cascade tie to its source
# document, so it's deleted explicitly alongside it.
CLEANUP_ORDER = [
    "arcs.advance.liquidation",
    "arcs.advance",
    "arcs.expense",
    "arcs.asset",
    "arcs.budget.transfer",
    "arcs.donor.funding.request",
    "arcs.spend.request",
    "arcs.commitment",
    "arcs.fund.receipt",
    "arcs.activity",
    "arcs.project",
    "arcs.program",
    "arcs.budget",
    "arcs.grant",
    "arcs.department",
    "arcs.zone",
    "arcs.donor",
]


class ArcsDemoData(models.AbstractModel):
    """Generates (and cleanly removes) a realistic, interconnected demo
    dataset spanning every feature of the DOFAS suite, triggered by the
    'Demo Data' toggle in Settings. Every top-level record created here is
    tagged via ir.model.data (module=__arcs_demo__) so it can be found and
    unwound later without touching any real data the user has entered."""

    _name = "arcs.demo.data"
    _description = "DOFAS Demo Data Generator"

    # ------------------------------------------------------------------ utils
    def _tag(self, xmlid_name, record):
        self.env["ir.model.data"].sudo().create({
            "name": xmlid_name,
            "module": DEMO_MODULE,
            "model": record._name,
            "res_id": record.id,
            "noupdate": True,
        })
        return record

    def _ref(self, xmlid_name):
        return self.env.ref("%s.%s" % (DEMO_MODULE, xmlid_name), raise_if_not_found=False)

    def _section(self, label, func):
        try:
            with self.env.cr.savepoint():
                func()
            _logger.info("Demo data: generated section '%s' OK.", label)
        except Exception as exc:  # noqa: BLE001 - a failed section must never block the rest
            _logger.warning("Demo data: section '%s' skipped (%s).", label, exc)

    # ================================================================ generate
    def _generate(self, company):
        self = self.sudo().with_company(company)
        today = fields.Date.context_today(self)

        state = {}  # small registry passed between sections

        self._section("Prerequisites (analytic plan)", lambda: self._ensure_prereqs(company))
        self._section("Donors", lambda: self._gen_donors(state))
        self._section("Grants", lambda: self._gen_grants(state, today))
        self._section("Budgets", lambda: self._gen_budgets(state))
        self._section("Regions / Provinces / Departments", lambda: self._gen_geo(state))
        self._section("Programs / Projects / Activities", lambda: self._gen_programs(state, today))
        self._section("Acquisitions (Four-Form)", lambda: self._gen_acquisitions(state, today))
        self._section("Recovery: Internal Transfer & Donor Funding", lambda: self._gen_recovery(state))
        self._section("Expenses", lambda: self._gen_expenses(state, today))
        self._section("Fund Receipts", lambda: self._gen_fund_receipts(state, today))
        self._section("Advances & Liquidation", lambda: self._gen_advances(state, today))
        self._section("Asset Register", lambda: self._gen_assets(state, today))

    def _ensure_prereqs(self, company):
        """Grants require a Default Grant Analytic Plan configured on the
        company before they can be approved (arcs.grant auto-creates an
        analytic account under it). The demo generator should be
        self-sufficient rather than require the user to configure Settings
        first, so provision a minimal plan automatically - but ONLY if
        nothing is configured yet; a real, user-set plan is never touched
        or replaced."""
        if company.arcs_default_analytic_plan_id:
            return
        plan = self.env["account.analytic.plan"].search([], limit=1)
        if not plan:
            plan = self.env["account.analytic.plan"].create({"name": "Grants"})
            self._tag("analytic_plan_demo", plan)
        company.sudo().write({"arcs_default_analytic_plan_id": plan.id})

    # ---------------------------------------------------------------- donors
    def _gen_donors(self, state):
        Donor = self.env["arcs.donor"]
        donors_vals = [
            {"name": "Global Health Fund", "code": "GHF", "donor_type": "multilateral",
             "email": "grants@globalhealthfund.org", "reporting_frequency": "quarterly"},
            {"name": "European Union Trust Fund", "code": "EUTF", "donor_type": "government",
             "email": "contact@eutf.example.org", "reporting_frequency": "quarterly"},
            {"name": "Nordic Relief Foundation", "code": "NRF", "donor_type": "foundation",
             "email": "info@nordicrelief.example.org", "reporting_frequency": "annual"},
        ]
        state["donors"] = []
        for i, vals in enumerate(donors_vals):
            d = self._tag("donor_%d" % i, Donor.create(vals))
            state["donors"].append(d)

    # ---------------------------------------------------------------- grants
    def _gen_grants(self, state, today):
        Grant = self.env["arcs.grant"]
        d0, d1, d2 = state["donors"][0], state["donors"][1], state["donors"][2]
        currency = self.env.company.currency_id.id

        specs = [
            # (xmlid, donor, number, title, amount, state chain, funding_model)
            ("grant_active", d0, "GHF-2026-001", "Vaccination Outreach Program", 250000,
             ["submit", "approve", "activate"], "grant_based"),
            ("grant_draft", d1, "EUTF-2026-014", "Community Resilience Initiative", 120000,
             [], "earmarked"),
            ("grant_closed", d2, "NRF-2025-007", "Winter Emergency Relief", 80000,
             ["submit", "approve", "activate", "close"], "reimbursement"),
        ]
        state["grants"] = {}
        for xmlid, donor, number, title, amount, chain, model in specs:
            g = Grant.create({
                "name": title, "grant_number": number, "donor_id": donor.id,
                "funding_model": model, "currency_id": currency,
                "date_start": today - timedelta(days=200), "date_end": today + timedelta(days=200),
                "approved_amount": amount,
            })
            for step in chain:
                getattr(g, "action_%s" % step)()
            self._tag(xmlid, g)
            state["grants"][xmlid] = g

    # ---------------------------------------------------------------- budgets
    def _gen_budgets(self, state):
        Budget = self.env["arcs.budget"]
        active = state["grants"]["grant_active"]
        closed = state["grants"]["grant_closed"]

        b1 = Budget.create({"grant_id": active.id, "line_ids": [
            (0, 0, {"name": "Cold Chain Equipment", "category": "equipment", "planned_amount": 90000}),
            (0, 0, {"name": "Field Staff & HR", "category": "hr", "planned_amount": 70000}),
            (0, 0, {"name": "Training & Workshops", "category": "training", "planned_amount": 30000}),
            (0, 0, {"name": "Logistics & Transport", "category": "logistics", "planned_amount": 40000}),
            (0, 0, {"name": "Program Administration", "category": "administration", "planned_amount": 20000}),
        ]})
        b1.action_approve()
        self._tag("budget_active", b1)

        b2 = Budget.create({"grant_id": closed.id, "line_ids": [
            (0, 0, {"name": "Emergency Kits", "category": "procurement", "planned_amount": 50000}),
            (0, 0, {"name": "Travel & Field Visits", "category": "travel", "planned_amount": 30000}),
        ]})
        b2.action_approve()
        self._tag("budget_closed", b2)

        state["budgets"] = {"active": b1, "closed": b2}
        state["lines"] = {l.name: l for l in (b1.line_ids | b2.line_ids)}

    # ---------------------------------------------------------------- geo
    def _gen_geo(self, state):
        Zone = self.env["arcs.zone"]
        Dept = self.env["arcs.department"]

        hq = self._tag("zone_hq", Zone.create({"name": "Head Office", "code": "HQ", "kind": "hq"}))
        central = self._tag("zone_central", Zone.create(
            {"name": "Central Region", "code": "CTRL", "kind": "zone", "parent_id": hq.id}))
        eastern = self._tag("zone_eastern", Zone.create(
            {"name": "Eastern Region", "code": "EAST", "kind": "zone", "parent_id": hq.id}))
        prov1 = self._tag("zone_prov1", Zone.create(
            {"name": "Kabul Province", "code": "KBL", "kind": "province", "parent_id": central.id}))
        prov2 = self._tag("zone_prov2", Zone.create(
            {"name": "Nangarhar Province", "code": "NGR", "kind": "province", "parent_id": eastern.id}))

        dept1 = self._tag("dept_health", Dept.create(
            {"name": "Health", "code": "HEALTH", "zone_id": prov1.id}))
        dept2 = self._tag("dept_logistics", Dept.create(
            {"name": "Logistics", "code": "LOGIS", "zone_id": prov1.id}))
        dept3 = self._tag("dept_it", Dept.create(
            {"name": "IT", "code": "IT", "zone_id": prov2.id}))

        state["zones"] = {"hq": hq, "central": central, "eastern": eastern,
                          "prov1": prov1, "prov2": prov2}
        state["departments"] = {"health": dept1, "logistics": dept2, "it": dept3}

    # ---------------------------------------------------------------- programs
    def _gen_programs(self, state, today):
        Program = self.env["arcs.program"]
        Project = self.env["arcs.project"]
        Activity = self.env["arcs.activity"]
        active = state["grants"]["grant_active"]

        prog = self._tag("program_health", Program.create({"name": "Health Program", "code": "PRG-HLT"}))
        proj = self._tag("project_vacc", Project.create({
            "name": "Vaccination Project", "code": "PRJ-VAC", "program_id": prog.id,
            "grant_id": active.id, "date_start": today - timedelta(days=180),
            "date_end": today + timedelta(days=180),
        }))
        act1 = self._tag("activity_kits", Activity.create({
            "name": "Purchasing Vaccination Kits", "project_id": proj.id,
            "date_start": today - timedelta(days=150), "date_end": today + timedelta(days=150),
        }))
        act2 = self._tag("activity_training", Activity.create({
            "name": "Cold Chain Staff Training", "project_id": proj.id,
            "date_start": today - timedelta(days=120), "date_end": today + timedelta(days=90),
        }))
        state["programs"] = {"prog": prog, "proj": proj, "act_kits": act1, "act_training": act2}

    # ---------------------------------------------------------------- acquisitions
    def _gen_acquisitions(self, state, today):
        SR = self.env["arcs.spend.request"]
        active = state["grants"]["grant_active"]
        eq_line = state["lines"]["Cold Chain Equipment"]
        hr_line = state["lines"]["Field Staff & HR"]
        log_line = state["lines"]["Logistics & Transport"]
        zone = state["zones"]["prov1"]
        dept = state["departments"]["health"]
        proj = state["programs"]["proj"]
        act = state["programs"]["act_kits"]
        vendor = self.env["res.partner"].search([("name", "=", "Azizi Medical Supplies")], limit=1) \
            or self._tag("vendor_azizi", self.env["res.partner"].create(
                {"name": "Azizi Medical Supplies", "company_type": "company"}))

        def base_vals(name, budget_line, amount, note=""):
            return {
                "name": name, "zone_id": zone.id, "department_id": dept.id,
                "budget_line_id": budget_line.id, "project_id": proj.id, "activity_id": act.id,
                "date_request": today, "note": note,
                "line_ids": [(0, 0, {"name": name, "quantity": 1, "unit_estimate": amount})],
            }

        acqs = {}

        # 1) Draft
        acqs["draft"] = self._tag("acq_draft", SR.create(
            base_vals("Purchase office laptops", hr_line, 4500)))

        # 2) Submitted (awaiting Confirm Real Price)
        sub = SR.create(base_vals("Buy printer and scanner", hr_line, 1800))
        sub.action_submit()
        acqs["submitted"] = self._tag("acq_submitted", sub)

        # 3) Committed (quoted + reserved, matches the estimate closely)
        com = SR.create(base_vals("Cold chain refrigerators", eq_line, 25000))
        com.action_submit()
        com.approved_amount = 24500
        com.quotation_ref = "QTN-2026-0101"
        com.vendor_id = vendor.id
        com.action_commit()
        acqs["committed"] = self._tag("acq_committed", com)

        # 4) Approved -> can spawn an expense
        appr = SR.create(base_vals("Vaccination kits (bulk)", eq_line, 20000))
        appr.action_submit()
        appr.approved_amount = 19500
        appr.quotation_ref = "QTN-2026-0102"
        appr.vendor_id = vendor.id
        appr.action_commit()
        appr.action_approve()
        acqs["approved"] = self._tag("acq_approved", appr)

        # 5) Insufficient Funds (deliberately over-quotes the small logistics line)
        short = SR.create(base_vals("Vehicle hire for field visits", log_line, 45000))
        short.action_submit()
        short.approved_amount = 45000
        short.quotation_ref = "QTN-2026-0103"
        short.vendor_id = vendor.id
        try:
            short.action_commit()
        except UserError:
            pass
        self._tag("acq_insufficient", short)
        acqs["insufficient"] = short

        state["acquisitions"] = acqs
        state["vendor"] = vendor

    # ---------------------------------------------------------------- recovery
    def _gen_recovery(self, state):
        short = state["acquisitions"].get("insufficient")
        if not short or short.state != "insufficient_funds":
            return
        # Internal transfer covering part of the shortfall, left submitted
        # (not approved) so it's a visible, actionable demo record.
        transfer = self.env["arcs.budget.transfer"].create({
            "to_line_id": short.budget_line_id.id,
            "from_line_id": state["lines"]["Program Administration"].id,
            "amount": min(short.shortfall_amount or 5000, 5000),
            "reason": "Demo: cover part of the shortfall on %s." % short.name,
            "spend_request_id": short.id,
        })
        transfer.action_submit()
        self._tag("transfer_demo", transfer)

        funding = self.env["arcs.donor.funding.request"].create({
            "grant_id": short.grant_id.id,
            "amount_requested": short.shortfall_amount or 5000,
            "reason": "Demo: request supplementary funds to cover %s." % short.name,
            "spend_request_id": short.id,
        })
        funding.action_request()
        self._tag("funding_demo", funding)

    # ---------------------------------------------------------------- expenses
    def _gen_expenses(self, state, today):
        Expense = self.env["arcs.expense"]
        active = state["grants"]["grant_active"]
        hr_line = state["lines"]["Field Staff & HR"]
        zone = state["zones"]["prov1"]
        vendor = state.get("vendor")

        def vals(name, budget_line, amount, extra=None):
            v = {"name": name, "grant_id": active.id, "budget_line_id": budget_line.id,
                "amount": amount, "date": today, "zone_id": zone.id, "partner_id": vendor.id if vendor else False}
            if extra:
                v.update(extra)
            return v

        # 1) Draft
        e1 = Expense.create(vals("Stationery and office supplies", hr_line, 450))
        self._tag("expense_draft", e1)

        # 2) Submitted
        e2 = Expense.create(vals("Field team per-diem, June", hr_line, 2100))
        e2.action_submit()
        self._tag("expense_submitted", e2)

        # 3) Posted, spawned from the approved acquisition (adopts its reserve)
        appr = state["acquisitions"].get("approved")
        if appr:
            e3 = Expense.create(vals(appr.name, appr.budget_line_id, appr.approved_amount or appr.estimated_amount,
                                      {"request_id": appr.id, "project_id": appr.project_id.id,
                                       "activity_id": appr.activity_id.id}))
            e3.action_submit()
            e3.action_approve()
            e3.action_post()
            self._tag("expense_posted", e3)

    # ---------------------------------------------------------------- fund receipts
    def _gen_fund_receipts(self, state, today):
        Receipt = self.env["arcs.fund.receipt"]
        active = state["grants"]["grant_active"]
        closed = state["grants"]["grant_closed"]

        r1 = Receipt.create({
            "grant_id": active.id, "amount": 100000, "currency_id": active.currency_id.id,
            "received_date": today - timedelta(days=60),
            "bank_voucher_ref": "BV-2026-0044",
        })
        r1.action_post()
        self._tag("receipt_1", r1)

        r2 = Receipt.create({
            "grant_id": closed.id, "amount": 80000, "currency_id": closed.currency_id.id,
            "received_date": today - timedelta(days=300),
            "bank_voucher_ref": "BV-2025-0091",
        })
        r2.action_post()
        self._tag("receipt_2", r2)

    # ---------------------------------------------------------------- advances
    def _gen_advances(self, state, today):
        Advance = self.env["arcs.advance"]
        active = state["grants"]["grant_active"]
        hr_line = state["lines"]["Field Staff & HR"]
        prov1, prov2 = state["zones"]["prov1"], state["zones"]["prov2"]

        a1 = Advance.create({
            "advance_type": "zone", "zone_id": prov1.id, "grant_id": active.id,
            "budget_line_id": hr_line.id, "amount": 5000, "date": today - timedelta(days=20),
            "reference": "ADV-DEMO-1",
        })
        a1.action_issue()
        self._tag("advance_1", a1)

        a2 = Advance.create({
            "advance_type": "zone", "zone_id": prov2.id, "grant_id": active.id,
            "budget_line_id": hr_line.id, "amount": 3000, "date": today - timedelta(days=10),
            "reference": "ADV-DEMO-2",
        })
        a2.action_issue()
        self._tag("advance_2", a2)

        Liquidation = self.env["arcs.advance.liquidation"]
        liq = Liquidation.create({
            "advance_id": a1.id, "amount": 3200, "date": today - timedelta(days=2),
            "note": "Demo: partial liquidation of ADV-DEMO-1.",
        })
        self._tag("liquidation_1", liq)

    # ---------------------------------------------------------------- assets
    def _gen_assets(self, state, today):
        Asset = self.env["arcs.asset"]
        active = state["grants"]["grant_active"]

        a1 = Asset.create({
            "name": "Toyota Land Cruiser - Field Vehicle", "grant_id": active.id,
            "category": "vehicle" if "vehicle" in dict(Asset._fields["category"].selection) else "equipment",
            "acquisition_date": today - timedelta(days=90), "acquisition_cost": 45000,
        })
        self._tag("asset_1", a1)

        a2 = Asset.create({
            "name": "Cold Chain Refrigerator Unit #2", "grant_id": active.id,
            "category": "equipment", "acquisition_date": today - timedelta(days=30),
            "acquisition_cost": 8500,
        })
        self._tag("asset_2", a2)

    # ================================================================== clear
    def _clear(self):
        self = self.sudo()
        IMD = self.env["ir.model.data"].sudo()
        entries = IMD.search([("module", "=", DEMO_MODULE)])
        by_model = {}
        for e in entries:
            by_model.setdefault(e.model, []).append(e.res_id)

        for model in CLEANUP_ORDER:
            ids = by_model.pop(model, [])
            if not ids:
                continue
            try:
                with self.env.cr.savepoint():
                    self.env[model].browse(ids).exists().unlink()
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Demo data cleanup: could not remove %s (%s).", model, exc)

        # Anything left over from a model not in the explicit order (e.g. a
        # vendor partner) - best-effort, ignore individual failures.
        for model, ids in by_model.items():
            try:
                with self.env.cr.savepoint():
                    self.env[model].browse(ids).exists().unlink()
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Demo data cleanup: could not remove leftover %s (%s).", model, exc)

        IMD.search([("module", "=", DEMO_MODULE)]).unlink()
