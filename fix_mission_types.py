#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick fix script to migrate mission types from mission level to destination level.
This can be run manually if needed after the module update.
"""

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def migrate_mission_types(env):
    """
    Migrate mission types from transport.mission to transport.destination
    """
    
    # Find all missions that might still have mission_type data
    missions = env['transport.mission'].search([])
    
    updated_count = 0
    
    for mission in missions:
        # Check if any destinations don't have mission_type set
        destinations_without_type = mission.destination_ids.filtered(lambda d: not d.mission_type)
        
        if destinations_without_type:
            # Set all destinations to 'delivery' as default
            destinations_without_type.write({'mission_type': 'delivery'})
            updated_count += len(destinations_without_type)
            _logger.info(f"Updated {len(destinations_without_type)} destinations for mission {mission.name}")
    
    _logger.info(f"Migration completed: Updated {updated_count} destinations")
    return updated_count

def main():
    """
    Main function to run the migration
    """
    import odoo
    from odoo.tools import config
    
    # This would be run in an Odoo environment
    # For manual execution, you'd need to set up the Odoo environment first
    print("This script should be run within an Odoo environment")
    print("Example usage in Odoo shell:")
    print(">>> from transport_management.fix_mission_types import migrate_mission_types")
    print(">>> migrate_mission_types(env)")

if __name__ == '__main__':
    main()