#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify the mission type refactoring works correctly.
Run this in an Odoo shell to test the functionality.
"""

def test_mission_types(env):
    """
    Test the mission type functionality
    """
    
    # Create a test mission
    mission = env['transport.mission'].create({
        'name': 'Test Mixed Mission',
        'mission_date': '2024-01-15',
        'source_location': 'Test Source Location',
        'source_latitude': 33.5731,
        'source_longitude': -7.5898,
    })
    
    print(f"Created mission: {mission.name}")
    
    # Create destinations with different types
    pickup_dest = env['transport.destination'].create({
        'mission_id': mission.id,
        'location': 'Pickup Location',
        'latitude': 33.5831,
        'longitude': -7.5798,
        'sequence': 1,
        'mission_type': 'pickup',
    })
    
    delivery_dest = env['transport.destination'].create({
        'mission_id': mission.id,
        'location': 'Delivery Location',
        'latitude': 33.5931,
        'longitude': -7.5698,
        'sequence': 2,
        'mission_type': 'delivery',
    })
    
    print(f"Created pickup destination: {pickup_dest.location}")
    print(f"Created delivery destination: {delivery_dest.location}")
    
    # Test computed fields
    mission._compute_mission_type_summary()
    
    print(f"Mission pickup count: {mission.pickup_count}")
    print(f"Mission delivery count: {mission.delivery_count}")
    print(f"Mission type summary: {mission.mission_type_summary}")
    
    # Verify the summary is correct
    assert mission.pickup_count == 1, f"Expected 1 pickup, got {mission.pickup_count}"
    assert mission.delivery_count == 1, f"Expected 1 delivery, got {mission.delivery_count}"
    assert mission.mission_type_summary == "1 Pickup + 1 Delivery", f"Unexpected summary: {mission.mission_type_summary}"
    
    print("✅ All tests passed!")
    
    # Clean up
    mission.unlink()
    print("🧹 Test data cleaned up")

def main():
    """
    Instructions for running the test
    """
    print("To run this test, execute in Odoo shell:")
    print(">>> from transport_management.test_mission_types import test_mission_types")
    print(">>> test_mission_types(env)")

if __name__ == '__main__':
    main()