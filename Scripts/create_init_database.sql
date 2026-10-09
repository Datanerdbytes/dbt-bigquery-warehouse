-- Terminate any active connections to Demo_Database if it exists
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'Demo_Database'
  AND pid <> pg_backend_pid();

-- Drop and recreate the flat database
DROP DATABASE IF EXISTS "Demo_Database";
CREATE DATABASE "Demo_Database";
