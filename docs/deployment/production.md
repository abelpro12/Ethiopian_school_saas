# Production Deployment Guide

1. Clone repository to `/var/www/ethiopian_school_saas/`.
2. Configure `.env` with production secrets (`DATABASE_URL`, `SECRET_KEY`, `CHAPA_SECRET_KEY`).
3. Run `docker-compose -f deployment/docker/docker-compose.prod.yml up -d --build`.
4. Verify `/ready/` endpoint returns HTTP 200 `status: ready`.
