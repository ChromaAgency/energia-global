# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase


class TestMrpComponentWorkcenter(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.location_src = cls.env.ref("stock.stock_location_stock")
        cls.location_dest = cls.env.ref("stock.stock_location_production")

        cls.workcenter_a = cls.env["mrp.workcenter"].create({
            "name": "WC A",
            "company_id": cls.company.id,
        })
        cls.workcenter_b = cls.env["mrp.workcenter"].create({
            "name": "WC B",
            "company_id": cls.company.id,
        })

        operation_model = cls.env["mrp.bom.line"]._fields["operation_id"].comodel_name
        cls.operation_a = cls.env[operation_model].create({
            "name": "Op A",
            "workcenter_id": cls.workcenter_a.id,
            "company_id": cls.company.id,
        })
        cls.operation_b = cls.env[operation_model].create({
            "name": "Op B",
            "workcenter_id": cls.workcenter_b.id,
            "company_id": cls.company.id,
        })

        cls.product_tmpl = cls.env["product.template"].create({
            "name": "Finished Product",
            "type": "product",
            "uom_id": cls.uom_unit.id,
            "uom_po_id": cls.uom_unit.id,
        })
        cls.product = cls.product_tmpl.product_variant_id
        cls.component = cls.env["product.product"].create({
            "name": "Component 1",
            "type": "product",
            "uom_id": cls.uom_unit.id,
            "uom_po_id": cls.uom_unit.id,
        })
        cls.alt_component = cls.env["product.product"].create({
            "name": "Component 1 Alt",
            "type": "product",
            "uom_id": cls.uom_unit.id,
            "uom_po_id": cls.uom_unit.id,
        })

        cls.bom = cls.env["mrp.bom"].create({
            "product_tmpl_id": cls.product_tmpl.id,
            "product_qty": 1.0,
            "product_uom_id": cls.uom_unit.id,
            "type": "normal",
        })

    def _create_move(self, **values):
        base_vals = {
            "name": self.component.display_name,
            "product_id": self.component.id,
            "product_uom": self.uom_unit.id,
            "product_uom_qty": 1.0,
            "location_id": self.location_src.id,
            "location_dest_id": self.location_dest.id,
        }
        base_vals.update(values)
        return self.env["stock.move"].create(base_vals)

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

    def test_alternative_components_on_move(self):
        bom_line = self.env["mrp.bom.line"].create({
            "bom_id": self.bom.id,
            "product_id": self.component.id,
            "product_qty": 1.0,
            "product_uom_id": self.uom_unit.id,
            "alternative_product_ids": [(6, 0, [self.alt_component.id])],
        })
        move = self._create_move(bom_line_id=bom_line.id)
        move._compute_alternative_products()
        self.assertIn(self.alt_component, move.alternative_product_ids)
        move.alternative_product_id = self.alt_component
        move._onchange_alternative_product_id()
        self.assertEqual(move.product_id, self.alt_component)
