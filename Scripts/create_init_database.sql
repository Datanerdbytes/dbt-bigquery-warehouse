USE master;
GO 

-- Force disconnect active users if it exists, then drop
IF EXISTS (SELECT 1 FROM sys.databases WHERE name = 'Demo_Database')
BEGIN
    ALTER DATABASE Demo_Database SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
END;

DROP DATABASE IF EXISTS Demo_Database;
GO

CREATE DATABASE Demo_Database;
GO 

USE Demo_Database;
GO 

-- Create Schemas
IF SCHEMA_ID('bronze') IS NULL EXEC('CREATE SCHEMA bronze');
GO
IF SCHEMA_ID('silver') IS NULL EXEC('CREATE SCHEMA silver');
GO
IF SCHEMA_ID('gold') IS NULL EXEC('CREATE SCHEMA gold');
GO