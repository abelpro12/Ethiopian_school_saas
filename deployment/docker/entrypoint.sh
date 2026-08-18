#!/bin/sh

set -e

echo "Waiting for PostgreSQL database..."
python manage.py check

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

exec "$@"
