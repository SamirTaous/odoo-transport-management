#!/usr/bin/env python3
"""
Post-migration script for transport_management module
Handles the addition of estimated_duration_minutes field
"""

def migrate(cr, version):
    """
    Migration script for version 1.0.1
    """
    # Check if the estimated_duration_minutes column exists
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'transport_mission' 
        AND column_name = 'estimated_duration_minutes'
    """)
    
    if not cr.fetchone():
        # Add the column if it doesn't exist
        cr.execute("""
            ALTER TABLE transport_mission 
            ADD COLUMN estimated_duration_minutes NUMERIC DEFAULT 0
        """)
        print("Added estimated_duration_minutes column to transport_mission table")
    
    # Update existing missions to have default values
    cr.execute("""
        UPDATE transport_mission 
        SET estimated_duration_minutes = 0 
        WHERE estimated_duration_minutes IS NULL
    """)
    
    # Update distance calculation method for existing missions
    cr.execute("""
        UPDATE transport_mission 
        SET distance_calculation_method = 'haversine' 
        WHERE distance_calculation_method IS NULL
    """)
    
    print("Migration completed successfully")