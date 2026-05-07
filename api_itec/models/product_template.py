# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    sheet_type = fields.Char(string="Tipo de Chapa")
