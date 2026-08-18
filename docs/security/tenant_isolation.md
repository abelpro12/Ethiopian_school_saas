# Multi-Tenant Security & Isolation Standards

Every model in `apps/` MUST inherit from `TenantAwareModel`. Queries are automatically scoped via `TenantManager.for_school(school)` and verified by `verify_tenant_ownership`.

Cross-tenant access attempts trigger a `TenantSecurityException` or return an empty queryset (404/403).
