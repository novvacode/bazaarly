-- Runs once when the Postgres container initialises its data directory.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS citext;

-- Separate database for the test suite (pytest uses TEST_DATABASE_URL / bazaarly_test).
CREATE DATABASE bazaarly_test OWNER bazaarly;
\connect bazaarly_test
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS citext;
