{
    "name": "MCIT Donor Mgmt - Dashboards",
    "version": "17.0.1.3.1",
    "summary": "Community monitoring: OWL portfolio dashboard + pivot/graph views.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3", "author": "MCIT",
    "depends": ["mcit_budget", "mcit_expense", "mcit_fund", "mcit_report",
                "mcit_program", "mcit_zone", "mcit_advance"],
    "data": [
        "views/mcit_dashboard_views.xml",
        "views/menus.xml",
        "views/dashboard_action.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mcit_dashboard/static/src/scss/dashboard.scss",
            "mcit_dashboard/static/src/js/dashboard.js",
            "mcit_dashboard/static/src/xml/dashboard.xml",
        ],
    },
    "installable": True,
}
