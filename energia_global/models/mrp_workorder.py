from odoo import fields, api, models, _
from odoo.exceptions import UserError


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    @api.model
    def resolve_workorder_for_move(self, move_id, workcenter_id=False):
        move = self.env["stock.move"].browse(move_id).exists()
        if not move:
            return False
        production = move.raw_material_production_id or move.production_id
        if not production:
            return False
        workorders = production.workorder_ids
        if workcenter_id:
            workorders = workorders.filtered(
                lambda workorder: workorder.workcenter_id.id == workcenter_id
            )
        related_operations = move.related_operation_ids
        if related_operations:
            operation_workorders = workorders.filtered(
                lambda workorder: workorder.operation_id in related_operations
            )
            if operation_workorders:
                workorders = operation_workorders
        elif move.operation_id:
            operation_workorders = workorders.filtered(
                lambda workorder: workorder.operation_id == move.operation_id
            )
            if operation_workorders:
                workorders = operation_workorders
        elif move.bom_line_id and move.bom_line_id.operation_ids:
            operation_workorders = workorders.filtered(
                lambda workorder: workorder.operation_id in move.bom_line_id.operation_ids
            )
            if operation_workorders:
                workorders = operation_workorders
        if not workorders:
            return False
        return workorders.sorted(key=lambda workorder: (workorder.sequence, workorder.id))[0].id

    def get_move_piece_state(self, move_id):
        self.ensure_one()
        move = self.env["stock.move"].browse(move_id).exists()
        if not move:
            return "idle"
        piece_time = self.env["mrp.workcenter.productivity"].search(
            [
                ("workorder_id", "=", self.id),
                ("move_id", "=", move.id),
                ("user_id", "=", self.env.user.id),
            ],
            order="date_start desc, id desc",
            limit=1,
        )
        if not piece_time:
            return "idle"
        if piece_time.piece_state == "working" and not piece_time.date_end:
            return "working"
        if piece_time.piece_state == "paused":
            return "paused"
        if piece_time.piece_state == "done":
            return "done"
        return "idle"

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
        pending_blocking_workorders = self._get_pending_blocking_workorders_for_move(move)
        return not pending_blocking_workorders

    def _get_pending_blocking_workorders_for_move(self, move):
        self.ensure_one()
        blocking_workorders = self._get_blocking_workorders_for_move(move)
        if not blocking_workorders:
            return self.env["mrp.workorder"]
        productivity_model = self.env["mrp.workcenter.productivity"]
        pending_blocking_workorders = self.env["mrp.workorder"]
        for blocking_workorder in blocking_workorders:
            if blocking_workorder.state == "cancel":
                continue
            is_done_in_blocking_operation = bool(
                productivity_model.search_count(
                    [
                        ("workorder_id", "=", blocking_workorder.id),
                        ("move_id", "=", move.id),
                        ("piece_state", "=", "done"),
                    ]
                )
            )
            if not is_done_in_blocking_operation:
                pending_blocking_workorders |= blocking_workorder
        return pending_blocking_workorders

    def _get_blocking_workorders_for_move(self, move):
        self.ensure_one()
        blocking_workorders = self.blocked_by_workorder_ids.filtered(
            lambda blocking_workorder: self._is_move_related_to_workorder(move, blocking_workorder)
        )
        if blocking_workorders:
            return blocking_workorders

        if not self.production_id:
            return self.env["mrp.workorder"]

        previous_related = self.env["mrp.workorder"]
        for workorder in self.production_id.workorder_ids.sorted(
            key=lambda current_workorder: (current_workorder.sequence, current_workorder.id)
        ):
            if workorder.id == self.id:
                break
            if self._is_move_related_to_workorder(move, workorder):
                previous_related |= workorder
        return previous_related

    def _resolve_grouping_field(self, move):
        self.ensure_one()
        grouping_field = self.workcenter_id.grouping_field
        if grouping_field:
            return grouping_field
        if self.workcenter_id.behavior_type == "grouped":
            raise UserError(
                _(
                    "No se ha configurado el campo de agrupación para este centro de trabajo."
                )
            )
        return False

    def _get_move_related_operations(self, move):
        self.ensure_one()
        operations = move.related_operation_ids
        if operations:
            return operations
        operations = self.env["mrp.routing.workcenter"]
        if move.operation_id:
            operations |= move.operation_id
        if move.bom_line_id:
            if move.bom_line_id.operation_ids:
                operations |= move.bom_line_id.operation_ids
            elif move.bom_line_id.operation_id:
                operations |= move.bom_line_id.operation_id
        return operations

    def _is_move_for_current_operation(self, move):
        self.ensure_one()
        if not self.operation_id:
            return True
        related_operations = self._get_move_related_operations(move)
        if not related_operations:
            return True
        return self.operation_id in related_operations

    def _is_move_for_current_workcenter(self, move):
        self.ensure_one()
        if not self.workcenter_id:
            return self._is_move_for_current_operation(move)
        related_workcenters = move.related_workcenter_ids
        if related_workcenters:
            return self.workcenter_id in related_workcenters
        return self._is_move_for_current_operation(move)

    def _is_move_related_to_workorder(self, move, workorder):
        if not workorder.operation_id:
            return False
        related_operations = self._get_move_related_operations(move)
        if not related_operations:
            return False
        return workorder.operation_id in related_operations

    def _get_grouped_moves(self, move):
        self.ensure_one()
        grouping_field = self._resolve_grouping_field(move)
        if not grouping_field:
            return move
        group_value = getattr(move, grouping_field)
        if not group_value:
            return move
        moves = self.production_id.move_raw_ids.filtered(
            lambda component: getattr(component, grouping_field) == group_value
            and self._is_move_for_current_workcenter(component)
        )
        return moves or move

    def check_move_unlocked(self, move_id, grouped=None):
        self.ensure_one()
        move = self.env["stock.move"].browse(move_id).exists()
        if not move:
            return False
        return self._is_move_unlocked(move)

    def get_move_timer_status(self, move_id):
        self.ensure_one()
        move = self.env["stock.move"].browse(move_id).exists()
        if not move:
            return {
                "piece_state": "idle",
                "is_unlocked": False,
                "blocked_by": [],
                "blocked_by_text": _("Bloqueado"),
            }
        pending_blocking_workorders = self._get_pending_blocking_workorders_for_move(move)
        return {
            "piece_state": self.get_move_piece_state(move_id),
            "is_unlocked": not pending_blocking_workorders,
            "blocked_by": pending_blocking_workorders.mapped("display_name"),
            "blocked_by_text": pending_blocking_workorders and _(
                "Bloqueado por: %s"
            )
            % ", ".join(pending_blocking_workorders.mapped("display_name"))
            or False,
        }

    def _get_moves_for_action(self, move, grouped=None):
        self.ensure_one()
        use_grouped = self.workcenter_id.behavior_type == "grouped"
        if grouped is True:
            use_grouped = True
        if use_grouped:
            if not self._is_move_for_current_workcenter(move):
                raise UserError(
                    _(
                        "La pieza seleccionada no está relacionada con el centro de trabajo actual."
                    )
                )
            return self._get_grouped_moves(move)
        if not self._is_move_for_current_operation(move):
            raise UserError(
                _(
                    "La pieza seleccionada no está relacionada con la operación actual."
                )
            )
        return move

    def _get_default_loss_id(self):
        loss = self.env.ref("mrp.block_reason7", raise_if_not_found=False)
        if loss:
            return loss.id
        loss = self.env["mrp.workcenter.productivity.loss"].search(
            [("loss_type", "=", "productive")],
            limit=1,
        )
        if not loss:
            raise UserError(
                _("Debe configurar una pérdida productiva para registrar tiempos.")
            )
        return loss.id

    def _lock_moves_for_timer(self, moves):
        self.ensure_one()
        if not moves:
            return
        self.env.cr.execute(
            "SELECT id FROM stock_move WHERE id IN %s FOR UPDATE",
            [tuple(moves.ids)],
        )

    def _ensure_no_active_timer_in_other_workorders(self, moves):
        self.ensure_one()
        active_times = self.env["mrp.workcenter.productivity"].search(
            [
                ("move_id", "in", moves.ids),
                ("workorder_id", "!=", self.id),
                ("piece_state", "=", "working"),
                ("date_end", "=", False),
            ],
            limit=1,
        )
        if active_times:
            blocking_workorder = active_times.workorder_id
            raise UserError(
                _(
                    "No puede iniciar esta pieza porque ya está en curso en %s. Finalice o pause allí antes de continuar."
                )
                % blocking_workorder.display_name
            )

    def _start_moves_time(self, moves):
        self.ensure_one()
        time_model = self.env["mrp.workcenter.productivity"]
        now = fields.Datetime.now()
        loss_id = self._get_default_loss_id()
        running = time_model.search(
            [
                ("workorder_id", "=", self.id),
                ("move_id", "in", moves.ids),
                ("user_id", "=", self.env.user.id),
                ("piece_state", "=", "working"),
                ("date_end", "=", False),
            ]
        )
        running_move_ids = set(running.mapped("move_id").ids)
        to_create = [
            {
                "workorder_id": self.id,
                "workcenter_id": self.workcenter_id.id,
                "company_id": self.company_id.id,
                "move_id": move.id,
                "user_id": self.env.user.id,
                "date_start": now,
                "piece_state": "working",
                "loss_id": loss_id,
            }
            for move in moves
            if move.id not in running_move_ids
        ]
        if to_create:
            time_model.create(to_create)

    def _close_moves_time(self, moves, piece_state):
        self.ensure_one()
        time_model = self.env["mrp.workcenter.productivity"]
        now = fields.Datetime.now()
        running = time_model.search(
            [
                ("workorder_id", "=", self.id),
                ("move_id", "in", moves.ids),
                ("user_id", "=", self.env.user.id),
                ("piece_state", "=", "working"),
                ("date_end", "=", False),
            ]
        )
        if running:
            running.write({"date_end": now, "piece_state": piece_state})
        remaining_moves = moves - running.mapped("move_id")
        if piece_state == "done" and remaining_moves:
            last_times = time_model.search(
                [
                    ("workorder_id", "=", self.id),
                    ("move_id", "in", remaining_moves.ids),
                    ("user_id", "=", self.env.user.id),
                    ("piece_state", "!=", "done"),
                ],
                order="date_start desc",
            )
            for move in remaining_moves:
                last_time = last_times.filtered(lambda record: record.move_id == move)[:1]
                if not last_time:
                    continue
                vals = {"piece_state": "done"}
                if not last_time.date_end:
                    vals["date_end"] = now
                last_time.write(vals)

    def action_start_piece_time(self, move_id, grouped=None):
        self.ensure_one()
        move = self.env["stock.move"].browse(move_id).exists()
        if not move:
            raise UserError(_("La pieza seleccionada no existe."))
        moves = self._get_moves_for_action(move, grouped)
        self._lock_moves_for_timer(moves)
        self._ensure_no_active_timer_in_other_workorders(moves)
        # In grouped mode we validate the selected piece and then start the full group together.
        moves_to_validate = move if len(moves) > 1 else moves
        locked_moves = moves_to_validate.filtered(
            lambda component: not self._is_move_unlocked(component)
        )
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
