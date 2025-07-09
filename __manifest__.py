{
    'name': "Transport Management",
    'version': '16.0.1.0.0',
    'summary': "Manage transport missions, drivers, and vehicles.",
    'description': "A module to manage transport operations, including mission planning and status tracking.",
    'author': "Samir Taous",
    'category': 'Operations/Transport',
    'depends': [
        'base', 
        'fleet',  # For the 'fleet.vehicle' model
        'mail',   # For the chatter and activity features
    ],
    'data': [
        # 1. Security (Load first)
        'security/ir.model.access.csv',
        # 2. Data (Sequences, etc.)
        'data/sequence_data.xml',
        # 3. Views (UI)
        'views/transport_vehicle_views.xml',
        'views/transport_mission_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [

            # Stylesheet File
            'transport_management/static/src/scss/styles.scss',

            # Leaflet Library
            'transport_management/static/lib/leaflet/leaflet.css',
            'transport_management/static/lib/leaflet/leaflet.js',
            
            # Map Widget Files
            'transport_management/static/src/js/map_field_widget.js',
            'transport_management/static/src/xml/map_field_widget.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}