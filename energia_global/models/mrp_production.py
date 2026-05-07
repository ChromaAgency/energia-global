# -*- coding: utf-8 -*-

from odoo import api, fields, models


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

    @api.depends("cnc_tracking_ids", "cnc_tracking_ids.state")
    def _compute_cnc_progress(self):
        for production in self:
            total = len(production.cnc_tracking_ids)
            done = len(production.cnc_tracking_ids.filtered(lambda entry: entry.state == "done"))
            production.cnc_tracking_total = total
            production.cnc_tracking_done = done
            production.all_cnc_done = bool(total) and total == done

    def _sync_cnc_tracking_from_bom(self):
        tracking_model = self.env["mrp.cnc.tracking"]
        for production in self:
            if not production.bom_id:
                continue
            if production.cnc_tracking_ids:
                continue
            bom_cnc_lines = production.bom_id.cnc_config_ids.sorted(key=lambda line: (line.sequence, line.id))
            if not bom_cnc_lines:
                continue
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

    @api.model_create_multi
    def create(self, vals_list):
        productions = super().create(vals_list)
        productions._sync_cnc_tracking_from_bom()
        return productions

    def write(self, vals):
        result = super().write(vals)
        if "bom_id" in vals:
            self._sync_cnc_tracking_from_bom()
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