# System Architecture Overview

The **Ethiopian School Management SaaS** is designed as a multi-tenant enterprise system using Django and PostgreSQL.

## Core Architectural Pillars
1. **Tenant Security**: Shared database with logical separation via `TenantAwareModel` and `TenantMiddleware`.
2. **Academic Standards**: Native support for Ethiopian Academic Year calendar (Meskerem to Hamle), Grade 9-12 streams (Natural and Social Science), continuous assessment, and 1224 competition ranking.
3. **Financial Integrity**: Multi-channel fee collections (Chapa, Bank Transfer, Cash) with idempotency, manual authorization, reconciliation, and audit-logged refunds.
