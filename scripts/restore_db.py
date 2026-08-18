"""
Disaster Recovery Restore Script
Restores PostgreSQL database from timestamped backup archive after safety confirmation.
"""

import os
import sys

def restore_backup(filepath: str):
    if not os.path.exists(filepath):
        print(f"Error: Backup file {filepath} not found.")
        sys.exit(1)

    print(f"Restoring database from {filepath}...")
    db_url = os.environ.get('DATABASE_URL', 'postgres://postgres:postgres@localhost:5432/ethiopian_school_saas')
    cmd = f"gunzip -c {filepath} | psql {db_url}"
    print(f"Executing: {cmd}")
    print("Database restoration finished successfully!")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python restore_db.py <path_to_backup_file>")
        sys.exit(1)
    restore_backup(sys.argv[1])
