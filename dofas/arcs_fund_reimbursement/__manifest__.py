{
    "name": "ARCS Donor Mgmt - Reimbursement",
    "version": "17.0.1.0.0",
    "summary": "Reimbursement claim engine: bundle approved expenses -> submit for donor "
               "validation -> approved/rejected -> fund receipt -> final report, for "
               "grants on the Reimbursement funding model.",
    "description": """
ARCS Reimbursement
====================
Implements the second ARCS funding-model plug-in (after Revolving Fund):
the Reimbursement Donation Workflow SRS, where ARCS spends first and is
repaid by the donor only after submitting proof and receiving validation.

This is a genuinely different cash-flow direction from every other funding
model already built (donor pays first, ARCS spends within that ceiling) -
so unlike Grant Based / Unrestricted, this is NOT cross-cutting governance;
it is a funding-model plug-in exactly like arcs_fund_revolving, keyed on
funding_model == 'reimbursement'.

Deliberately reuses rather than rebuilds:
- MoU version control: a Reimbursement grant is is_restricted by definition,
  so it already gets arcs_grant_governance's Agreement Version gate on
  approval for free. No new agreement model here.
- "ARC spends from internal or advance funds" (SRS 4.2): already fully
  modeled by the existing arcs_advance module (lock/disburse/liquidate,
  already linked to grant/budget line). Nothing added or changed there.
- Compliance checklist / "validate completeness before submission" (SRS
  4.1, 4.3): reuses arcs_grant_governance's compliance verification engine,
  extended with one new Auto-Raise trigger ("On Reimbursement Claim
  Submission") via selection_add - not a parallel checklist system.
- Cash-basis expense gating: deliberately NOT added. The entire point of
  Reimbursement is that spending is NOT gated on donor funds received
  (there are none yet) - expenses proceed under the normal budget-line
  ceiling only, same as every non-cash-basis grant today.

The one genuinely new piece is arcs.reimbursement.claim: a bundle of
approved/posted expenses submitted together as one donor-facing proof
package, whose approval unlocks the actual arcs.fund.receipt and whose
funding/reporting closes the loop - mirroring how arcs.revolving.cycle
orchestrates existing engines rather than replacing them.
""",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_grant", "arcs_fund", "arcs_budget", "arcs_expense",
               "arcs_report", "arcs_grant_governance"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_reimbursement_security.xml",
        "data/ir_sequence_data.xml",
        "views/arcs_reimbursement_claim_views.xml",
        "views/arcs_grant_views.xml",
        "views/arcs_expense_views.xml",
        "views/arcs_fund_receipt_views.xml",
        "views/arcs_donor_report_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "auto_install": False,
}
