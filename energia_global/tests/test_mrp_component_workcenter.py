# -*- coding: utf-8 -*-

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestMrpComponentWorkcenter(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.location_src = cls.env.ref("stock.stock_location_stock")
        cls.location_dest = cls.env["stock.location"].search(
            [
                ("usage", "=", "production"),
                ("company_id", "in", [False, cls.company.id]),
            ],
            limit=1,
        ) or cls.location_src

        cls.workcenter_a = cls.env["mrp.workcenter"].create({
            "name": "WC A",
            "company_id": cls.company.id,
        })
        cls.workcenter_b = cls.env["mrp.workcenter"].create({
            "name": "WC B",
            "company_id": cls.company.id,
        })

        cls.product_tmpl = cls.env["product.template"].create({
            "name": "Finished Product",
            "uom_id": cls.uom_unit.id,
        })
        cls.product = cls.product_tmpl.product_variant_id
        cls.replacement_category = cls.env["product.category"].create({
            "name": "Replacement Category",
        })
        cls.blocked_category = cls.env["product.category"].create({
            "name": "Blocked Replacement Category",
        })
        cls.component = cls.env["product.product"].create({
            "name": "Component 1",
            "uom_id": cls.uom_unit.id,
        })
        cls.alt_component = cls.env["product.product"].create({
            "name": "Component 1 Alt",
            "uom_id": cls.uom_unit.id,
            "categ_id": cls.replacement_category.id,
        })
        cls.category_component = cls.env["product.product"].create({
            "name": "Component Category Alt",
            "uom_id": cls.uom_unit.id,
            "categ_id": cls.replacement_category.id,
        })
        cls.blocked_component = cls.env["product.product"].create({
            "name": "Blocked Category Component",
            "uom_id": cls.uom_unit.id,
            "categ_id": cls.blocked_category.id,
        })

        cls.bom = cls.env["mrp.bom"].create({
            "product_tmpl_id": cls.product_tmpl.id,
            "product_qty": 1.0,
            "product_uom_id": cls.uom_unit.id,
            "type": "normal",
        })

        operation_model = cls.env["mrp.bom.line"]._fields["operation_id"].comodel_name
        cls.operation_a = cls.env[operation_model].create({
            "name": "Op A",
            "workcenter_id": cls.workcenter_a.id,
            "company_id": cls.company.id,
            "bom_id": cls.bom.id,
        })
        cls.operation_b = cls.env[operation_model].create({
            "name": "Op B",
            "workcenter_id": cls.workcenter_b.id,
            "company_id": cls.company.id,
            "bom_id": cls.bom.id,
        })
        cls.operator_user = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "MRP Operator",
            "login": "mrp_operator_component_test",
            "email": "mrp_operator_component_test@example.com",
            "group_ids": [
                (
                    6,
                    0,
                    [
                        cls.env.ref("base.group_user").id,
                        cls.env.ref("mrp.group_mrp_user").id,
                    ],
                )
            ],
        })

    def _create_move(self, **values):
        base_vals = {
            "description_picking": self.component.display_name,
            "product_id": self.component.id,
            "product_uom": self.uom_unit.id,
            "product_uom_qty": 1.0,
            "location_id": self.location_src.id,
            "location_dest_id": self.location_dest.id,
        }
        base_vals.update(values)
        return self.env["stock.move"].create(base_vals)

    def _create_production_with_component_move(self, component_qty=2.0):
        bom_line = self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.component.id,
            "product_qty": component_qty,
            "product_uom_id": self.uom_unit.id,
            "operation_id": self.operation_a.id,
        })
        production = self.env["mrp.production"].create({
            "name": "MO Component Progress",
            "company_id": self.company.id,
            "product_id": self.product.id,
            "product_uom_id": self.uom_unit.id,
            "product_qty": 1.0,
            "bom_id": self.bom.id,
            "location_src_id": self.location_src.id,
            "location_dest_id": self.location_dest.id,
        })
        production.action_confirm()
        move = production.move_raw_ids.filtered(lambda current_move: current_move.bom_line_id == bom_line)[:1]
        workorder = production.workorder_ids.filtered(
            lambda current_workorder: current_workorder.operation_id == self.operation_a
        )[:1] or production.workorder_ids[:1]
        self.assertTrue(move)
        self.assertTrue(workorder)
        return production, workorder, move

    def test_related_workcenter_from_operation(self):
        bom_line = self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.component.id,
            "product_qty": 1.0,
            "product_uom_id": self.uom_unit.id,
            "operation_id": self.operation_a.id,
        })
        move = self._create_move(bom_line_id=bom_line.id, operation_id=self.operation_a.id)
        move._compute_related_workcenter_ids()
        self.assertIn(self.workcenter_a, move.related_workcenter_ids)

    def test_related_workcenter_from_bom_line_operations(self):
        bom_line = self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.component.id,
            "product_qty": 1.0,
            "product_uom_id": self.uom_unit.id,
            "operation_ids": [(6, 0, [self.operation_a.id, self.operation_b.id])],
        })
        move = self._create_move(bom_line_id=bom_line.id)
        move._compute_related_workcenter_ids()
        self.assertIn(self.workcenter_a, move.related_workcenter_ids)
        self.assertIn(self.workcenter_b, move.related_workcenter_ids)

    def test_related_operations_from_bom_line_operations(self):
        bom_line = self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.component.id,
            "product_qty": 1.0,
            "product_uom_id": self.uom_unit.id,
            "operation_ids": [(6, 0, [self.operation_a.id, self.operation_b.id])],
        })
        move = self._create_move(bom_line_id=bom_line.id)
        move._compute_related_operation_ids()
        self.assertIn(self.operation_a, move.related_operation_ids)
        self.assertIn(self.operation_b, move.related_operation_ids)

    def test_related_operations_from_move_operation(self):
        move = self._create_move(operation_id=self.operation_a.id)
        move._compute_related_operation_ids()
        self.assertIn(self.operation_a, move.related_operation_ids)

    def test_operator_can_write_component_directly(self):
        bom_line = self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.component.id,
            "product_qty": 1.0,
            "product_uom_id": self.uom_unit.id,
            "operation_id": self.operation_a.id,
        })
        production = self.env["mrp.production"].create({
            "name": "MO Write Guard",
            "company_id": self.company.id,
            "product_id": self.product.id,
            "product_uom_id": self.uom_unit.id,
            "product_qty": 1.0,
            "bom_id": self.bom.id,
            "location_src_id": self.location_src.id,
            "location_dest_id": self.location_dest.id,
        })
        production.action_confirm()
        move = production.move_raw_ids.filtered(lambda current_move: current_move.bom_line_id == bom_line)[:1]
        self.assertTrue(move)

        move.with_user(self.operator_user).write({"product_id": self.alt_component.id})
        self.assertEqual(move.product_id, self.alt_component)

    def test_product_must_belong_to_replacement_category(self):
        bom_line = self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.component.id,
            "product_qty": 1.0,
            "product_uom_id": self.uom_unit.id,
            "operation_id": self.operation_a.id,
            "replacement_category_ids": [(6, 0, [self.replacement_category.id])],
        })
        production = self.env["mrp.production"].create({
            "name": "MO Replacement Category Validation",
            "company_id": self.company.id,
            "product_id": self.product.id,
            "product_uom_id": self.uom_unit.id,
            "product_qty": 1.0,
            "bom_id": self.bom.id,
            "location_src_id": self.location_src.id,
            "location_dest_id": self.location_dest.id,
        })
        production.action_confirm()
        move = production.move_raw_ids.filtered(lambda current_move: current_move.bom_line_id == bom_line)[:1]
        self.assertTrue(move)

        move.with_user(self.operator_user).write({"product_id": self.category_component.id})
        self.assertEqual(move.product_id, self.category_component)

        with self.assertRaises(UserError):
            move.with_user(self.operator_user).write({"product_id": self.blocked_component.id})

    def test_component_progress_and_production_totals(self):
        production, workorder, move = self._create_production_with_component_move(component_qty=2.0)

        self.assertFalse(move.component_is_finalized)
        self.assertEqual(move.component_finalization_state, "pending")
        self.assertIn("Etapa 1/1", move.component_operation_stage_label)
        self.assertEqual(production.component_total_planned_qty, 2.0)
        self.assertEqual(production.component_total_done_qty, 0.0)

        workorder.action_start_piece_time(move.id)
        workorder.action_stop_piece_time(move.id)

        self.assertTrue(move.component_is_finalized)
        self.assertEqual(move.component_finalization_state, "done")
        self.assertIn("Finalizado", move.component_operation_stage_label)
        self.assertEqual(production.component_total_done_qty, 1.0)
        self.assertEqual(production.component_total_remaining_qty, 1.0)

        workorder.action_start_piece_time(move.id)
        workorder.action_stop_piece_time(move.id)

        self.assertTrue(move.component_is_finalized)
        self.assertEqual(move.component_finalization_state, "done")
        self.assertEqual(production.component_total_done_qty, 2.0)
        self.assertEqual(production.component_total_remaining_qty, 0.0)
        self.assertEqual(production.component_total_progress_pct, 100.0)

    def test_component_totals_with_zero_target(self):
        production, workorder, move = self._create_production_with_component_move(component_qty=0.0)

        self.assertFalse(move.component_is_finalized)
        self.assertEqual(move.component_finalization_state, "pending")
        self.assertIn("Etapa 1/1", move.component_operation_stage_label)

        workorder.action_start_piece_time(move.id)
        workorder.action_stop_piece_time(move.id)

        self.assertTrue(move.component_is_finalized)
        self.assertEqual(move.component_finalization_state, "done")
        self.assertIn("Finalizado", move.component_operation_stage_label)
        self.assertEqual(production.component_total_planned_qty, 0.0)
        self.assertEqual(production.component_total_done_qty, 1.0)
        self.assertEqual(production.component_total_progress_pct, 100.0)

    def test_component_is_finalized_only_after_all_operations_done(self):
        bom_line = self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.component.id,
            "product_qty": 1.0,
            "product_uom_id": self.uom_unit.id,
            "operation_ids": [(6, 0, [self.operation_a.id, self.operation_b.id])],
        })
        production = self.env["mrp.production"].create({
            "name": "MO Finalization Multi Operation",
            "company_id": self.company.id,
            "product_id": self.product.id,
            "product_uom_id": self.uom_unit.id,
            "product_qty": 1.0,
            "bom_id": self.bom.id,
            "location_src_id": self.location_src.id,
            "location_dest_id": self.location_dest.id,
        })
        production.action_confirm()

        move = production.move_raw_ids.filtered(lambda current_move: current_move.bom_line_id == bom_line)[:1]
        workorder_a = production.workorder_ids.filtered(
            lambda current_workorder: current_workorder.operation_id == self.operation_a
        )[:1]
        workorder_b = production.workorder_ids.filtered(
            lambda current_workorder: current_workorder.operation_id == self.operation_b
        )[:1]

        self.assertTrue(move)
        self.assertTrue(workorder_a)
        self.assertTrue(workorder_b)
        self.assertFalse(move.component_is_finalized)
        self.assertIn("Etapa 1/2", move.component_operation_stage_label)

        workorder_a.action_start_piece_time(move.id)
        workorder_a.action_stop_piece_time(move.id)
        self.assertFalse(move.component_is_finalized)
        self.assertEqual(move.component_finalization_state, "pending")
        self.assertIn("Etapa 2/2", move.component_operation_stage_label)

        workorder_b.action_start_piece_time(move.id)
        workorder_b.action_stop_piece_time(move.id)
        self.assertTrue(move.component_is_finalized)
        self.assertEqual(move.component_finalization_state, "done")
        self.assertIn("Finalizado", move.component_operation_stage_label)

    def test_first_workorder_unlocked_for_multi_operation_move(self):
        bom_line = self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.component.id,
            "product_qty": 1.0,
            "product_uom_id": self.uom_unit.id,
            "operation_ids": [(6, 0, [self.operation_a.id, self.operation_b.id])],
        })
        production = self.env["mrp.production"].create({
            "name": "MO Blocking First WO",
            "company_id": self.company.id,
            "product_id": self.product.id,
            "product_uom_id": self.uom_unit.id,
            "product_qty": 1.0,
            "bom_id": self.bom.id,
            "location_src_id": self.location_src.id,
            "location_dest_id": self.location_dest.id,
        })
        production.action_confirm()
        move = production.move_raw_ids.filtered(lambda current_move: current_move.bom_line_id == bom_line)[:1]
        workorder_a = production.workorder_ids.filtered(
            lambda current_workorder: current_workorder.operation_id == self.operation_a
        )[:1]
        workorder_b = production.workorder_ids.filtered(
            lambda current_workorder: current_workorder.operation_id == self.operation_b
        )[:1]

        status_a = workorder_a.get_move_timer_status(move.id)
        status_b = workorder_b.get_move_timer_status(move.id)

        self.assertTrue(status_a["is_unlocked"])
        self.assertFalse(status_b["is_unlocked"])
        self.assertIn(workorder_a.display_name, status_b["blocked_by_text"])

    def test_second_workorder_unlocks_after_first_done(self):
        bom_line = self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.component.id,
            "product_qty": 1.0,
            "product_uom_id": self.uom_unit.id,
            "operation_ids": [(6, 0, [self.operation_a.id, self.operation_b.id])],
        })
        production = self.env["mrp.production"].create({
            "name": "MO Blocking Unlock Flow",
            "company_id": self.company.id,
            "product_id": self.product.id,
            "product_uom_id": self.uom_unit.id,
            "product_qty": 1.0,
            "bom_id": self.bom.id,
            "location_src_id": self.location_src.id,
            "location_dest_id": self.location_dest.id,
        })
        production.action_confirm()
        move = production.move_raw_ids.filtered(lambda current_move: current_move.bom_line_id == bom_line)[:1]
        workorder_a = production.workorder_ids.filtered(
            lambda current_workorder: current_workorder.operation_id == self.operation_a
        )[:1]
        workorder_b = production.workorder_ids.filtered(
            lambda current_workorder: current_workorder.operation_id == self.operation_b
        )[:1]

        workorder_a.action_start_piece_time(move.id)
        workorder_a.action_stop_piece_time(move.id)

        status_b = workorder_b.get_move_timer_status(move.id)
        self.assertTrue(status_b["is_unlocked"])
        workorder_b.action_start_piece_time(move.id)

    def test_unmapped_move_is_unlocked_on_any_workorder(self):
        production, workorder, move = self._create_production_with_component_move()
        move.write({"operation_id": False, "bom_line_id": False})
        move._compute_related_operation_ids()
        move._compute_related_workcenter_ids()

        status = workorder.get_move_timer_status(move.id)
        self.assertTrue(status["is_unlocked"])

    def test_component_summary_groups_required_qty_by_product(self):
        self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.component.id,
            "product_qty": 1.0,
            "product_uom_id": self.uom_unit.id,
            "operation_id": self.operation_a.id,
        })
        self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.component.id,
            "product_qty": 2.0,
            "product_uom_id": self.uom_unit.id,
            "operation_id": self.operation_a.id,
        })
        self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.alt_component.id,
            "product_qty": 3.0,
            "product_uom_id": self.uom_unit.id,
            "operation_id": self.operation_b.id,
        })

        production = self.env["mrp.production"].create({
            "name": "MO Component Summary",
            "company_id": self.company.id,
            "product_id": self.product.id,
            "product_uom_id": self.uom_unit.id,
            "product_qty": 1.0,
            "bom_id": self.bom.id,
            "location_src_id": self.location_src.id,
            "location_dest_id": self.location_dest.id,
        })
        production.action_confirm()

        summary_lines = production.component_summary_line_ids
        self.assertEqual(len(summary_lines), 2)

        component_line = summary_lines.filtered(lambda line: line.product_id == self.component)
        alt_component_line = summary_lines.filtered(lambda line: line.product_id == self.alt_component)

        self.assertEqual(component_line.required_qty, 3.0)
        self.assertEqual(alt_component_line.required_qty, 3.0)
