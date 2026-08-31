# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductClientTag(models.Model):
    _name = "product.client.tag"
    _description = "Etiqueta de cliente (producto)"
    _order = "name"

    name = fields.Char(string="Cliente", required=True)
    color = fields.Integer(string="Color")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_unique", "unique(name)", "Ya existe una etiqueta de cliente con ese nombre."),
    ]
