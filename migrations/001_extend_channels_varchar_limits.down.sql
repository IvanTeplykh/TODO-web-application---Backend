-- ============================================================================
-- Rollback Migration: 001_extend_channels_varchar_limits.down.sql
-- Description: Rollback channels table VARCHAR limits to legacy values
-- Engine: PostgreSQL
-- ============================================================================

BEGIN;

-- 1. Revert channels.name back to VARCHAR(100) with safe substring truncation
ALTER TABLE channels 
    ALTER COLUMN name TYPE VARCHAR(100) USING SUBSTRING(name FROM 1 FOR 100);

-- 2. Revert channels.description back to VARCHAR(250) with safe substring truncation
ALTER TABLE channels 
    ALTER COLUMN description TYPE VARCHAR(250) USING SUBSTRING(description FROM 1 FOR 250);

-- 3. Revert channels.invite_code_hash back to VARCHAR(100) with safe substring truncation
ALTER TABLE channels 
    ALTER COLUMN invite_code_hash TYPE VARCHAR(100) USING SUBSTRING(invite_code_hash FROM 1 FOR 100);

-- 4. Revert channels.avatar_url back to VARCHAR(250) with safe substring truncation
ALTER TABLE channels 
    ALTER COLUMN avatar_url TYPE VARCHAR(250) USING SUBSTRING(avatar_url FROM 1 FOR 250);

COMMIT;
