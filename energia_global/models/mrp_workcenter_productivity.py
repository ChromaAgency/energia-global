from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MrpWorkcenterProductivity(models.Model):
    _inherit = "mrp.workcenter.productivity"

    move_id = fields.Many2one(
        "stock.move",
        string="Component",
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        related="move_id.product_id",
        store=True,
        readonly=True,
    )
    piece_state = fields.Selection(
        [
            ("working", "Working"),
            ("paused", "Paused"),
            ("done", "Done"),
        ],
        string="Piece State",
        default="working",
        required=True,
    )

    @api.constrains("workorder_id")
    def _check_open_time_ids(self):
        for workorder in self.workorder_id:
            open_time_ids_by_user = self.env["mrp.workcenter.productivity"]._read_group(
                [
                    ("id", "in", workorder.time_ids.ids),
                    ("date_end", "=", False),
                    ("move_id", "=", False),
                ],
                ["user_id"],
                having=[("__count", ">", 1)],
            )
            if open_time_ids_by_user:
                raise ValidationError(
                    _("The Workorder (%s) cannot be started twice!", workorder.display_name)
                )
