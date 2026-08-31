# -*- coding: utf-8 -*-

from odoo import api, fields, models


class MrpProductionComponentSummary(models.Model):
    _name = "mrp.production.component.summary"
    _description = "MRP Production Component Summary"
    _order = "production_id, product_id"

    production_id = fields.Many2one(
        "mrp.production",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        required=True,
        readonly=True,
        string="Componente",
    )
    uom_id = fields.Many2one(
        "uom.uom",
        required=True,
        readonly=True,
        string="UdM",
    )
    required_qty = fields.Float(
        string="Cantidad Requerida",
        digits="Product Unit of Measure",
        readonly=True,
    )


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    cnc_tracking_ids = fields.One2many(
        "mrp.cnc.tracking",
        "production_id",
        string="CNC",
    )
    cnc_tracking_total = fields.Integer(
        string="CNC Total",
        compute="_compute_cnc_progress",
    )
    cnc_tracking_done = fields.Integer(
        string="CNC Done",
        compute="_compute_cnc_progress",
    )
    all_cnc_done = fields.Boolean(
        string="All CNC Done",
        compute="_compute_cnc_progress",
    )
    component_total_planned_qty = fields.Float(
        string="Components Planned",
        compute="_compute_component_totals",
        readonly=True,
    )
    component_total_done_qty = fields.Float(
        string="Components Done",
        compute="_compute_component_totals",
        readonly=True,
    )
    component_total_remaining_qty = fields.Float(
        string="Components Remaining",
        compute="_compute_component_totals",
        readonly=True,
    )
    component_total_progress_pct = fields.Float(
        string="Components Progress (%)",
        compute="_compute_component_totals",
        readonly=True,
    )
    component_summary_line_ids = fields.One2many(
        "mrp.production.component.summary",
        "production_id",
        string="Sumatoria de Componentes",
        readonly=True,
    )

    @api.depends("cnc_tracking_ids", "cnc_tracking_ids.state")
    def _compute_cnc_progress(self):
        for production in self:
            total = len(production.cnc_tracking_ids)
            done = len(production.cnc_tracking_ids.filtered(lambda entry: entry.state == "done"))
            production.cnc_tracking_total = total
            production.cnc_tracking_done = done
            production.all_cnc_done = bool(total) and total == done

    @api.depends("move_raw_ids", "move_raw_ids.product_uom_qty", "move_raw_ids.state")
    def _compute_component_totals(self):
        production_by_move = {}
        move_ids = []
        for production in self:
            moves = production.move_raw_ids.filtered(lambda move: move.state != "cancel")
            production_by_move[production.id] = moves
            move_ids.extend(moves.ids)

        done_counts = {}
        if move_ids:
            grouped_done = self.env["mrp.workcenter.productivity"].read_group(
                [("move_id", "in", move_ids), ("piece_state", "=", "done")],
                ["move_id"],
                ["move_id"],
            )
            done_counts = {
                row["move_id"][0]: row.get("move_id_count", 0)
                for row in grouped_done
                if row.get("move_id")
            }

        for production in self:
            planned_total = 0.0
            done_total = 0.0
            for move in production_by_move.get(production.id, self.env["stock.move"]):
                target = max(move.product_uom_qty or 0.0, 0.0)
                done_for_move = float(done_counts.get(move.id, 0))
                planned_total += target
                done_total += min(done_for_move, target) if target else done_for_move

            remaining_total = max(planned_total - done_total, 0.0)
            if planned_total:
                progress = done_total / planned_total * 100.0
            else:
                progress = 100.0 if done_total else 0.0

            production.component_total_planned_qty = planned_total
            production.component_total_done_qty = done_total
            production.component_total_remaining_qty = remaining_total
            production.component_total_progress_pct = min(progress, 100.0)

    def _sync_cnc_tracking_from_bom(self):
        """Copia CNC/planos desde BoM; si no hay BoM CNC, usa el plano del producto."""
        tracking_model = self.env["mrp.cnc.tracking"]
        for production in self:
            if production.cnc_tracking_ids:
                continue
            bom_cnc_lines = []
            if production.bom_id:
                bom_cnc_lines = production.bom_id.cnc_config_ids.sorted(
                    key=lambda line: (line.sequence, line.id)
                )
            if bom_cnc_lines:
                tracking_model.create(
                    [
                        {
                            "production_id": production.id,
                            "sequence": line.sequence,
                            "cnc_number": line.cnc_number,
                            "quantity": line.quantity,
                            "render_3d_file": line.render_3d_file,
                            "render_3d_filename": line.render_3d_filename,
                        }
                        for line in bom_cnc_lines
                    ]
                )
                continue
            template = production.product_id.product_tmpl_id
            if not template.render_3d_file:
                continue
            tracking_model.create(
                {
                    "production_id": production.id,
                    "sequence": 10,
                    "cnc_number": template.default_code or template.name or "PLANO-1",
                    "quantity": 1,
                    "render_3d_file": template.render_3d_file,
                    "render_3d_filename": template.render_3d_filename,
                }
            )

    def _build_component_summary_map(self):
        self.ensure_one()
        summary = {}
        moves = self.move_raw_ids.filtered(
            lambda move: move.state != "cancel" and move.product_id
        )
        for move in moves:
            product = move.product_id
            target_uom = product.uom_id
            move_uom = move.product_uom or target_uom
            qty = move_uom._compute_quantity(move.product_uom_qty or 0.0, target_uom)
            values = summary.setdefault(
                product.id,
                {
                    "product_id": product.id,
                    "uom_id": target_uom.id,
                    "required_qty": 0.0,
                },
            )
            values["required_qty"] += qty
        return summary

    def _sync_component_summary_lines(self):
        summary_model = self.env["mrp.production.component.summary"].sudo()
        for production in self:
            summary_by_product = production._build_component_summary_map()
            summary_model.search([("production_id", "=", production.id)]).unlink()
            if summary_by_product:
                summary_model.create(
                    [
                        {
                            "production_id": production.id,
                            "product_id": values["product_id"],
                            "uom_id": values["uom_id"],
                            "required_qty": values["required_qty"],
                        }
                        for values in summary_by_product.values()
                    ]
                )

    @api.model_create_multi
    def create(self, vals_list):
        productions = super().create(vals_list)
        productions._sync_cnc_tracking_from_bom()
        productions._sync_component_summary_lines()
        return productions

    def write(self, vals):
        result = super().write(vals)
        if "bom_id" in vals:
            # ponytail: re-sync planos al cambiar BoM; pierde ediciones manuales en CNC tracking
            self.cnc_tracking_ids.unlink()
            self._sync_cnc_tracking_from_bom()
        if set(vals) & {"bom_id", "product_qty", "move_raw_ids"}:
            self._sync_component_summary_lines()
        return result

    def _get_laser_candidates(self):
        return ("laser", "láser", "cnc")

    def _is_laser_workorder(self, workorder):
        workcenter_name = (workorder.workcenter_id.name or "").lower()
        operation_name = (workorder.operation_id.name or "").lower()
        return any(token in workcenter_name or token in operation_name for token in self._get_laser_candidates())

    def _find_laser_workorder(self):
        self.ensure_one()
        active_workorders = self.workorder_ids.filtered(lambda entry: entry.state not in ("done", "cancel"))
        laser_workorders = active_workorders.filtered(self._is_laser_workorder)
        return laser_workorders.sorted(key=lambda entry: (entry.sequence, entry.id))[:1]

    def _find_next_workorder(self, current_workorder):
        self.ensure_one()
        ordered = self.workorder_ids.sorted(key=lambda entry: (entry.sequence, entry.id))
        for index, workorder in enumerate(ordered):
            if workorder.id != current_workorder.id:
                continue
            for next_workorder in ordered[index + 1 :]:
                if next_workorder.state not in ("done", "cancel"):
                    return next_workorder
            break
        return self.env["mrp.workorder"]

    def _call_first_available_method(self, record, method_names):
        for method_name in method_names:
            method = getattr(record, method_name, False)
            if not method:
                continue
            method()
            return True
        return False

    def _try_complete_laser_and_move_next(self):
        for production in self:
            if not production.all_cnc_done:
                continue

            laser_workorder = production._find_laser_workorder()
            if not laser_workorder:
                continue

            if laser_workorder.state not in ("done", "cancel"):
                production._call_first_available_method(
                    laser_workorder,
                    ["button_finish", "button_done", "do_finish", "action_finish"],
                )

            next_workorder = production._find_next_workorder(laser_workorder)
            if not next_workorder or next_workorder.state in ("progress", "done", "cancel"):
                continue

            production._call_first_available_method(
                next_workorder,
                ["button_start", "action_start"],
            )

        return True