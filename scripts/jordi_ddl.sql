-- 1. Create a new database
CREATE OR REPLACE DATABASE JORDI_DB;

-- 2. Create schema (though PUBLIC exists by default, this ensures a fresh one)
CREATE OR REPLACE SCHEMA JORDI_DB.PUBLIC;

-- 3. Create a compute warehouse
CREATE OR REPLACE WAREHOUSE COMPUTE_WH
  WITH WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE;


-- 4. Use the database, schema, and warehouse
USE DATABASE JORDI_DB;
USE SCHEMA PUBLIC;
USE WAREHOUSE COMPUTE_WH;


-- 5. Run a simple test to ensure everything is active
SELECT CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_WAREHOUSE();
