from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockMove(models.Model):
	_inherit = "stock.move"

	final_product_id = fields.Many2one(
		"product.product",
		compute="_compute_final_product_id",
		store=True,
		readonly=True,
		string="Producto Intermedio (Visual)",
	)

	@api.depends("bom_line_id", "bom_line_id.visual_intermediate_product_id")
	def _compute_final_product_id(self):
		for move in self:
			move.final_product_id = move.bom_line_id.visual_intermediate_product_id

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
		compute="_compute_alternative_product_ids",
		readonly=True,
		string="Alternative Components",
	)
	alternative_product_id = fields.Many2one(
		"product.product",
		string="Alternative Component",
		domain="[('id', 'in', alternative_product_ids)]",
		compute="_compute_alternative_product_id",
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
	is_component_swap_allowed = fields.Boolean(
		string="Can Swap Component",
		compute="_compute_is_component_swap_allowed",
	)
	component_is_finalized = fields.Boolean(
		string="Componente Finalizado",
		compute="_compute_component_finalization_state",
		readonly=True,
	)
	component_finalization_state = fields.Selection(
		[
			("pending", "Pendiente"),
			("done", "Finalizado"),
		],
		string="Estado de Componente (Interno)",
		compute="_compute_component_finalization_state",
		readonly=True,
	)
	component_finalization_state_label = fields.Char(
		string="Estado de Componente",
		compute="_compute_component_finalization_state",
		readonly=True,
	)
	component_operation_stage_label = fields.Char(
		string="Etapa de Operación",
		compute="_compute_component_finalization_state",
		readonly=True,
	)
	component_piece_total = fields.Float(
		string="Component Target",
		compute="_compute_component_progress",
		readonly=True,
	)
	component_piece_done = fields.Float(
		string="Component Done",
		compute="_compute_component_progress",
		readonly=True,
	)
	component_progress_pct = fields.Float(
		string="Component Progress (%)",
		compute="_compute_component_progress",
		readonly=True,
	)
	component_partial_state = fields.Selection(
		[
			("not_started", "No Iniciado"),
			("in_progress", "En Curso"),
			("partial", "Parcial"),
			("done", "Completo"),
		],
		string="Partial Status",
		compute="_compute_component_progress",
		readonly=True,
	)
	component_partial_state_label = fields.Char(
		string="Partial Status Label",
		compute="_compute_component_progress",
		readonly=True,
	)

	@api.depends_context("uid")
	def _compute_is_component_swap_allowed(self):
		is_allowed = self.env.user.has_group("mrp.group_mrp_manager")
		for move in self:
			move.is_component_swap_allowed = is_allowed

	@api.depends("bom_line_id", "bom_line_id.alternative_product_ids")
	def _compute_alternative_product_ids(self):
		for move in self:
			alternatives = move.bom_line_id.alternative_product_ids
			move.alternative_product_ids = alternatives

	@api.depends("bom_line_id", "bom_line_id.alternative_product_ids", "product_id")
	def _compute_alternative_product_id(self):
		for move in self:
			alternatives = move.bom_line_id.alternative_product_ids
			if not alternatives:
				move.alternative_product_id = False
				continue
			if move.product_id and move.product_id in alternatives:
				move.alternative_product_id = move.product_id
				continue
			if move.alternative_product_id and move.alternative_product_id in alternatives:
				continue
			move.alternative_product_id = alternatives[:1]

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

	def _get_required_workorders_for_completion(self):
		self.ensure_one()
		production = self.raw_material_production_id
		if not production:
			return self.env["mrp.workorder"]

		workorders = production.workorder_ids.filtered(lambda workorder: workorder.state != "cancel")
		operations = self.related_operation_ids
		if operations:
			required = workorders.filtered(lambda workorder: workorder.operation_id in operations)
			if required:
				return required
		if self.workorder_id and self.workorder_id.state != "cancel":
			return self.workorder_id
		return self.env["mrp.workorder"]

	@api.depends(
		"related_operation_ids",
		"operation_id",
		"workorder_id",
		"raw_material_production_id",
		"raw_material_production_id.workorder_ids",
		"raw_material_production_id.workorder_ids.state",
	)
	def _compute_component_finalization_state(self):
		state_labels = {
			"pending": _("Pendiente"),
			"done": _("Finalizado"),
		}
		productivity_model = self.env["mrp.workcenter.productivity"]
		for move in self:
			required_workorders = move._get_required_workorders_for_completion().sorted(
				key=lambda workorder: (workorder.sequence, workorder.id)
			)
			is_done = False
			stage_label = _("Sin operaciones")
			if required_workorders:
				done_rows = productivity_model.search(
					[
						("move_id", "=", move.id),
						("workorder_id", "in", required_workorders.ids),
						("piece_state", "=", "done"),
					]
				)
				done_workorder_ids = set(done_rows.mapped("workorder_id").ids)
				is_done = set(required_workorders.ids).issubset(done_workorder_ids)

				completed_steps = 0
				for workorder in required_workorders:
					if workorder.id not in done_workorder_ids:
						break
					completed_steps += 1

				total_steps = len(required_workorders)
				if is_done:
					stage_label = _("Etapa %s/%s - Finalizado") % (total_steps, total_steps)
				else:
					next_index = min(completed_steps + 1, total_steps)
					next_workorder = required_workorders[completed_steps] if completed_steps < total_steps else required_workorders[-1]
					next_operation_name = next_workorder.operation_id.display_name or next_workorder.display_name
					stage_label = _("Etapa %s/%s - %s") % (next_index, total_steps, next_operation_name)
			else:
				is_done = bool(
					productivity_model.search_count(
						[("move_id", "=", move.id), ("piece_state", "=", "done")]
					)
				)
				if is_done:
					stage_label = _("Etapa 1/1 - Finalizado")
			state = "done" if is_done else "pending"
			move.component_is_finalized = is_done
			move.component_finalization_state = state
			move.component_finalization_state_label = state_labels[state]
			move.component_operation_stage_label = stage_label

	def _get_component_progress_counts(self):
		counts = {
			"done": {},
			"active": {},
		}
		if not self.ids:
			return counts

		productivity_model = self.env["mrp.workcenter.productivity"]
		done_rows = productivity_model.read_group(
			[("move_id", "in", self.ids), ("piece_state", "=", "done")],
			["move_id"],
			["move_id"],
		)
		for row in done_rows:
			if row.get("move_id"):
				counts["done"][row["move_id"][0]] = row.get("move_id_count", 0)

		active_rows = productivity_model.read_group(
			[("move_id", "in", self.ids), ("piece_state", "in", ["working", "paused"])],
			["move_id"],
			["move_id"],
		)
		for row in active_rows:
			if row.get("move_id"):
				counts["active"][row["move_id"][0]] = row.get("move_id_count", 0)

		return counts

	@api.depends("product_uom_qty")
	def _compute_component_progress(self):
		state_labels = {
			"not_started": _("No iniciado"),
			"in_progress": _("En curso"),
			"partial": _("Parcial"),
			"done": _("Completo"),
		}
		counts = self._get_component_progress_counts()
		for move in self:
			target = max(move.product_uom_qty or 0.0, 0.0)
			done = float(counts["done"].get(move.id, 0))
			done_capped = min(done, target) if target else done

			if target:
				progress = min((done_capped / target) * 100.0, 100.0)
			else:
				progress = 100.0 if done_capped else 0.0

			if done_capped <= 0:
				state = "in_progress" if counts["active"].get(move.id) else "not_started"
			elif target and done_capped >= target:
				state = "done"
			elif not target:
				state = "done"
			else:
				state = "partial"

			move.component_piece_total = target
			move.component_piece_done = done_capped
			move.component_progress_pct = progress
			move.component_partial_state = state
			move.component_partial_state_label = state_labels[state]

	def _check_component_swap_permissions(self):
		if not self.env.user.has_group("mrp.group_mrp_manager"):
			raise UserError(
				_("Solo los responsables de fabricación pueden intercambiar componentes alternativos.")
			)

	def _should_guard_component_changes(self):
		return not self.env.su and not self.env.context.get("skip_component_swap_permission")

	def _check_component_write_permissions(self, vals):
		if not self._should_guard_component_changes():
			return
		protected_fields = {"product_id", "alternative_product_id"}
		if not (protected_fields & set(vals.keys())):
			return
		moves_to_protect = self.filtered(
			lambda move: move.raw_material_production_id and move.bom_line_id
		)
		if not moves_to_protect:
			return
		if not self.env.user.has_group("mrp.group_mrp_manager"):
			raise UserError(
				_("Solo los responsables de fabricación pueden modificar el componente en líneas MRP.")
			)

	def _sync_component_summary_for_productions(self, extra_productions=False):
		productions = self.mapped("raw_material_production_id")
		if extra_productions:
			productions |= extra_productions
		if productions:
			productions.sudo()._sync_component_summary_lines()

	@api.model_create_multi
	def create(self, vals_list):
		moves = super().create(vals_list)
		moves._sync_component_summary_for_productions()
		return moves

	def write(self, vals):
		self._check_component_write_permissions(vals)
		summary_fields = {"raw_material_production_id", "product_id", "product_uom", "product_uom_qty", "state"}
		previous_productions = self.env["mrp.production"]
		if set(vals) & summary_fields:
			previous_productions = self.mapped("raw_material_production_id")
		result = super().write(vals)
		if set(vals) & summary_fields:
			self._sync_component_summary_for_productions(extra_productions=previous_productions)
		return result

	def unlink(self):
		productions = self.mapped("raw_material_production_id")
		result = super().unlink()
		if productions:
			productions.sudo()._sync_component_summary_lines()
		return result

	def action_use_alternative_component(self):
		for move in self:
			move._check_component_swap_permissions()
			alternative = move.alternative_product_id or move.alternative_product_ids[:1]
			if not alternative:
				raise UserError(_("No hay componente alternativo configurado para esta línea."))
			move.product_id = alternative
		return True

	def action_restore_original_component(self):
		for move in self:
			move._check_component_swap_permissions()
			original = move.bom_line_id.product_id
			if not original:
				raise UserError(_("No se encontró componente original de la línea de lista de materiales."))
			move.product_id = original
		return True

	@api.depends_context("workorder_id")
	def _compute_is_unlocked(self):
		workorder_id = self.env.context.get("workorder_id")
		workorder = self.env["mrp.workorder"].browse(workorder_id) if workorder_id else False
		for move in self:
			if not workorder:
				move.is_unlocked = True
				continue
			move.is_unlocked = workorder._is_move_unlocked(move)
