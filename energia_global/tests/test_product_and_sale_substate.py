# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProductTemplateFields(TransactionCase):
    def test_custom_product_fields_persist(self):
        thickness = self.env["thickness.measurements"].create({"name": "2mm"})
        client_tag = self.env["product.client.tag"].create({"name": "Cliente Demo"})
        product = self.env["product.template"].create(
            {
                "name": "Chapa test",
                "sheet_type": "Galvanizada",
                "broad": 1.2,
                "long": 2.4,
                "superficie": 2.88,
                "gross_weight": 12.5,
                "thickness_measurements": thickness.id,
                "client_tag_ids": [(6, 0, client_tag.ids)],
            }
        )
        self.assertEqual(product.sheet_type, "Galvanizada")
        self.assertEqual(product.broad, 1.2)
        self.assertEqual(product.long, 2.4)
        self.assertEqual(product.superficie, 2.88)
        self.assertEqual(product.gross_weight, 12.5)
        self.assertEqual(product.thickness_measurements, thickness)
        self.assertEqual(product.client_tag_ids, client_tag)


@tagged("post_install", "-at_install")
class TestSaleWorkflowSubstate(TransactionCase):
    def test_substate_forward_and_backward(self):
        if "sale.order" not in self.env:
            self.skipTest("sale module not installed")
        partner = self.env["res.partner"].create({"name": "Cliente Test"})
        order = self.env["sale.order"].create({"partner_id": partner.id})
        self.assertEqual(order.workflow_substate, "draft")

        order.action_substate_to_dibujo()
        self.assertEqual(order.workflow_substate, "dibujo")

        order.action_substate_to_oficina_tecnica()
        self.assertEqual(order.workflow_substate, "oficina_tecnica")

        order.action_substate_back_to_dibujo()
        self.assertEqual(order.workflow_substate, "dibujo")

        order.action_substate_back_to_draft()
        self.assertEqual(order.workflow_substate, "draft")

    def test_skip_sent_and_jump_to_oficina_tecnica(self):
        partner = self.env["res.partner"].create({"name": "Cliente Test 2"})
        order = self.env["sale.order"].create({"partner_id": partner.id})
        order.action_substate_to_oficina_tecnica()
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.workflow_substate, "oficina_tecnica")
