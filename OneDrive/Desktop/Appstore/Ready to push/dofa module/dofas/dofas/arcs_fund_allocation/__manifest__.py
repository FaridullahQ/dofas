{
    "name": "ARCS Donor Mgmt - Fund Program Allocation",
    "version": "17.0.1.4.0",
    "category": "Accounting",
    "summary": "Auto-generates a Program -> Project -> Activity breakdown (each with its own "
               "Planned Cost) for every Donor Fund Receipt, straight from the grant's own "
               "plan - surfaced on the receipt, the Thank-You letter, and the "
               "acknowledgement email.",
    "description": """
Fund Receipt -> Program Allocation
===================================
Every Donor Fund Receipt automatically gets a hierarchical Program ->
Project -> Activity breakdown of the grant it's against - every Program
related to that grant, every one of its Projects under that grant, and
every one of their Activities, each carrying its own Planned Cost exactly
as already entered in arcs_program. Nothing is typed in by hand: picking
the Grant fills it in immediately, and a Refresh button re-syncs it if the
underlying plan changes later. The same hierarchical breakdown is shown on
the receipt form, the printed Thank-You letter, and prefilled into the
donor acknowledgement email body - so a donor can see, in the same
structure the organisation itself plans in, exactly how their contribution
maps onto real programs, projects and activities.

Kept as a separate module (rather than added into arcs_fund) because
arcs_program depends on arcs_fund indirectly through arcs_expense; arcs_fund
extending arcs_program would create a circular dependency.
""",
    "author": "ARCS",
    "depends": ["arcs_fund", "arcs_program"],
    "data": [
        "security/ir.model.access.csv",
        "views/arcs_fund_receipt_views.xml",
        "report/fund_thanks_report_inherit.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
