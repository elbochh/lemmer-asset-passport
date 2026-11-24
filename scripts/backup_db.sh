#!/bin/sh
# Backup the Lemmer Asset Passport database to a timestamped file.
# Usage: DATABASE_URL=postgresql://user:pass@host:5432/dbname scripts/backup_db.sh [outdir]
# (use a plain postgresql:// URL, not the postgresql+psycopg:// form)
set -eu
: "${DATABASE_URL:?Set DATABASE_URL to the PostgreSQL connection string}"
out="${1:-.}/lemmer_backup_$(date +%Y%m%d_%H%M%S).dump"
pg_dump --format=custom --no-owner --file "$out" "$DATABASE_URL"
echo "Backup written to $out"
echo "Restore with: pg_restore --no-owner --dbname \"\$DATABASE_URL\" $out"
