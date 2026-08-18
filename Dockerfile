FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt /app/requirements/
COPY requirements/production.txt /app/requirements/
RUN pip install --no-cache-dir -r requirements/production.txt

COPY . /app/

EXPOSE 8000

CMD ["gunicorn", "--config", "deployment/gunicorn/gunicorn_conf.py", "config.wsgi:application"]
