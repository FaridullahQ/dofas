{
    "name": "MCIT Donor Management",
    "version": "17.0.1.5.0",
    "summary": "Complete donor, grant, fund, budget, project, compliance and reporting suite.",
    "description": "Umbrella app installing the full MCIT Donor Management suite.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3", "author": "MCIT",
    "depends": [
        "mcit_base", "mcit_donor", "mcit_grant", "mcit_budget", "mcit_fund",
        "mcit_expense", "mcit_program", "mcit_procurement", "mcit_compliance",
        "mcit_report", "mcit_closure", "mcit_dashboard", "mcit_asset",
        "mcit_zone", "mcit_request", "mcit_advance", "mcit_about",
    ],
    "data": ["views/menu_structure.xml"],
    "application": True,
    "installable": True,
}
