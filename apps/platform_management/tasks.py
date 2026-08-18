import logging
from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)

@shared_task
def run_automated_database_backup():
    """
    Automated Celery task to dump the PostgreSQL database
    and compress it to the configured storage (AWS S3).
    """
    try:
        logger.info("Starting automated database backup to S3...")
        # Runs the equivalent of `python manage.py dbbackup --compress --clean`
        call_command('dbbackup', compress=True, clean=True)
        logger.info("Database backup completed successfully.")
    except Exception as e:
        logger.error(f"Database backup failed: {str(e)}")
        raise
