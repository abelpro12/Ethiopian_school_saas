# Multi-Tenancy Architecture & Data Isolation

## Shared Database with Mandatory Tenant Foreign Key (`school_id`)

Every tenant model inherits from `TenantAwareModel`:

```python
class TenantAwareModel(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, db_index=True)
    objects = TenantManager()
    class Meta:
        abstract = True
```

## Security Enforcement Layers

1. **Queryset Level:** `TenantManager.for_school(active_school)` automatically scopes queries to the active school context.
2. **Middleware Level:** `TenantMiddleware` extracts the tenant context from headers (`X-School-ID`), user session, or subdomains.
3. **Database Integrity:** Overridden `save()` raises `ValueError` if `school_id` is missing.
4. **DRF Permission Scoping:** `IsTenantScoped` permission class blocks cross-tenant API requests.
