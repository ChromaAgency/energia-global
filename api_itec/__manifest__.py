# -*- coding: utf-8 -*-
{
    "name": "API Itec REST",
    "summary": "Endpoints REST nativos para crear / actualizar productos desde Postman u otra app, "
               "reemplazando el middleware externo que convertía REST a JSON-RPC.",
    "description": "",
    "author": "Chroma Agency",
    "website": "https://chroma.agency",
    "category": "Tools",
    "version": "1.0.2",
    "license": "LGPL-3",
    "depends": ["base", "product", "mrp", "stock",],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/product_template_views.xml",
        "views/itec_api_key_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
