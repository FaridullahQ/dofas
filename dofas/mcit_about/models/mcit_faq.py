from odoo import fields, models


class McitFaq(models.Model):
    _name = "mcit.faq"
    _description = "DoFAS FAQ"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    question = fields.Char(required=True)
    answer = fields.Text(required=True)
    active = fields.Boolean(default=True)
