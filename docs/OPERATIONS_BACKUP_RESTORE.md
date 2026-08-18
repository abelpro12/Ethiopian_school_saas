# Operations Guide: Database Backup & Restoration Procedures

This document defines the mandatory automated backup, retention, and disaster recovery procedures for the **Ethiopian School Management SaaS V1** PostgreSQL production database.

---

## 1. Automated PostgreSQL Backup Workflow

Automated backups run on a scheduled cron trigger twice daily (02:00 UTC and 14:00 UTC) using standard `pg_dump` with custom compressed format `.dump`.

### Backup Script (`scripts/postgres_backup.sh`)
```bash
#!/bin/bash
set -e

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="/var/backups/postgres"
BACKUP_FILE="${BACKUP_DIR}/ethiopian_school_saas_${TIMESTAMP}.dump"
S3_BUCKET="s3://ethiopian-school-saas-backups-prod"

# Ensure local backup directory exists
mkdir -p ${BACKUP_DIR}

# Execute pg_dump with tenant safety flags
pg_dump -U postgres -d ethiopian_school_saas_db -F c -b -v -f ${BACKUP_FILE}

# Encrypt backup file using AES-256
gpg --symmetric --cipher-algo AES256 --batch --passphrase-file /etc/backup_passphrase.key ${BACKUP_FILE}

# Upload encrypted backup to isolated AWS S3 Glacier storage
aws s3 cp ${BACKUP_FILE}.gpg ${S3_BUCKET}/daily/${TIMESTAMP}.dump.gpg

# Cleanup local dumps older than 7 days
find ${BACKUP_DIR} -type f -mtime +7 -delete

echo "PostgreSQL Automated Backup completed successfully at ${TIMESTAMP}"
```

---

## 2. Retention Policy
* **Daily Backups**: Retained for 30 days.
* **Weekly Snapshots**: Retained for 12 months.
* **Annual Archives**: Retained indefinitely in AWS S3 Glacier Deep Archive to comply with educational record retention laws.

---

## 3. Documented Restoration Procedures (Disaster Recovery Test)

### Step-by-Step Database Restoration Procedure
If a database restoration is required due to hardware failure or disaster recovery validation:

1. **Provision Fresh Target Instance**: Ensure PostgreSQL version matches production (v15+).
2. **Retrieve and Decrypt Backup**:
   ```bash
   aws s3 cp s3://ethiopian-school-saas-backups-prod/daily/20260810_120000.dump.gpg ./target_backup.dump.gpg
   gpg --decrypt --batch --passphrase-file /etc/backup_passphrase.key target_backup.dump.gpg > target_backup.dump
   ```
3. **Terminate Active Connections**:
   ```sql
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'ethiopian_school_saas_db';
   ```
4. **Drop and Recreate Database**:
   ```sql
   DROP DATABASE ethiopian_school_saas_db;
   CREATE DATABASE ethiopian_school_saas_db WITH OWNER postgres ENCODING 'UTF8';
   ```
5. **Restore Schema & Data**:
   ```bash
   pg_restore -U postgres -d ethiopian_school_saas_db -v -c target_backup.dump
   ```
6. **Verify Data Integrity**:
   ```bash
   python manage.py check
   python manage.py shell -c "from apps.tenants.models import School; print('Total Schools Restored:', School.objects.count())"
   ```
