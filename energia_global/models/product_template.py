# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    sheet_type = fields.Char(string="Tipo de Chapa")
    broad = fields.Float(string="Ancho", digits="Product Unit of Measure")
    long = fields.Float(string="Largo", digits="Product Unit of Measure")
    superficie = fields.Float(string="Superficie", digits="Product Unit of Measure")
    gross_weight = fields.Float(string="Peso Bruto", digits="Stock Weight")
    thickness_measurements = fields.Many2one(
        "thickness.measurements",
        string="Espesor",
        ondelete="restrict",
    )
    client_tag_ids = fields.Many2many(
        "product.client.tag",
        "product_template_client_tag_rel",
        "product_tmpl_id",
        "tag_id",
        string="Etiqueta de Cliente",
    )
    render_3d_file = fields.Binary(
        string="Plano 3D",
        attachment=True,
        help="Plano del producto. La API lo carga directamente; la OP lo hereda al crearse.",
    )
    render_3d_filename = fields.Char(string="Nombre de archivo del plano")
