# 🇪🇹 Ethiopian School Management SaaS V1 (Enterprise Edition)

A multi-tenant Ethiopian School Management SaaS built specifically for Ethiopian High Schools (Grades 9–12).

---

## 🌟 Key Features
- **Multi-Tenancy & Data Isolation**: Strict tenant scoping (`TenantAwareModel`) preventing data leaks across schools.
- **Ethiopian Calendar & Localization**: Dual Ethiopian/Gregorian calendar support, Amharic PDFs, ETB currency, and administrative location fields (Region, Zone, Woreda, City, Sub-city, Kebele).
- **Academic Lifecycle & 1224 Ranking**: Natural/Social Science streams, continuous assessment, section-level competition ranking ("1224"), auto-generated transcripts, report cards, and payment receipts with anti-forgery QR verification codes.
- **Finance & Chapa Integration**: Multi-channel payments (Chapa, Bank Transfer, Cash), manual payment authorization workflow, automated reconciliation, and audit-logged refunds/reversals.
- **Unified Notification Engine**: Pluggable SMS provider abstraction (`SMSProviderBase`), Telegram bot account linking, Email alerts, and user notification preference management.
- **Super Admin & Monitoring**: `/health/` and `/ready/` infrastructure readiness probes, platform usage metering, and tenant provisioning dashboards.

---

## 📁 Repository Structure
```text
ethiopian_school_saas/
│
├── apps/                 # 24 Modular Django Tenant Applications
├── core/                 # Core Middlewares, Permissions, Exceptions & Services
├── utils/                # Ethiopian Calendar, ReportLab PDF & Security Validators
├── templates/            # Django HTML Templates
├── static/               # CSS, JS, and Branding Assets
├── media/                # User Uploads and Generated PDF Receipts
├── locale/               # Amharic & English Translations
├── tests/                # Unit, Integration, API, Security, & Workflow Test Suites
├── scripts/              # Automated Backup, Deployment, & Maintenance Scripts
├── deployment/           # Nginx, Gunicorn, Docker, & Systemd Production Configs
├── docs/                 # Architectural, API, Security, & Legal Documentation
├── config/               # Settings Modules, Celery Setup, & URL Routing
└── .github/              # Automated CI/CD GitHub Actions Workflow Pipeline
```

---

## 🚀 Quick Start
```bash
# 1. Clone repository & initialize virtual environment
git clone https://github.com/organization/ethiopian_school_saas.git
cd ethiopian_school_saas
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements/development.txt

# 3. Run database migrations
python manage.py migrate

# 4. Execute test suite
pytest -v tests/

# 5. Start development server
python manage.py runserver
```
