from odoo import fields, models, _
from odoo.exceptions import UserError


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def _get_previous_workorder(self):
        self.ensure_one()
        if not self.production_id:
            return False
        workorders = self.production_id.workorder_ids.sorted(
            key=lambda workorder: (workorder.sequence, workorder.id)
        )
        previous = False
        for workorder in workorders:
            if workorder.id == self.id:
                return previous
            previous = workorder
        return False

    def _is_move_unlocked(self, move):
        self.ensure_one()
        previous_workorder = self._get_previous_workorder()
        if not previous_workorder:
            return True
        if previous_workorder.state in ("done", "cancel"):
            return True
        return bool(
            self.env["mrp.workorder.product.time"].search_count(
                [
                    ("workorder_id", "=", previous_workorder.id),
                    ("move_id", "=", move.id),
                    ("state", "=", "done"),
                ]
            )
        )

    def _resolve_grouping_field(self, move):
        self.ensure_one()
        grouping_field = self.workcenter_id.grouping_field
        if grouping_field:
            return grouping_field
        if move.cnc_number:
            return "cnc_number"
        if move.weld_group:
            return "weld_group"
        return False

    def _get_grouped_moves(self, move):
        self.ensure_one()
        grouping_field = self._resolve_grouping_field(move)
        if not grouping_field:
            raise UserError(
                _(
                    "No se ha configurado el campo de agrupación para este centro de trabajo."
                )
            )
        group_value = getattr(move, grouping_field)
        if not group_value:
            raise UserError(
                _(
                    "La pieza seleccionada no tiene valor para el campo de agrupación."
                )
            )
        moves = self.production_id.move_raw_ids.filtered(
            lambda component: getattr(component, grouping_field) == group_value
        )
        return moves or move

    def check_move_unlocked(self, move_id):
        self.ensure_one()
        move = self.env["stock.move"].browse(move_id).exists()
        if not move:
            return False
        return self._is_move_unlocked(move)

    def _get_moves_for_action(self, move, grouped=None):
        self.ensure_one()
        if self.workcenter_id.behavior_type == "grouped":
            return self._get_grouped_moves(move)
        return move

    def _start_moves_time(self, moves):
        self.ensure_one()
        time_model = self.env["mrp.workorder.product.time"]
        now = fields.Datetime.now()
        running = time_model.search(
            [
                ("workorder_id", "=", self.id),
                ("move_id", "in", moves.ids),
                ("user_id", "=", self.env.user.id),
                ("state", "=", "working"),
                ("date_end", "=", False),
            ]
        )
        running_move_ids = set(running.mapped("move_id").ids)
        to_create = [
            {
                "workorder_id": self.id,
                "move_id": move.id,
                "user_id": self.env.user.id,
                "date_start": now,
                "state": "working",
            }
            for move in moves
            if move.id not in running_move_ids
        ]
        if to_create:
            time_model.create(to_create)

    def _close_moves_time(self, moves, state):
        self.ensure_one()
        time_model = self.env["mrp.workorder.product.time"]
        now = fields.Datetime.now()
        running = time_model.search(
            [
                ("workorder_id", "=", self.id),
                ("move_id", "in", moves.ids),
                ("user_id", "=", self.env.user.id),
                ("state", "=", "working"),
                ("date_end", "=", False),
            ]
        )
        if running:
            running.write({"date_end": now, "state": state})
        remaining_moves = moves - running.mapped("move_id")
        if state == "done" and remaining_moves:
            last_times = time_model.search(
                [
                    ("workorder_id", "=", self.id),
                    ("move_id", "in", remaining_moves.ids),
                    ("user_id", "=", self.env.user.id),
                    ("state", "!=", "done"),
                ],
                order="date_start desc",
            )
            for move in remaining_moves:
                last_time = last_times.filtered(lambda record: record.move_id == move)[:1]
                if not last_time:
                    continue
                vals = {"state": "done"}
                if not last_time.date_end:
                    vals["date_end"] = now
                last_time.write(vals)

    def action_start_piece_time(self, move_id, grouped=None):
        self.ensure_one()
        move = self.env["stock.move"].browse(move_id).exists()
        if not move:
            raise UserError(_("La pieza seleccionada no existe."))
        moves = self._get_moves_for_action(move, grouped)
        locked_moves = moves.filtered(lambda component: not self._is_move_unlocked(component))
        if locked_moves:
            raise UserError(
                _(
                    "Las siguientes piezas siguen bloqueadas: %s"
                )
                % ", ".join(locked_moves.mapped("display_name"))
            )
        self._start_moves_time(moves)
        return True

    def action_pause_piece_time(self, move_id, grouped=None):
        self.ensure_one()
        move = self.env["stock.move"].browse(move_id).exists()
        if not move:
            raise UserError(_("La pieza seleccionada no existe."))
        moves = self._get_moves_for_action(move, grouped)
        self._close_moves_time(moves, "paused")
        return True

    def action_stop_piece_time(self, move_id, grouped=None):
        self.ensure_one()
        move = self.env["stock.move"].browse(move_id).exists()
        if not move:
            raise UserError(_("La pieza seleccionada no existe."))
        moves = self._get_moves_for_action(move, grouped)
        self._close_moves_time(moves, "done")
        return True
