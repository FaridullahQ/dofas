{
    "name": "ARCS Donor Mgmt - Grant Governance",
    "version": "17.0.2.0.0",
    "summary": "Agreement version control, fund release schedule, universal compliance "
               "verification (advisory or hard-gate), and donor-feedback-gated closure.",
    "description": """
ARCS Grant Governance
=======================
Implements two related SRS documents as one coherent, layered design rather
than two separate funding-model plug-ins:

- Grant Based Restricted Donation Workflow: formal agreement version
  control, a fund release schedule, and donor-feedback-gated closure - all
  scoped to arcs.grant.is_restricted, so every restricted funding model
  (Grant Based, Earmarked, Multi-Donor, One-Donor-Multiple-Projects)
  benefits, not just Grant Based specifically.
- Unrestricted Donation Workflow: ARCS's own compliance checklist must be
  enforced even without donor-imposed conditions. This revealed that
  compliance-checklist applicability was always donor/requirement-driven in
  this codebase, never restriction-driven - so verification-raising is
  universal (every grant), while agreement/release-schedule/closure-gating
  correctly remain is_restricted-only.

Compliance enforcement is configurable per checklist line, not hardcoded to
a funding model:
- Auto-Raise On (manual / on expense approval / on report submission):
  when a requirement is automatically raised as a Compliance Verification.
- Enforcement (advisory / gate): Advisory never blocks the transaction that
  raised it (only that grant's closure, if left Flagged or Rejected); Gate
  blocks the NEXT step (expense Approval, following Submit; report Review,
  following Submit) until the item is Passed or Waived. Both default to the
  values that reproduce the original, pre-existing behavior, so no existing
  checklist changes behavior until a line is deliberately reconfigured.

Also fixes a latent gap in arcs_compliance: a general (donor_id=False)
checklist's lines were never actually resolved onto any grant, despite the
UI already promising this ("Leave empty for a general checklist"). They now
apply to every grant, alongside that grant's donor-specific checklist(s).

Scope notes:
- "Automatic checking" means automatically raising the right requirement at
  the right moment for a human reviewer to Pass, Flag, Reject, or Waive -
  not machine evaluation of arbitrary donor policy text.
- Donor feedback is recorded manually by staff; no donor-portal integration
  is included (a future interface, not built here).
""",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_grant", "arcs_compliance", "arcs_expense", "arcs_report", "arcs_closure"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_grant_governance_security.xml",
        "views/arcs_grant_agreement_views.xml",
        "views/arcs_grant_release_schedule_views.xml",
        "views/arcs_compliance_verification_views.xml",
        "views/arcs_compliance_checklist_views.xml",
        "views/arcs_grant_views.xml",
        "views/arcs_donor_report_views.xml",
        "views/arcs_project_closure_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "auto_install": False,
}
