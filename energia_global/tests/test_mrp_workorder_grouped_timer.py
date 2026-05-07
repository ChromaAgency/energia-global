# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase


class TestMrpWorkorderGroupedTimer(TransactionCase):
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

        cls.workcenter = cls.env["mrp.workcenter"].create(
            {
                "name": "WC Grouped Timer",
                "company_id": cls.company.id,
                "behavior_type": "grouped",
                "grouping_field": "weld_group",
            }
        )

        cls.finished_tmpl = cls.env["product.template"].create(
            {
                "name": "Finished Grouped Timer",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.finished_product = cls.finished_tmpl.product_variant_id

        cls.component_a = cls.env["product.product"].create(
            {
                "name": "Component A",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.component_b = cls.env["product.product"].create(
            {
                "name": "Component B",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.component_c = cls.env["product.product"].create(
            {
                "name": "Component C",
                "uom_id": cls.uom_unit.id,
            }
        )

    def _create_workorder_with_moves(self):
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.finished_tmpl.id,
                "product_qty": 1.0,
                "product_uom_id": self.uom_unit.id,
                "type": "normal",
            }
        )
        operation_model = self.env["mrp.bom.line"]._fields["operation_id"].comodel_name
        operation = self.env[operation_model].create(
            {
                "name": "Operation Grouped Timer",
                "workcenter_id": self.workcenter.id,
                "company_id": self.company.id,
                "bom_id": bom.id,
            }
        )
        for component in (self.component_a, self.component_b, self.component_c):
            self.env["mrp.bom.line"].create(
                {
                    "bom_id": bom.id,
                    "product_id": component.id,
                    "product_qty": 1.0,
                    "product_uom_id": self.uom_unit.id,
                    "operation_id": operation.id,
                }
            )

        production = self.env["mrp.production"].create(
            {
                "name": "MO Grouped Timer",
                "company_id": self.company.id,
                "product_id": self.finished_product.id,
                "product_uom_id": self.uom_unit.id,
                "product_qty": 1.0,
                "bom_id": bom.id,
                "location_src_id": self.location_src.id,
                "location_dest_id": self.location_dest.id,
            }
        )
        production.action_confirm()

        workorder = production.workorder_ids[:1]
        self.assertTrue(workorder)
        moves = production.move_raw_ids.filtered(
            lambda move: move.product_id.id
            in {self.component_a.id, self.component_b.id, self.component_c.id}
        )
        moves_by_product = {
            move.product_id.id: move for move in moves
        }
        self.assertEqual(len(moves_by_product), 3)

        return workorder, moves_by_product

    def _get_running_move_ids(self, workorder):
        running = self.env["mrp.workcenter.productivity"].search(
            [
                ("workorder_id", "=", workorder.id),
                ("piece_state", "=", "working"),
                ("date_end", "=", False),
            ]
        )
        return set(running.mapped("move_id").ids)

    def test_grouped_start_uses_weld_group_from_workcenter(self):
        self.workcenter.write({"behavior_type": "grouped", "grouping_field": "weld_group"})
        workorder, moves = self._create_workorder_with_moves()

        move_a = moves[self.component_a.id]
        move_b = moves[self.component_b.id]
        move_c = moves[self.component_c.id]
        move_a.write({"weld_group": "W1", "cnc_number": "C1"})
        move_b.write({"weld_group": "W1", "cnc_number": "C2"})
        move_c.write({"weld_group": "W2", "cnc_number": "C1"})

        workorder.action_start_piece_time(move_a.id)

        self.assertSetEqual(self._get_running_move_ids(workorder), {move_a.id, move_b.id})

    def test_grouped_start_uses_cnc_number_from_workcenter(self):
        self.workcenter.write({"behavior_type": "grouped", "grouping_field": "cnc_number"})
        workorder, moves = self._create_workorder_with_moves()

        move_a = moves[self.component_a.id]
        move_b = moves[self.component_b.id]
        move_c = moves[self.component_c.id]
        move_a.write({"weld_group": "W1", "cnc_number": "C1"})
        move_b.write({"weld_group": "W2", "cnc_number": "C1"})
        move_c.write({"weld_group": "W1", "cnc_number": "C2"})

        workorder.action_start_piece_time(move_a.id)

        self.assertSetEqual(self._get_running_move_ids(workorder), {move_a.id, move_b.id})

    def test_grouped_start_falls_back_to_individual_without_group_value(self):
        self.workcenter.write({"behavior_type": "grouped", "grouping_field": "weld_group"})
        workorder, moves = self._create_workorder_with_moves()

        move_a = moves[self.component_a.id]
        move_b = moves[self.component_b.id]
        move_c = moves[self.component_c.id]
        move_a.write({"weld_group": False, "cnc_number": "C1"})
        move_b.write({"weld_group": "W1", "cnc_number": "C1"})
        move_c.write({"weld_group": "W1", "cnc_number": "C2"})

        workorder.action_start_piece_time(move_a.id)

        self.assertSetEqual(self._get_running_move_ids(workorder), {move_a.id})
