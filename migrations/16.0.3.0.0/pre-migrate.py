def migrate(cr, version):
    """Add starting_weight field to transport_mission table"""
    cr.execute("""
        ALTER TABLE transport_mission 
        ADD COLUMN IF NOT EXISTS starting_weight NUMERIC(10,2) DEFAULT 0.0
    """)