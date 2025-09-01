#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def migrate(cr, version):
    """
    Post-migration script to clean up old mission_type column from transport.mission
    """
    
    # Check if mission_type column still exists in transport_mission table
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'transport_mission' 
        AND column_name = 'mission_type'
    """)
    
    mission_type_exists = cr.fetchone()
    
    if mission_type_exists:
        # Remove the old mission_type column from transport_mission
        try:
            cr.execute("""
                ALTER TABLE transport_mission 
                DROP COLUMN mission_type
            """)
            print("Post-migration completed: Removed old mission_type column from transport_mission")
        except Exception as e:
            print(f"Warning: Could not remove mission_type column: {e}")
    else:
        print("Post-migration skipped: mission_type column already removed from transport_mission table")