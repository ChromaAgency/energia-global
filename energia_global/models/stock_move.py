from odoo import api, fields, models


class StockMove(models.Model):
	_inherit = "stock.move"

	related_workcenter_ids = fields.Many2many(
		"mrp.workcenter",
		compute="_compute_related_workcenter_ids",
		store=True,
		readonly=True,
		string="Related Work Centers",
	)
	related_operation_ids = fields.Many2many(
		"mrp.routing.workcenter",
		compute="_compute_related_operation_ids",
		store=True,
		readonly=True,
		string="Related Operations",
	)
	alternative_product_ids = fields.Many2many(
		"product.product",
		compute="_compute_alternative_products",
		readonly=True,
		string="Alternative Components",
	)
	alternative_product_id = fields.Many2one(
		"product.product",
		string="Alternative Component",
		domain="[('id', 'in', alternative_product_ids)]",
		compute="_compute_alternative_products",
		readonly=True,
		store=True,
	)
	cnc_number = fields.Char(string="CNC Number")
	weld_group = fields.Char(string="Weld Group")
	is_unlocked = fields.Boolean(
		string="Unlocked",
		compute="_compute_is_unlocked",
	)
	render_3d_file = fields.Binary(
		related="bom_line_id.render_3d_file",
		readonly=True,
	)
	render_3d_filename = fields.Char(
		related="bom_line_id.render_3d_filename",
		readonly=True,
	)
	has_render_3d = fields.Boolean(
		compute="_compute_has_render_3d",
		store=True,
		readonly=True,
	)

	@api.depends("bom_line_id", "bom_line_id.alternative_product_ids")
	def _compute_alternative_products(self):
		for move in self:
			move.alternative_product_ids = move.bom_line_id.alternative_product_ids
			move.alternative_product_id = move.bom_line_id.alternative_product_ids[:1]

	@api.depends(
		"operation_id",
		"bom_line_id",
		"bom_line_id.operation_id",
		"bom_line_id.operation_ids",
	)
	def _compute_related_operation_ids(self):
		for move in self:
			operations = self.env["mrp.routing.workcenter"]
			if move.operation_id:
				operations |= move.operation_id
			if move.bom_line_id:
				if move.bom_line_id.operation_ids:
					operations |= move.bom_line_id.operation_ids
				elif move.bom_line_id.operation_id:
					operations |= move.bom_line_id.operation_id
			move.related_operation_ids = operations

	@api.depends(
		"operation_id",
		"operation_id.workcenter_id",
		"bom_line_id",
		"bom_line_id.operation_id",
		"bom_line_id.operation_id.workcenter_id",
		"bom_line_id.operation_ids",
		"bom_line_id.operation_ids.workcenter_id",
	)
	def _compute_related_workcenter_ids(self):
		for move in self:
			workcenters = self.env["mrp.workcenter"]
			if move.operation_id and move.operation_id.workcenter_id:
				workcenters |= move.operation_id.workcenter_id
			if move.bom_line_id:
				if move.bom_line_id.operation_ids:
					workcenters |= move.bom_line_id.operation_ids.mapped("workcenter_id")
				elif move.bom_line_id.operation_id and move.bom_line_id.operation_id.workcenter_id:
					workcenters |= move.bom_line_id.operation_id.workcenter_id
			move.related_workcenter_ids = workcenters

	@api.depends("bom_line_id.render_3d_file")
	def _compute_has_render_3d(self):
		for move in self:
			move.has_render_3d = bool(move.bom_line_id.render_3d_file)

	@api.onchange("alternative_product_id")
	def _onchange_alternative_product_id(self):
		for move in self:
			if move.alternative_product_id:
				move.product_id = move.alternative_product_id

	@api.depends_context("workorder_id")
	def _compute_is_unlocked(self):
		workorder_id = self.env.context.get("workorder_id")
		workorder = self.env["mrp.workorder"].browse(workorder_id) if workorder_id else False
		for move in self:
			if not workorder:
				move.is_unlocked = True
				continue
			move.is_unlocked = workorder._is_move_unlocked(move)
