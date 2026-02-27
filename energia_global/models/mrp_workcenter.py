from odoo import fields, models


class MrpWorkcenter(models.Model):
    _inherit = "mrp.workcenter"

    behavior_type = fields.Selection(
        [
            ("individual", "Individual"),
            ("grouped", "Grouped"),
        ],
        string="Piece Start Behavior",
        default="individual",
        required=True,
    )
    grouping_field = fields.Selection(
        [
            ("cnc_number", "CNC Number"),
            ("weld_group", "Weld Group"),
        ],
        string="Grouping Field",
    )
