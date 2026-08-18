# Legal & Commercial Policy Documentation

This document outlines the mandatory legal agreements, data ownership policies, data retention schedules, and refund terms for commercial operation of the **Ethiopian School Management SaaS Platform**.

---

## 1. Terms of Service (ToS) Summary
* **Service Scope**: B2B SaaS management platform provided to Ethiopian Educational Institutions (Grades 9–12).
* **Tenant Isolation & Security**: The platform guarantees strict multi-tenant data isolation. Each institution's database records are segregated logically via tenant middleware and unique school identifier keys.
* **Service Level Agreement (SLA)**: 99.9% monthly uptime target for core student administration and mark submission services.

---

## 2. School Data Ownership Policy
* **Data Ownership**: Schools retain 100% full ownership of all student academic records, teacher profiles, examination marks, daily attendance logs, and financial transaction records created on the platform.
* **Data Portability**: At any time during an active subscription or upon cancellation, school administrators may export full database records in standardized CSV and JSON formats.

---

## 3. Privacy & Student Data Protection Policy
* **Student Privacy**: Student data (names, birth dates, academic marks, guardians' contact info) is processed strictly for educational administration. Data is never sold, shared, or analyzed for commercial advertising.
* **Access Rights**: Parents and students have right-of-access to view published marks and attendance via dedicated portal dashboards.

---

## 4. Payment, Fee & Refund Policy
* **Digital Payments**: Online payments processed via Chapa or direct bank transfers are immediately allocated to student invoices.
* **Refund Requests**: Refund or reversal requests for duplicate or incorrect payments must be processed by School Accountants with mandatory audit trail log entries (`PaymentRefund`).

---

## 5. Data Retention & Archival Policy (Point 69)
When a student leaves, or a school cancels its subscription, records enter lifecycle states:
1. **Active**: Standard operational access.
2. **Archived**: Student graduation or transfer. Records remain read-only for historical transcript generation for 10 years.
3. **Anonymized / Deleted**: Upon formal contract termination, school PII is anonymized after a 90-day grace period, retaining unidentifiable statistical metadata for reporting.
