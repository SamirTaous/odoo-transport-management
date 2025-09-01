#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def migrate(cr, version):
    """
    Migration script to move mission_type from transport.mission to transport.destination
    """
    
    # Check if mission_type column exists in transport_mission table
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'transport_mission' 
        AND column_name = 'mission_type'
    """)
    
    mission_type_exists = cr.fetchone()
    
    if mission_type_exists:
        # Add mission_type column to transport_destination if it doesn't exist
        cr.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'transport_destination' 
            AND column_name = 'mission_type'
        """)
        
        dest_mission_type_exists = cr.fetchone()
        
        if not dest_mission_type_exists:
            # Add the mission_type column to transport_destination
            cr.execute("""
                ALTER TABLE transport_destination 
                ADD COLUMN mission_type VARCHAR
            """)
        
        # Copy mission_type from mission to all its destinations
        cr.execute("""
            UPDATE transport_destination 
            SET mission_type = tm.mission_type
            FROM transport_mission tm
            WHERE transport_destination.mission_id = tm.id
            AND transport_destination.mission_type IS NULL
        """)
        
        # Set default value for any destinations without mission_type
        cr.execute("""
            UPDATE transport_destination 
            SET mission_type = 'delivery'
            WHERE mission_type IS NULL
        """)
        
        print("Migration completed: Moved mission_type from missions to destinations")
    else:
        print("Migration skipped: mission_type column not found in transport_mission table")