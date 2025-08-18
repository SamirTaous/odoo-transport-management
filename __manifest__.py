{
    'name': "Transport Management",
    'version': '16.0.2.0.0',
    'summary': "Manage transport missions, drivers, and vehicles.",
    'description': "A module to manage transport operations, including mission planning and status tracking.",
    'author': "Samir Taous",
    'category': 'Operations/Transport',
    'depends': [
        'base', 
        'fleet',  # For the 'fleet.vehicle' model
        'mail',   # For the chatter and activity features
        'base_geolocalize',
    ],
    'data': [
        # 1. Security (Load first)
        'security/ir.model.access.csv',
        # 2. Data (Sequences, etc.)
        'data/sequence_data.xml',
        'data/ir_config_parameter_data.xml',
        # 3. Actions (Load before views that reference them)
        'views/actions.xml',
        # 4. Views (UI)
        'views/transport_vehicle_views.xml',
        'views/transport_mission_views.xml',
        'views/route_cache_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'assets': {
        'web.assets_backend': [

            # Stylesheet Files
            'transport_management/static/src/scss/styles.scss',
            'transport_management/static/src/css/transport_mission.css',

            # Leaflet Library
            'transport_management/static/lib/leaflet/leaflet.css',
            'transport_management/static/lib/leaflet/leaflet.js',
            
            # Map Widget Files
            'transport_management/static/src/js/mission_map_planner_widget.js',
            'transport_management/static/src/xml/mission_map_planner_widget.xml',
            
            # Overview Map Files
            'transport_management/static/src/js/mission_overview_simple.js',
            'transport_management/static/src/xml/mission_overview_simple.xml',
        ],
    },
    'external_dependencies': {
        'python': ['requests'], 
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}