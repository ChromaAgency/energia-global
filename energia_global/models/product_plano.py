# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductTemplatePlano(models.Model):
    _name = "product.template.plano"
    _description = "Plano de producto"
    _order = "sequence, id"

    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Producto",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Descripción")
    cnc_number = fields.Char(string="Número CNC")
    render_3d_file = fields.Binary(
        string="Plano 3D",
        attachment=True,
        help="Archivo 3D (GLB/GLTF) para visualización en taller.",
    )
    render_3d_filename = fields.Char(string="Nombre de archivo")
