-- SQL script to fix database issues after adding new fields
-- Run this in your PostgreSQL database if the upgrade fails

-- Add the estimated_duration_minutes column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'transport_mission' 
        AND column_name = 'estimated_duration_minutes'
    ) THEN
        ALTER TABLE transport_mission ADD COLUMN estimated_duration_minutes NUMERIC DEFAULT 0;
        RAISE NOTICE 'Added estimated_duration_minutes column';
    END IF;
END $$;

-- Update existing records to have default values
UPDATE transport_mission 
SET estimated_duration_minutes = 0 
WHERE estimated_duration_minutes IS NULL;

UPDATE transport_mission 
SET distance_calculation_method = 'osrm' 
WHERE distance_calculation_method IS NULL;

-- Verify the changes
SELECT 
    name, 
    total_distance_km, 
    estimated_duration_minutes, 
    distance_calculation_method 
FROM transport_mission 
LIMIT 5;