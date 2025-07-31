#!/usr/bin/env python3
"""
Script to fix distance discrepancies in transport missions.
Run this in Odoo shell to immediately fix all mission distances.
"""

def fix_mission_distances():
    """Fix all missions with incorrect distance calculations"""
    print("Starting distance fix process...")
    
    # Get all missions with coordinates
    missions = env['transport.mission'].search([
        ('source_latitude', '!=', False),
        ('source_longitude', '!=', False)
    ])
    
    print(f"Found {len(missions)} missions to check...")
    
    fixed_count = 0
    for mission in missions:
        try:
            old_distance = mission.total_distance_km
            old_method = getattr(mission, 'distance_calculation_method', 'unknown')
            
            # Clear any existing cache to force fresh calculation
            if mission.destination_ids:
                waypoints = [[mission.source_latitude, mission.source_longitude]]
                destinations = mission.destination_ids.filtered(lambda d: d.latitude and d.longitude).sorted('sequence')
                for dest in destinations:
                    waypoints.append([dest.latitude, dest.longitude])
                
                if len(waypoints) >= 2:
                    route_cache = env['transport.route.cache']
                    route_hash = route_cache.generate_route_hash(waypoints)
                    existing_cache = route_cache.search([('route_hash', '=', route_hash)])
                    if existing_cache:
                        existing_cache.unlink()
            
            # Force recalculation
            mission._compute_total_distance()
            
            if abs(old_distance - mission.total_distance_km) > 0.01:
                fixed_count += 1
                print(f"✓ Fixed {mission.name}: {old_distance:.2f} km ({old_method}) -> {mission.total_distance_km:.2f} km ({mission.distance_calculation_method})")
            else:
                print(f"  {mission.name}: {mission.total_distance_km:.2f} km ({mission.distance_calculation_method}) - OK")
                
        except Exception as e:
            print(f"✗ Error fixing {mission.name}: {e}")
    
    print(f"\n=== SUMMARY ===")
    print(f"Fixed {fixed_count} missions with incorrect distances")
    print(f"Total missions processed: {len(missions)}")
    return fixed_count

# Run the fix
if 'env' in globals():
    fix_mission_distances()
else:
    print("This script must be run in Odoo shell context")
    print("Usage:")
    print("1. python3 odoo-bin shell -d your_database_name")
    print("2. exec(open('fix_distances.py').read())")