# -*- coding: utf-8 -*-

from odoo import fields, models


class ThicknessMeasurements(models.Model):
    _name = "thickness.measurements"
    _description = "Espesor de chapa"
    _order = "name"

    name = fields.Char(string="Espesor", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_unique", "unique(name)", "Ya existe un espesor con ese nombre."),
    ]
