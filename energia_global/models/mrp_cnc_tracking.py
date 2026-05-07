# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class MrpCncTracking(models.Model):
    _name = "mrp.cnc.tracking"
    _description = "CNC Tracking"
    _order = "sequence, id"

    production_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    cnc_number = fields.Char(string="CNC Number", required=True)
    quantity = fields.Integer(string="Quantity", default=1, required=True)
    render_3d_file = fields.Binary(
        string="3D Render",
        attachment=True,
        help="3D model file (GLB/GLTF) used for CNC visualization.",
    )
    render_3d_filename = fields.Char(string="3D Render Filename")
    has_render_3d = fields.Boolean(
        string="Has 3D Render",
        compute="_compute_has_render_3d",
        store=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("idle", "Idle"),
            ("working", "Working"),
            ("paused", "Paused"),
            ("done", "Done"),
        ],
        string="State",
        default="idle",
        required=True,
        index=True,
    )
    user_id = fields.Many2one("res.users", string="Current User", readonly=True)
    date_start = fields.Datetime(string="Start")
    date_end = fields.Datetime(string="End", readonly=True)
    duration_minutes = fields.Float(string="Duration (Minutes)", default=0.0, readonly=True)
    duration = fields.Float(string="Duration", compute="_compute_duration")

    _sql_constraints = [
        (
            "cnc_quantity_positive",
            "CHECK(quantity > 0)",
            "Quantity must be greater than zero.",
        ),
        (
            "cnc_unique_per_production",
            "unique(production_id, cnc_number)",
            "CNC Number must be unique per manufacturing order.",
        ),
    ]

    @api.depends("duration_minutes", "state", "date_start")
    def _compute_duration(self):
        now = fields.Datetime.now()
        for record in self:
            duration_minutes = record.duration_minutes
            if record.state == "working" and record.date_start:
                elapsed_seconds = (now - record.date_start).total_seconds()
                duration_minutes += max(elapsed_seconds, 0.0) / 60.0
            record.duration = duration_minutes

    @api.depends("render_3d_file")
    def _compute_has_render_3d(self):
        for record in self:
            record.has_render_3d = bool(record.render_3d_file)

    def _ensure_state(self, allowed_states):
        for record in self:
            if record.state not in allowed_states:
                raise UserError(
                    _(
                        "Invalid state transition for CNC %(cnc)s. Current state: %(state)s"
                    )
                    % {
                        "cnc": record.cnc_number,
                        "state": record.state,
                    }
                )

    def _consume_running_time(self):
        now = fields.Datetime.now()
        for record in self.filtered(lambda entry: entry.state == "working" and entry.date_start):
            elapsed_seconds = (now - record.date_start).total_seconds()
            elapsed_minutes = max(elapsed_seconds, 0.0) / 60.0
            record.duration_minutes += elapsed_minutes
            record.date_end = now

    def _safe_progress_workorders(self):
        productions = self.mapped("production_id").exists()
        if not productions:
            return
        for production in productions:
            with self.env.cr.savepoint():
                try:
                    production._try_complete_laser_and_move_next()
                except Exception as error:
                    _logger.warning(
                        "CNC auto progression failed for MO %s: %s",
                        production.display_name,
                        error,
                    )

    def action_start(self):
        self._ensure_state(["idle", "paused"])
        now = fields.Datetime.now()
        self.write(
            {
                "state": "working",
                "date_start": now,
                "date_end": False,
                "user_id": self.env.user.id,
            }
        )
        return True

    def action_pause(self):
        self._ensure_state(["working"])
        self._consume_running_time()
        self.write({"state": "paused"})
        return True

    def action_resume(self):
        return self.action_start()

    def action_finish(self):
        self._ensure_state(["working", "paused"])
        self._consume_running_time()
        self.write({"state": "done", "date_start": False, "date_end": fields.Datetime.now()})
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._safe_progress_workorders()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {"state", "quantity", "cnc_number"}.intersection(vals):
            self._safe_progress_workorders()
        return result

    def unlink(self):
        productions = self.mapped("production_id").exists()
        result = super().unlink()
        for production in productions:
            with self.env.cr.savepoint():
                try:
                    production._try_complete_laser_and_move_next()
                except Exception as error:
                    _logger.warning(
                        "CNC auto progression failed after unlink for MO %s: %s",
                        production.display_name,
                        error,
                    )
        return result