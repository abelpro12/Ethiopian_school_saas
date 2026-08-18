#!/bin/bash
set -e
echo "Starting production deployment for Ethiopian School SaaS V1..."
python manage.py migrate --noinput
python manage.py collectstatic --noinput
echo "Deployment completed successfully!"
