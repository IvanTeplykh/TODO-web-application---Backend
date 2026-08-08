-- ============================================================================
-- Migration: 001_extend_channels_varchar_limits.sql
-- Description: Expand VARCHAR column limits for 'channels' table with safety margin.
-- Engine: PostgreSQL
-- Type: Data-Preserving Schema Alteration (ALTER COLUMN TYPE, Zero-Downtime)
-- ============================================================================
-- 
-- RATIONALE & LIMIT JUSTIFICATION:
-- 1. channels.name (VARCHAR(100) -> VARCHAR(255)):
--    - Prevents StringDataRightTruncationError when users input descriptive, multilingual,
--      or emoji-rich team/workspace channel names exceeding 100 characters.
--    - 255 chars is the standard web identifier and title length across modern SaaS applications.
--
-- 2. channels.description (VARCHAR(250) -> VARCHAR(500)):
--    - 250 characters was too restrictive for comprehensive onboarding descriptions, rules,
--      or channel purpose guidelines. 500 characters provides a 2x safety buffer.
--
-- 3. channels.invite_code_hash (VARCHAR(100) -> VARCHAR(255)):
--    - Future-proofs storage for cryptographic hashes and encoded tokens (Argon2id, bcrypt,
--      SHA-512, HMAC-SHA256 with salts, iterations, and algorithm prefixes).
--
-- 4. channels.avatar_url (VARCHAR(250) -> VARCHAR(500)):
--    - Cloudinary, AWS S3 presigned URLs, and CDN paths with query parameters, expiration
--      timestamps, and security tokens easily exceed 250 characters. 500 chars safely prevents truncation.
--
-- 5. channel_members.role & channel_members.status (Safe enum/varchar headroom):
--    - Verified: channel_members uses Enum string values up to 20-50 chars ('owner', 'admin', 'member', 'pending', 'accepted').
-- ============================================================================

-- ============================================================================
-- UP MIGRATION (APPLY)
-- ============================================================================

BEGIN;

-- 1. channels.name: Expand from VARCHAR(100) to VARCHAR(255)
ALTER TABLE channels 
    ALTER COLUMN name TYPE VARCHAR(255);

-- 2. channels.description: Expand from VARCHAR(250) to VARCHAR(500)
ALTER TABLE channels 
    ALTER COLUMN description TYPE VARCHAR(500);

-- 3. channels.invite_code_hash: Expand from VARCHAR(100) to VARCHAR(255)
ALTER TABLE channels 
    ALTER COLUMN invite_code_hash TYPE VARCHAR(255);

-- 4. channels.avatar_url: Expand from VARCHAR(250) to VARCHAR(500)
-- Note: Uses USING clause if column is currently TEXT or VARCHAR to guarantee safe conversion
ALTER TABLE channels 
    ALTER COLUMN avatar_url TYPE VARCHAR(500) USING avatar_url::VARCHAR(500);

COMMIT;

-- ============================================================================
-- DOWN MIGRATION (ROLLBACK)
-- ============================================================================
-- WARNING: Reverting back to smaller VARCHAR limits will truncate or fail if 
-- data in production contains strings longer than the legacy limits.
-- 
-- To safely rollback manually, execute the following block:
--
-- BEGIN;
-- 
-- ALTER TABLE channels 
--     ALTER COLUMN name TYPE VARCHAR(100) USING SUBSTRING(name FROM 1 FOR 100);
-- 
-- ALTER TABLE channels 
--     ALTER COLUMN description TYPE VARCHAR(250) USING SUBSTRING(description FROM 1 FOR 250);
-- 
-- ALTER TABLE channels 
--     ALTER COLUMN invite_code_hash TYPE VARCHAR(100) USING SUBSTRING(invite_code_hash FROM 1 FOR 100);
-- 
-- ALTER TABLE channels 
--     ALTER COLUMN avatar_url TYPE VARCHAR(250) USING SUBSTRING(avatar_url FROM 1 FOR 250);
-- 
-- COMMIT;
