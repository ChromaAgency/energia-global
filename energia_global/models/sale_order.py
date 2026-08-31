# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    workflow_substate = fields.Selection(
        [
            ("draft", "Cotización"),
            ("dibujo", "Dibujo"),
            ("oficina_tecnica", "Oficina Técnica"),
        ],
        string="Subestado",
        default="draft",
        tracking=True,
        copy=False,
        help="Subestado interno previo a la confirmación. "
        "No modifica el estado nativo de la orden de venta.",
    )

    workflow_substate_label = fields.Char(
        string="Subestado (etiqueta)",
        compute="_compute_workflow_substate_label",
    )

    @api.depends("workflow_substate")
    def _compute_workflow_substate_label(self):
        labels = dict(self._fields["workflow_substate"].selection)
        for order in self:
            order.workflow_substate_label = labels.get(order.workflow_substate, "")

    def _ensure_editable_substate(self):
        for order in self:
            if order.state not in ("draft", "sent"):
                raise UserError(
                    _(
                        "El subestado solo se puede modificar en cotizaciones "
                        "no confirmadas (orden %s)."
                    )
                    % order.display_name
                )

    def action_substate_to_dibujo(self):
        self._ensure_editable_substate()
        self.write({"workflow_substate": "dibujo"})
        return True

    def action_substate_to_oficina_tecnica(self):
        self._ensure_editable_substate()
        for order in self.filtered(lambda o: o.workflow_substate != "oficina_tecnica"):
            if order.workflow_substate not in ("draft", "dibujo"):
                raise UserError(
                    _("Solo se puede avanzar a Oficina Técnica desde Cotización o Dibujo.")
                )
        self.write({"workflow_substate": "oficina_tecnica"})
        return True

    def action_substate_back_to_dibujo(self):
        self._ensure_editable_substate()
        for order in self:
            if order.workflow_substate != "oficina_tecnica":
                raise UserError(
                    _("Solo se puede retroceder a Dibujo desde Oficina Técnica.")
                )
        self.write({"workflow_substate": "dibujo"})
        return True

    def action_substate_back_to_draft(self):
        self._ensure_editable_substate()
        for order in self:
            if order.workflow_substate != "dibujo":
                raise UserError(_("Solo se puede retroceder a Cotización desde Dibujo."))
        self.write({"workflow_substate": "draft"})
        return True
