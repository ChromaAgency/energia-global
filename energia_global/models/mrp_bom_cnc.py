# -*- coding: utf-8 -*-

from odoo import fields, models


class MrpBom(models.Model):
    _inherit = "mrp.bom"

    cnc_config_ids = fields.One2many(
        "mrp.bom.cnc",
        "bom_id",
        string="CNC Configuration",
    )


class MrpBomCnc(models.Model):
    _name = "mrp.bom.cnc"
    _description = "BOM CNC Configuration"
    _order = "sequence, id"

    bom_id = fields.Many2one(
        "mrp.bom",
        string="Bill of Materials",
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

    _sql_constraints = [
        (
            "bom_cnc_quantity_positive",
            "CHECK(quantity > 0)",
            "Quantity must be greater than zero.",
        ),
        (
            "bom_cnc_unique_per_bom",
            "unique(bom_id, cnc_number)",
            "CNC Number must be unique per BOM.",
        ),
    ]