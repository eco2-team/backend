#!/bin/bash
set -e

# Initialize PostgreSQL extensions for location service
# This script should be run with superuser privileges

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Install geospatial extensions
    CREATE EXTENSION IF NOT EXISTS cube;
    CREATE EXTENSION IF NOT EXISTS earthdistance;

    -- Verify installation
    SELECT extname, extversion FROM pg_extension WHERE extname IN ('cube', 'earthdistance');
EOSQL

echo "✅ PostgreSQL extensions installed successfully"
