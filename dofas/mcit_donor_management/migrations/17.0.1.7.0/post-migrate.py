"""Revert the menu reorganization (views/menu_structure.xml, removed in this
version) back to each menu's native, module-defined parent/sequence.

Deleting the override file only stops it from being re-applied on future
upgrades - it does NOT undo the field writes it already made on an existing
database. This script explicitly restores the original values so the
reversal actually takes effect here, not just on fresh installs.
"""

# (xmlid, {field: value, ...})
_RESET = [
    ("mcit_base.setting_label", {"sequence": 9}),
    ("mcit_dashboard.menu_mcit_dashboards", {"sequence": 5}),
    ("mcit_base.menu_mcit_operations", {"sequence": 10}),
    ("mcit_report.menu_mcit_reporting", {"sequence": 30}),
    ("mcit_base.menu_mcit_master", {
        "parent_id": "mcit_base.menu_mcit_root", "sequence": 20}),
    ("mcit_base.menu_mcit_config", {"sequence": 99}),
    ("mcit_base.menu_mcit_audit", {
        "parent_id": "mcit_base.menu_mcit_root", "sequence": 90}),
    ("mcit_dashboard.menu_mcit_db_overview", {"sequence": 5}),
    ("mcit_dashboard.menu_mcit_budget_monitor", {"sequence": 10}),
    ("mcit_dashboard.menu_mcit_expense_analysis", {"sequence": 20}),
    ("mcit_dashboard.menu_mcit_commitment_analysis", {"sequence": 30}),
    ("mcit_advance.menu_mcit_advance_tracking", {
        "parent_id": "mcit_advance.menu_mcit_advance_root", "sequence": 30}),
    ("mcit_grant.menu_mcit_grants", {"sequence": 10}),
    ("mcit_budget.menu_mcit_budgets", {"sequence": 10}),
    ("mcit_fund.menu_mcit_fund_receipts", {"sequence": 20}),
    ("mcit_request.menu_mcit_spend_request", {"sequence": 15}),
    ("mcit_expense.menu_mcit_expenses", {"sequence": 16}),
    ("mcit_advance.menu_mcit_advance", {"sequence": 10}),
    ("mcit_advance.menu_mcit_liq", {"sequence": 20}),
    ("mcit_asset.menu_mcit_assets", {"sequence": 45}),
    ("mcit_closure.menu_mcit_closure", {"sequence": 60}),
    ("mcit_budget.menu_mcit_commitments", {"sequence": 30}),
    ("mcit_report.menu_mcit_dept_reports", {"sequence": 10}),
    ("mcit_report.menu_mcit_donor_reports", {"sequence": 20}),
    ("mcit_donor.menu_mcit_donors", {
        "parent_id": "mcit_base.menu_mcit_master", "sequence": 10}),
    ("mcit_zone.menu_mcit_zone", {"sequence": 30}),
    ("mcit_zone.menu_mcit_department", {"sequence": 31}),
    ("mcit_compliance.menu_mcit_compliance", {"sequence": 70}),
    ("mcit_report.menu_mcit_rtemplates", {"sequence": 20}),
]


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    def resolve(xmlid):
        try:
            return env.ref(xmlid, raise_if_not_found=False)
        except Exception:
            return None

    for xmlid, vals in _RESET:
        menu = resolve(xmlid)
        if not menu:
            continue
        write_vals = {}
        for field, value in vals.items():
            if field == "parent_id":
                parent = resolve(value)
                write_vals["parent_id"] = parent.id if parent else False
            else:
                write_vals[field] = value
        menu.write(write_vals)
