class TenantSecurityException(Exception):
    """Raised when tenant isolation boundary is breached."""
    pass

class EntitlementException(Exception):
    """Raised when plan quota or entitlement limit is exceeded."""
    pass
