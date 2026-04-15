import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def fetch_hourly():
    logger.info("scheduler: fetch_rates_hourly start")
    call_command("fetch_rates", days=3)
    logger.info("scheduler: fetch_rates_hourly done")


def fetch_daily_backfill():
    logger.info("scheduler: fetch_rates_daily_backfill start")
    call_command("fetch_rates", days=90, no_alerts=True)
    logger.info("scheduler: fetch_rates_daily_backfill done")


class Command(BaseCommand):
    help = "Run the APScheduler-based job scheduler (blocking — run as a separate service)."

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone="UTC")

        # Every hour at :00
        scheduler.add_job(fetch_hourly, CronTrigger(minute=0), id="fetch_hourly", max_instances=1)

        # Daily at 02:00 UTC — 90-day backfill, no alerts
        scheduler.add_job(
            fetch_daily_backfill,
            CronTrigger(hour=2, minute=0),
            id="fetch_daily_backfill",
            max_instances=1,
        )

        self.stdout.write("Scheduler started. Jobs: fetch_hourly (0 * * * *), fetch_daily_backfill (0 2 * * *).")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write("Scheduler stopped.")
