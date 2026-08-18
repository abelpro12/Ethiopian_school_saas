# Database Migration Safety Policy

To prevent downtime or data loss across multi-tenant schools, **never casually edit production database schema manually**. Always follow this strict four-step workflow:

---

## 1. Migration Safety Pipeline

```text
Backup Production DB 
        ↓
Test Migration on Staging Copy 
        ↓
Run Migration via CI/CD 
        ↓
Verify Application Health (/ready/)
```

---

## 2. Mandatory Pre-Migration Checklists

Before running `python manage.py migrate` in production:
1. **Never drop columns or tables in a single step**. Mark deprecated fields as `nullable` or `blank=True` first, deploy code changes, and remove columns in a subsequent release.
2. **Always test migration against a anonymized staging database copy** containing realistic data volumes to catch slow locking queries.
3. **Verify Index Creation**: Create heavy indexes concurrently (`CONCURRENTLY` in PostgreSQL) to avoid locking read/write queries during school hours.
4. **Tenant Isolation Audit**: Verify that all new models inherit from `TenantAwareModel` and contain indexed `school_id` foreign keys.
