#!/usr/bin/env python3
"""
Quick fix script for distance discrepancies.
Run this in Odoo shell to immediately fix the distance issue.

Usage:
1. Open Odoo shell: python3 odoo-bin shell -d your_database_name
2. Run: exec(open('quick_fix.py').read())
"""

print("🔧 Starting quick distance fix...")

try:
    # Get the transport mission model
    Mission = env['transport.mission']
    
    # Find all missions with coordinates
    missions = Mission.search([
        ('source_latitude', '!=', False),
        ('source_longitude', '!=', False)
    ])
    
    print(f"📊 Found {len(missions)} missions to process")
    
    fixed_count = 0
    for mission in missions:
        try:
            old_distance = mission.total_distance_km
            old_method = getattr(mission, 'distance_calculation_method', 'unknown')
            
            # Force recalculation by calling the compute method directly
            mission._compute_total_distance()
            
            new_distance = mission.total_distance_km
            new_method = mission.distance_calculation_method
            
            if abs(old_distance - new_distance) > 0.01:
                fixed_count += 1
                print(f"✅ {mission.name}: {old_distance:.2f} km ({old_method}) → {new_distance:.2f} km ({new_method})")
            else:
                print(f"ℹ️  {mission.name}: {new_distance:.2f} km ({new_method}) - Already correct")
                
        except Exception as e:
            print(f"❌ Error processing {mission.name}: {e}")
    
    print(f"\n🎉 Fix complete!")
    print(f"📈 Updated {fixed_count} missions")
    print(f"📋 Total processed: {len(missions)}")
    
    # Commit the changes
    env.cr.commit()
    print("💾 Changes committed to database")
    
except Exception as e:
    print(f"❌ Error during fix: {e}")
    print("🔄 Rolling back changes...")
    env.cr.rollback()