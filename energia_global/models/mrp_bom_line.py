from odoo import api, fields, models

class MrpProduction(models.Model):
	_inherit = "mrp.production"

	customer_name = fields.Char(string="Customer Name", related='sale_line_id.order_id.partner_id.display_name')

class MrpBomLine(models.Model):
	_inherit = "mrp.bom.line"

	visual_intermediate_product_id = fields.Many2one(
		"product.product",
		string="Producto Intermedio (Visual)",
		help="Campo informativo para mostrar el producto intermedio a producir en taller.",
	)

	operation_ids = fields.Many2many(
		"mrp.routing.workcenter",
		"mrp_bom_line_operation_rel",
		"bom_line_id",
		"operation_id",
		string="Operations",
		help="Operations where this component is consumed.",
	)
	alternative_product_ids = fields.Many2many(
		"product.product",
		"mrp_bom_line_alternative_product_rel",
		"bom_line_id",
		"product_id",
		string="Alternative Components",
		help="Components that can replace this BOM line.",
	)
	render_3d_file = fields.Binary(
		string="3D Render",
		attachment=True,
		help="3D model file (GLB/GLTF) for Shop Floor visualization.",
	)
	render_3d_filename = fields.Char(string="3D Render Filename")

	@api.onchange("operation_id")
	def _onchange_operation_id_sync(self):
		for line in self:
			if line.operation_id and line.operation_id not in line.operation_ids:
				line.operation_ids = [(4, line.operation_id.id)]
