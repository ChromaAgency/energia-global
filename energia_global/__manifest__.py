# -*- coding: utf-8 -*-
{
    'name': "Energia Global",
    'version': '19.0.0.4',

    'summary': """
        Modulo para customizaciones de Energia Global
    """,

    'description': """    """,

    'author': "Chroma",
    'website': "https://portal.chroma.agency/",
    'maintainer': 'Chroma',

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Miscellaneous',
    # any module necessary for this one to work correctly
    'depends': ['base', 'mrp', 'mrp_workorder', 'sale_mrp'],
    # always loaded
    'data': [
        'views/mrp_workorder_component_filter_views.xml',
    ],
    'assets': {
        'web.assets_backend': [ 
            'energia_global/static/src/js/mrp_shopfloor_component_filter.js',
            'energia_global/static/src/js/three_viewer.js',
            'energia_global/static/src/xml/mrp_shopfloor_component_fields.xml',
            'energia_global/static/src/xml/three_viewer_templates.xml',
        ],
    },
    'installable': True,
    'auto_install': True,
    'application': True,

}
