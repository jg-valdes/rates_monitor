import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class RatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "rates"

    def ready(self):
        # Avoid starting the scheduler twice when Django's dev reloader is active.
        import os
        if os.environ.get("RUN_MAIN") == "true" or not _is_runserver():
            _start_scheduler()


def _is_runserver():
    import sys
    return "runserver" in sys.argv


def _start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from django.core.management import call_command

    def fetch_hourly():
        logger.info("scheduler: fetch_hourly start")
        call_command("fetch_rates", days=3)
        logger.info("scheduler: fetch_hourly done")

    def fetch_daily_backfill():
        logger.info("scheduler: fetch_daily_backfill start")
        call_command("fetch_rates", days=90, no_alerts=True)
        logger.info("scheduler: fetch_daily_backfill done")

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(fetch_hourly, CronTrigger(minute=0), id="fetch_hourly", max_instances=1)
    scheduler.add_job(
        fetch_daily_backfill,
        CronTrigger(hour=2, minute=0),
        id="fetch_daily_backfill",
        max_instances=1,
    )
    scheduler.start()
    logger.info("scheduler: started (fetch_hourly @ *:00, fetch_daily_backfill @ 02:00 UTC)")
