"""Revert the menu reorganization (views/menu_structure.xml, removed in this
version) back to each menu's native, module-defined parent/sequence.

Deleting the override file only stops it from being re-applied on future
upgrades - it does NOT undo the field writes it already made on an existing
database. This script explicitly restores the original values so the
reversal actually takes effect here, not just on fresh installs.
"""

# (xmlid, {field: value, ...})
_RESET = [
    ("arcs_base.setting_label", {"sequence": 9}),
    ("arcs_dashboard.menu_arcs_dashboards", {"sequence": 5}),
    ("arcs_base.menu_arcs_operations", {"sequence": 10}),
    ("arcs_report.menu_arcs_reporting", {"sequence": 30}),
    ("arcs_base.menu_arcs_master", {
        "parent_id": "arcs_base.menu_arcs_root", "sequence": 20}),
    ("arcs_base.menu_arcs_config", {"sequence": 99}),
    ("arcs_base.menu_arcs_audit", {
        "parent_id": "arcs_base.menu_arcs_root", "sequence": 90}),
    ("arcs_dashboard.menu_arcs_db_overview", {"sequence": 5}),
    ("arcs_dashboard.menu_arcs_budget_monitor", {"sequence": 10}),
    ("arcs_dashboard.menu_arcs_expense_analysis", {"sequence": 20}),
    ("arcs_dashboard.menu_arcs_commitment_analysis", {"sequence": 30}),
    ("arcs_advance.menu_arcs_advance_tracking", {
        "parent_id": "arcs_advance.menu_arcs_advance_root", "sequence": 30}),
    ("arcs_grant.menu_arcs_grants", {"sequence": 10}),
    ("arcs_budget.menu_arcs_budgets", {"sequence": 10}),
    ("arcs_fund.menu_arcs_fund_receipts", {"sequence": 20}),
    ("arcs_request.menu_arcs_spend_request", {"sequence": 15}),
    ("arcs_expense.menu_arcs_expenses", {"sequence": 16}),
    ("arcs_advance.menu_arcs_advance", {"sequence": 10}),
    ("arcs_advance.menu_arcs_liq", {"sequence": 20}),
    ("arcs_asset.menu_arcs_assets", {"sequence": 45}),
    ("arcs_closure.menu_arcs_closure", {"sequence": 60}),
    ("arcs_budget.menu_arcs_commitments", {"sequence": 30}),
    ("arcs_report.menu_arcs_dept_reports", {"sequence": 10}),
    ("arcs_report.menu_arcs_donor_reports", {"sequence": 20}),
    ("arcs_donor.menu_arcs_donors", {
        "parent_id": "arcs_base.menu_arcs_master", "sequence": 10}),
    ("arcs_zone.menu_arcs_zone", {"sequence": 30}),
    ("arcs_zone.menu_arcs_department", {"sequence": 31}),
    ("arcs_compliance.menu_arcs_compliance", {"sequence": 70}),
    ("arcs_report.menu_arcs_rtemplates", {"sequence": 20}),
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
