# -*- coding: utf-8 -*-
"""
Endpoints REST nativos para crear / actualizar productos vía Postman u otra
app.

Endpoints disponibles
---------------------
* ``POST   /api/v1/itec/products``                  -> Crea ``product.template``
* ``PATCH  /api/v1/itec/products/<default_code>``   -> Actualiza por code
* ``GET    /api/v1/itec/products/<default_code>``   -> Lectura básica
* ``POST   /itec-api/create/product``               -> Compat (REST plano)
* ``POST   /itec-api/update/product``               -> Compat (REST plano)

Auth: header ``X-API-Key`` (modelo ``itec.api.key`` o parámetro de sistema
``itec_api.api_key`` como fallback).
"""

import base64
import functools
import json
import logging

from werkzeug.wrappers import Response

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

CORS = "*"


# ---------------------------------------------------------------------------
# Helpers a nivel módulo
# ---------------------------------------------------------------------------
def _to_bool(value):
    """Acepta booleanos, strings 'true'/'false'/'1'/'0' o None."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "y", "si", "sí"):
            return True
        if v in ("false", "0", "no", "n", ""):
            return False
    return None


def _json_response(data, status=200):
    """Construye una respuesta HTTP con cuerpo JSON y headers CORS."""
    response = Response(
        json.dumps(data, default=str),
        status=status,
        mimetype="application/json",
    )
    response.headers["Access-Control-Allow-Origin"] = CORS
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, X-API-Key, Authorization"
    )
    response.headers["Access-Control-Allow-Methods"] = (
        "GET, POST, PATCH, OPTIONS"
    )
    return response


def _error(message, status=400, **extra):
    payload = {"status": "Error", "message": message}
    payload.update(extra)
    return _json_response(payload, status=status)


def _load_payload():
    """Lee y parsea el body como JSON. Devuelve (payload, error_response)."""
    raw = request.httprequest.get_data(cache=False, as_text=True) or ""
    if not raw.strip():
        return {}, None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as exc:
        return None, _error(f"Body JSON inválido: {exc}", status=400)
    if not isinstance(data, dict):
        return None, _error(
            "El body debe ser un objeto JSON al primer nivel.", status=400
        )
    return data, None


def api_key_required(func):
    """Valida el header ``X-API-Key`` antes de ejecutar el endpoint.

    Si la validación es exitosa, guarda el registro ``itec.api.key`` (cuando
    existe) en ``request.itec_api_key`` para que el endpoint pueda usar el
    ``user_id`` asociado al firmar las operaciones (chatter, tracking, etc.).
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        raw_key = request.httprequest.headers.get("X-API-Key") or (
            request.httprequest.headers.get("Authorization", "").removeprefix(
                "Bearer "
            )
        )
        valid = request.env["itec.api.key"].sudo()._validate(raw_key)
        if not valid:
            _logger.warning(
                "Itec API: rechazado por API key inválida desde %s",
                request.httprequest.remote_addr,
            )
            return _error("API Key inválida o ausente.", status=401)
        # `valid` puede ser un record (clave del modelo) o True (clave global
        # del parámetro de sistema). Guardamos el record solo en el primer caso.
        setattr(
            request,
            "itec_api_key",
            valid if hasattr(valid, "_name") else None,
        )
        return func(self, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Controlador
# ---------------------------------------------------------------------------
class ItecApiController(http.Controller):

    # ---------------- helpers de identidad ----------------
    def _get_api_user(self):
        """Devuelve el ``res.users`` asociado a la API Key actual o ``False``.

        Solo aplica cuando la clave proviene del modelo ``itec.api.key``; si
        se autenticó por el parámetro de sistema global ``itec_api.api_key``,
        no hay usuario asociado y se devuelve ``False`` (cae en el usuario
        público del request).
        """
        api_key = getattr(request, "itec_api_key", None)
        if api_key and api_key.user_id:
            return api_key.user_id
        return False

    def _env_as_api_user(self):
        """Devuelve un env con ``env.user`` apuntando al usuario asociado.

        Esto hace que ``message_post`` automáticos del chatter, los
        ``tracking`` y ``create_uid`` / ``write_uid`` queden firmados por ese
        usuario en lugar de ``Public user``. Combinar con ``.sudo()`` cuando
        haga falta saltear ACLs.
        """
        user = self._get_api_user()
        if user:
            return request.env(user=user.id)
        return request.env

    # ---------------- helpers de mapeo ----------------
    def _resolve_category(self, name):
        if not name:
            return False
        category = (
            request.env["product.category"]
            .sudo()
            .search([("name", "=", name)], limit=1)
        )
        return category.id if category else False

    def _resolve_product_tags(self, tag_value):
        """Devuelve un comando M2M ``[(6, 0, [ids])]`` o False si nada matchea."""
        if not tag_value:
            return False
        if isinstance(tag_value, str):
            names = [tag_value]
        elif isinstance(tag_value, (list, tuple)):
            names = [str(x) for x in tag_value if x]
        else:
            return False
        if not names:
            return False
        tags = (
            request.env["product.tag"]
            .sudo()
            .search([("name", "in", names)])
        )
        if not tags:
            return False
        return [(6, 0, tags.ids)]

    def _resolve_thickness(self, name):
        if not name:
            return False
        if "thickness.measurements" not in request.env:
            return False
        record = (
            request.env["thickness.measurements"]
            .sudo()
            .search([("name", "=", name)], limit=1)
        )
        return record.id if record else False

    def _resolve_manufacture_route(self):
        """Devuelve la ruta de fabricación más confiable disponible."""
        route = request.env.ref(
            "mrp.route_warehouse0_manufacture", raise_if_not_found=False
        )
        if route:
            return route
        return (
            request.env["stock.route"]
            .sudo()
            .search(
                [
                    "|",
                    ("name", "=", "Manufacture"),
                    ("name", "=", "Fabricar"),
                ],
                limit=1,
            )
        )

    def _set_if_field(self, target, key, value, model_fields):
        """Asigna ``target[key] = value`` solo si el modelo tiene ese campo."""
        if key in model_fields:
            target[key] = value

    def _normalize_solidworks_payload(self, payload):
        """Aplica aliases mínimos para compatibilidad con gui.py.

        Regla actual:
        - ``surface`` -> ``superficie`` (solo si ``superficie`` no está presente).
        """
        if not isinstance(payload, dict):
            return {}
        if "surface" in payload and "superficie" not in payload:
            payload["superficie"] = payload["surface"]
        return payload

    def _merge_image_1920(self, payload, data, model_fields):
        """Decodifica ``image_1920`` (Base64 o ``data:...;base64,...``) y lo
        deja en ``data``. Devuelve una respuesta HTTP de error si la
        decodificación falla, o ``None`` si no aplica / fue correcto.

        Se usa tanto en create como en update para evitar duplicación.
        """
        if "image_1920" not in payload:
            return None
        if "image_1920" not in model_fields:
            return None
        raw = payload["image_1920"]
        if isinstance(raw, str) and raw.startswith("data:"):
            raw = raw.split(",", 1)[-1]
        try:
            data["image_1920"] = base64.b64encode(base64.b64decode(raw))
        except Exception:
            return _error("image_1920 no es un base64 válido.", status=400)
        return None

    def _build_create_data(self, payload, model_fields):
        """Convierte el payload REST en el dict para
        ``product.template.create()``. Devuelve ``(data, error_response)``."""
        data = {}

        # --- Pasthrough de campos directos (solo si existen en el modelo) ---
        passthrough = (
            "sheet_type", "weight", "broad", "long", "superficie",
            "description", "service_policy", "invoice_policy",
            "expense_policy", "uom_id", "uom_po_id", "force_currency_id",
            "l10n_ar_ncm_code", "barcode", "standard_price", "list_price",
            "product_route", "gross_weight", "volume",
        )
        for key in passthrough:
            if key in payload:
                self._set_if_field(data, key, payload.get(key), model_fields)

        # --- Booleanos ---
        for key in ("sale_ok", "purchase_ok"):
            if key in payload:
                value = _to_bool(payload.get(key))
                if value is None:
                    return None, _error(
                        f"El valor de '{key}' debe ser booleano.", status=400
                    )
                self._set_if_field(data, key, value, model_fields)

        # --- Categoría: el código original siempre fuerza "Producto Fabricado" ---
        if "categ_id" in payload:
            categ_id = self._resolve_category("Producto Fabricado")
            if not categ_id:
                return None, _error(
                    "La categoría 'Producto Fabricado' no existe en el sistema.",
                    status=404,
                )
            data["categ_id"] = categ_id

        # --- Tags ---
        if "product_tag_ids" in payload and "product_tag_ids" in model_fields:
            tag_command = self._resolve_product_tags(payload["product_tag_ids"])
            if tag_command is False:
                return None, _error(
                    "La etiqueta ingresada no existe en el sistema.",
                    status=404,
                )
            data["product_tag_ids"] = tag_command

        # --- Thickness (modelo custom de EnergiaGlobal) ---
        if "thickness" in payload:
            if "thickness_measurements" not in model_fields:
                pass  # módulo de espesores no instalado, lo ignoro
            else:
                tid = self._resolve_thickness(payload["thickness"])
                if not tid:
                    return None, _error(
                        "El espesor ingresado no existe en el sistema.",
                        status=404,
                    )
                data["thickness_measurements"] = tid

        err_img = self._merge_image_1920(payload, data, model_fields)
        if err_img is not None:
            return None, err_img

        # --- Tipo de producto (Odoo 18+: type='consu' + is_storable=True) ---
        data["tracking"] = "none"
        data["type"] = "consu"
        if "is_storable" in model_fields:
            data["is_storable"] = True

        # --- Ruta de fabricación ---
        route = self._resolve_manufacture_route()
        if route and "route_ids" in model_fields:
            data["route_ids"] = [(6, 0, [route.id])]

        return data, None

    def _build_update_data(self, payload, model_fields):
        """Variante para ``write()`` (no fuerza tipo, ni ruta, ni tracking)."""
        data = {}

        passthrough = (
            "name", "sheet_type", "weight", "broad", "long", "superficie",
            "description", "product_route", "service_policy",
            "invoice_policy", "expense_policy", "uom_id", "uom_po_id",
            "force_currency_id", "l10n_ar_ncm_code", "barcode",
            "standard_price", "list_price", "tracking", "gross_weight",
            "volume",
        )
        for key in passthrough:
            if key in payload:
                self._set_if_field(data, key, payload[key], model_fields)

        for key in ("sale_ok", "purchase_ok"):
            if key in payload:
                value = _to_bool(payload[key])
                if value is None:
                    return None, _error(
                        f"El valor de '{key}' debe ser booleano.", status=400
                    )
                self._set_if_field(data, key, value, model_fields)

        if "categ_id" in payload:
            categ_id = self._resolve_category("Producto Fabricado")
            if not categ_id:
                return None, _error(
                    "La categoría 'Producto Fabricado' no existe en el sistema.",
                    status=404,
                )
            data["categ_id"] = categ_id

        if "product_tag_ids" in payload and "product_tag_ids" in model_fields:
            tag_command = self._resolve_product_tags(payload["product_tag_ids"])
            if tag_command is False:
                return None, _error(
                    "La etiqueta ingresada no existe en el sistema.",
                    status=404,
                )
            data["product_tag_ids"] = tag_command

        if "thickness" in payload and "thickness_measurements" in model_fields:
            tid = self._resolve_thickness(payload["thickness"])
            if not tid:
                return None, _error(
                    "El espesor ingresado no existe en el sistema.", status=404,
                )
            data["thickness_measurements"] = tid

        err_img = self._merge_image_1920(payload, data, model_fields)
        if err_img is not None:
            return None, err_img

        return data, None

    def _create_bom(self, product, lines):
        """Crea ``mrp.bom`` con sus líneas. Devuelve (bom, error_response)."""
        if not lines:
            return False, None
        env = self._env_as_api_user()
        bom = (
            env["mrp.bom"]
            .sudo()
            .create(
                {
                    "product_tmpl_id": product.id,
                    "product_qty": 1,
                    "product_uom_id": product.uom_id.id,
                }
            )
        )
        for rec in lines:
            default_code = rec.get("default_code")
            component = (
                env["product.template"]
                .sudo()
                .search([("default_code", "=", default_code)], limit=1)
            )
            if not component:
                return None, _error(
                    "El producto requerido para la lista de materiales no "
                    f"existe en el sistema: {rec.get('name') or default_code}",
                    status=404,
                )
            env["mrp.bom.line"].sudo().create(
                {
                    "product_id": component.product_variant_id.id,
                    "bom_id": bom.id,
                    "product_qty": rec.get("product_qty", 1),
                }
            )
        return bom, None

    def _create_orderpoint(self, product, route):
        """Crea ``stock.warehouse.orderpoint`` (regla de abastecimiento)."""
        if not route:
            return
        env = self._env_as_api_user()
        warehouse = env["stock.warehouse"].sudo().search([], limit=1)
        if not warehouse:
            return
        env["stock.warehouse.orderpoint"].sudo().create(
            {
                "product_id": product.product_variant_id.id,
                "location_id": warehouse.lot_stock_id.id,
                "product_min_qty": 0,
                "product_max_qty": 0,
                # En Odoo 19 `qty_multiple=0` puede disparar ValueError
                # dependiendo de validaciones del modelo de orderpoint.
                "warehouse_id": warehouse.id,
                "route_id": route.id,
                "trigger": "auto",
                "company_id": request.env.company.id,
            }
        )

    def _serialize_product(self, product):
        return {
            "id": product.id,
            "default_code": product.default_code,
            "name": product.name,
            "barcode": product.barcode or False,
            "list_price": product.list_price,
            "standard_price": product.standard_price,
            "categ_id": product.categ_id.name if product.categ_id else False,
            "uom_id": product.uom_id.name if product.uom_id else False,
            "active": product.active,
        }

    # ---------------- Lógica reusable de create / update ----------------
    def _do_create(self, payload):
        if not isinstance(payload, dict):
            return _error(
                "El body debe ser un objeto JSON al primer nivel.", status=400
            )
        if not payload.get("name"):
            return _error(
                "El parámetro 'name' es requerido.", status=400
            )
        payload = self._normalize_solidworks_payload(payload)

        env = self._env_as_api_user()
        ProductTemplate = env["product.template"].sudo()
        model_fields = ProductTemplate._fields
        requested_code = payload.get('default_code')
        existing = ProductTemplate.search(
            [("default_code", "=", requested_code)], limit=1
        )
        if requested_code and existing:
            return _json_response(
                {
                    "status": "Conflict",
                    "message": "Ya existe un producto con ese default_code.",
                    "default_code": existing.default_code,
                    "name": existing.name,
                    "id": existing.id,
                },
                status=409,
            )

        data, err = self._build_create_data(payload, model_fields)
        if err is not None:
            return err
        if data is None:
            return _error("No se pudo construir el producto.", status=400)

        data["name"] = payload.get("name")
        data["default_code"] = requested_code

        try:
            product = ProductTemplate.create(data)
        except Exception as exc:
            _logger.exception("Itec API: error creando product.template")
            return _error(f"Error creando el producto: {exc}", status=500)

        bom, err = self._create_bom(product, payload.get("bill_of_materials"))
        if err is not None:
            return err

        try:
            self._create_orderpoint(product, self._resolve_manufacture_route())
        except Exception as exc:
            _logger.exception("Itec API: error creando orderpoint")
            return _error(
                f"Producto creado pero falló la regla de abastecimiento: {exc}",
                status=500,
                id=product.id,
                default_code=product.default_code,
            )

        return _json_response(
            {
                "status": "Ok",
                "message": "Producto creado",
                "id": product.id,
                "default_code": product.default_code,
                "bom_id": bom.id if bom else False,
            },
            status=201,
        )

    def _do_update(self, default_code, payload):
        if not default_code:
            return _error(
                "El parámetro 'default_code' es requerido.", status=400
            )
        if not isinstance(payload, dict):
            return _error(
                "El body debe ser un objeto JSON al primer nivel.", status=400
            )
        payload = self._normalize_solidworks_payload(payload)
        env = self._env_as_api_user()
        ProductTemplate = env["product.template"].sudo()
        product = ProductTemplate.search(
            [("default_code", "=", default_code)], limit=1
        )
        if not product:
            return _error(
                f"No existe ningún producto con default_code '{default_code}'.",
                status=404,
            )

        data, err = self._build_update_data(payload, ProductTemplate._fields)
        if err is not None:
            return err
        if data is None:
            return _error("No se pudo construir la actualización.", status=400)

        try:
            product.write(data)
        except Exception as exc:
            _logger.exception("Itec API: error actualizando product.template")
            return _error(f"Error actualizando el producto: {exc}", status=500)

        return _json_response(
            {
                "status": "Ok",
                "message": "Producto actualizado",
                "id": product.id,
                "default_code": product.default_code,
                "datos_actualizados": data,
                "lista_de_materiales": payload.get("bill_of_materials", []),
            }
        )

    # =========================================================================
    # Endpoints REST nuevos (versionados)
    # =========================================================================
    @http.route(
        "/api/v1/itec/products",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        cors=CORS,
        save_session=False,
    )
    @api_key_required
    def create_product(self, **_):
        payload, err = _load_payload()
        if err is not None:
            return err
        if payload is None:
            return _error("Body JSON inválido.", status=400)
        return self._do_create(payload)

    @http.route(
        "/api/v1/itec/products/<string:default_code>",
        type="http",
        auth="public",
        methods=["PATCH", "POST"],
        csrf=False,
        cors=CORS,
        save_session=False,
    )
    @api_key_required
    def update_product(self, default_code, **_):
        payload, err = _load_payload()
        if err is not None:
            return err
        if payload is None:
            return _error("Body JSON inválido.", status=400)
        return self._do_update(default_code, payload)

    @http.route(
        "/api/v1/itec/products/<string:default_code>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        cors=CORS,
        save_session=False,
    )
    @api_key_required
    def get_product(self, default_code, **_):
        product = (
            request.env["product.template"]
            .sudo()
            .search([("default_code", "=", default_code)], limit=1)
        )
        if not product:
            return _error(
                f"No existe ningún producto con default_code '{default_code}'.",
                status=404,
            )
        return _json_response(
            {"status": "Ok", "product": self._serialize_product(product)}
        )

    # ---- Preflight CORS ----
    @http.route(
        [
            "/api/v1/itec/products",
            "/api/v1/itec/products/<string:default_code>",
            "/itec-api/create/product",
            "/itec-api/update/product",
        ],
        type="http",
        auth="public",
        methods=["OPTIONS"],
        csrf=False,
        cors=CORS,
        save_session=False,
    )
    def cors_preflight(self, **_):
        return _json_response({"ok": True})

    # =========================================================================
    # Endpoints LEGADOS de compatibilidad (mismas URLs que api_itec, pero
    # ahora aceptan body REST plano sin envelope JSON-RPC)
    # =========================================================================
    @http.route(
        "/itec-api/create/product",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        cors=CORS,
        save_session=False,
    )
    @api_key_required
    def legacy_create_product(self, **_):
        _logger.warning(
            "Itec API: usando endpoint /itec-api/create/product (compatibilidad SolidWorks)."
        )
        payload, err = _load_payload()
        if err is not None:
            return err
        if payload is None:
            return _error("Body JSON inválido.", status=400)
        return self._do_create(payload)

    @http.route(
        "/itec-api/update/product",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        cors=CORS,
        save_session=False,
    )
    @api_key_required
    def legacy_update_product(self, **_):
        _logger.warning(
            "Itec API: usando endpoint /itec-api/update/product (compatibilidad SolidWorks)."
        )
        payload, err = _load_payload()
        if err is not None:
            return err
        if payload is None:
            return _error("Body JSON inválido.", status=400)
        default_code = payload.get("default_code")
        return self._do_update(default_code, payload)

