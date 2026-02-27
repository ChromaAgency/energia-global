from odoo import api, fields, models


class MrpWorkorderProductTime(models.Model):
    _name = "mrp.workorder.product.time"
    _description = "Workorder Product Time"
    _order = "date_start desc"

    workorder_id = fields.Many2one(
        "mrp.workorder",
        required=True,
        ondelete="cascade",
    )
    production_id = fields.Many2one(
        related="workorder_id.production_id",
        store=True,
        readonly=True,
    )
    move_id = fields.Many2one(
        "stock.move",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        related="move_id.product_id",
        store=True,
        readonly=True,
    )
    user_id = fields.Many2one(
        "res.users",
        required=True,
        default=lambda self: self.env.user,
    )
    date_start = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
    )
    date_end = fields.Datetime()
    duration = fields.Float(
        compute="_compute_duration",
        store=True,
    )
    state = fields.Selection(
        [
            ("working", "Working"),
            ("paused", "Paused"),
            ("done", "Done"),
        ],
        default="working",
        required=True,
    )
    company_id = fields.Many2one(
        related="workorder_id.company_id",
        store=True,
        readonly=True,
    )

    @api.depends("date_start", "date_end")
    def _compute_duration(self):
        for record in self:
            if record.date_start and record.date_end:
                record.duration = (
                    record.date_end - record.date_start
                ).total_seconds() / 60.0
            else:
                record.duration = 0.0
