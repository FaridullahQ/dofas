from odoo import fields, models


class ArcsCommitment(models.Model):
    _inherit = "arcs.commitment"

    # Kept fully optional, alongside the required budget_line_id (the
    # financial/accounting axis, unchanged) - these represent a second,
    # independent axis: the programmatic hierarchy a commitment belongs to.
    # An acquisition not linked to an Activity leaves all three empty and
    # behaves exactly as before this feature existed. When Program/Project
    # ceilings enforcement is off (the default), these fields are still
    # populated for traceability/reporting, they just aren't checked against
    # an availability limit at commit time.
    activity_id = fields.Many2one(
        "arcs.activity", string="Activity", ondelete="restrict", index=True)
    project_id = fields.Many2one(
        "arcs.project", string="Project", ondelete="restrict", index=True)
    program_id = fields.Many2one(
        "arcs.program", string="Program", ondelete="restrict", index=True)
