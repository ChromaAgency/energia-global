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

    def _invalidate_component_progress_fields(self):
        moves = self.mapped("move_id")
        if not moves:
            return
        moves.invalidate_recordset(
            [
                "component_is_finalized",
                "component_finalization_state",
                "component_finalization_state_label",
                "component_operation_stage_label",
                "component_piece_total",
                "component_piece_done",
                "component_progress_pct",
                "component_partial_state",
                "component_partial_state_label",
            ]
        )
        productions = moves.mapped("raw_material_production_id")
        if productions:
            productions.invalidate_recordset(
                [
                    "component_total_planned_qty",
                    "component_total_done_qty",
                    "component_total_remaining_qty",
                    "component_total_progress_pct",
                ]
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._invalidate_component_progress_fields()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._invalidate_component_progress_fields()
        return result

    def unlink(self):
        moves = self.mapped("move_id")
        result = super().unlink()
        if moves:
            moves.invalidate_recordset(
                [
                    "component_is_finalized",
                    "component_finalization_state",
                    "component_finalization_state_label",
                    "component_operation_stage_label",
                    "component_piece_total",
                    "component_piece_done",
                    "component_progress_pct",
                    "component_partial_state",
                    "component_partial_state_label",
                ]
            )
            productions = moves.mapped("raw_material_production_id")
            if productions:
                productions.invalidate_recordset(
                    [
                        "component_total_planned_qty",
                        "component_total_done_qty",
                        "component_total_remaining_qty",
                        "component_total_progress_pct",
                    ]
                )
        return result

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
