# -*- coding: utf-8 -*-
import secrets

from odoo import api, fields, models


class ItecApiKey(models.Model):
    _name = "itec.api.key"
    _description = "Itec API Key"
    _order = "id desc"

    name = fields.Char(
        string="Identificador",
        required=True,
        help="Nombre descriptivo de la integración (ej.: 'App ITEC móvil', "
             "'ETL nocturno', etc.).",
    )
    key = fields.Char(
        string="API Key",
        required=True,
        copy=False,
        index=True,
        default=lambda self: self._generate_key(),
        help="Token que el cliente debe enviar en el header X-API-Key. "
             "Se autogenera al abrir el formulario; usá 'Regenerar Key' "
             "para crear uno nuevo.",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Usuario asociado",
        ondelete="set null",
        help="Usuario en cuyo nombre se ejecutarán las operaciones cuando el "
             "endpoint use sudo()/with_user(). Si está vacío, se usa el usuario "
             "público del request.",
    )
    active = fields.Boolean(default=True)
    expires_on = fields.Date(
        string="Vence el",
        help="Si se setea, la clave deja de ser válida después de esta fecha.",
    )
    last_used = fields.Datetime(string="Último uso", readonly=True)
    note = fields.Text(string="Notas")

    _sql_constraints = [
        ("key_uniq", "unique(key)", "La API Key debe ser única."),
    ]

    @api.model
    def _generate_key(self):
        """Genera un token URL-safe de 48 caracteres."""
        return secrets.token_urlsafe(36)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("key"):
                vals["key"] = self._generate_key()
        return super().create(vals_list)

    def action_regenerate_key(self):
        """Regenera el token. Funciona tanto sobre registros guardados como
        sobre formularios en modo edición/creación (en ese caso se asigna
        en memoria y se persiste cuando el usuario guarda)."""
        for rec in self:
            rec.key = self._generate_key()
        return True

    @api.model
    def _validate(self, raw_key):
        """Devuelve el registro válido para `raw_key` o False.

        Acepta también la API Key global definida en el parámetro de sistema
        ``itec_api.api_key`` como fallback (no devuelve registro en ese caso,
        pero retorna ``True``).
        """
        if not raw_key:
            return False
        record = self.sudo().search(
            [("key", "=", raw_key), ("active", "=", True)], limit=1
        )
        if record:
            today = fields.Date.context_today(record)
            if record.expires_on and record.expires_on < today:
                return False
            record.sudo().write({"last_used": fields.Datetime.now()})
            return record
        # Fallback: parámetro de sistema con clave global
        global_key = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("itec_api.api_key")
        )
        if global_key and raw_key == global_key:
            return True
        return False
