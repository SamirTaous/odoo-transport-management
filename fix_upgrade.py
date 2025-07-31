#!/usr/bin/env python3
"""
Script to fix upgrade issues with transport_management module
Run this in Odoo shell if the upgrade gets stuck
"""

def fix_upgrade():
    """Fix upgrade issues by ensuring all fields have proper values"""
    try:
        print("🔧 Starting upgrade fix...")
        
        # Get the transport mission model
        Mission = env['transport.mission']
        
        # Check if the new field exists
        if hasattr(Mission, 'estimated_duration_minutes'):
            print("✅ estimated_duration_minutes field exists")
            
            # Update any records with null values
            missions_to_fix = Mission.search([
                ('estimated_duration_minutes', '=', False)
            ])
            
            if missions_to_fix:
                missions_to_fix.write({'estimated_duration_minutes': 0.0})
                print(f"✅ Fixed {len(missions_to_fix)} missions with null duration")
        else:
            print("❌ estimated_duration_minutes field not found")
        
        # Check distance calculation method field
        if hasattr(Mission, 'distance_calculation_method'):
            print("✅ distance_calculation_method field exists")
            
            # Update any records with null values
            missions_to_fix = Mission.search([
                ('distance_calculation_method', '=', False)
            ])
            
            if missions_to_fix:
                missions_to_fix.write({'distance_calculation_method': 'osrm'})
                print(f"✅ Fixed {len(missions_to_fix)} missions with null calculation method")
        else:
            print("❌ distance_calculation_method field not found")
        
        # Force recomputation of distances
        all_missions = Mission.search([])
        if all_missions:
            print(f"🔄 Recomputing distances for {len(all_missions)} missions...")
            all_missions._compute_total_distance()
            print("✅ Distance recomputation complete")
        
        # Commit changes
        env.cr.commit()
        print("💾 Changes committed successfully")
        print("🎉 Upgrade fix complete!")
        
    except Exception as e:
        print(f"❌ Error during upgrade fix: {e}")
        env.cr.rollback()
        print("🔄 Changes rolled back")

# Run the fix if in Odoo shell context
if 'env' in globals():
    fix_upgrade()
else:
    print("This script must be run in Odoo shell context")
    print("Usage:")
    print("1. python3 odoo-bin shell -d your_database_name")
    print("2. exec(open('fix_upgrade.py').read())")