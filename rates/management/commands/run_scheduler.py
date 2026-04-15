from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management.base import BaseCommand

from rates.cron import fetch_rates_and_send_all_alerts, fetch_rates_daily_backfill


class Command(BaseCommand):
    help = "Run the APScheduler-based job scheduler (blocking — use for manual testing)."

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone="UTC")

        scheduler.add_job(
            fetch_rates_and_send_all_alerts,
            CronTrigger(hour=7, minute=0),
            id="fetch_and_alert_morning",
            max_instances=1,
        )
        scheduler.add_job(
            fetch_rates_and_send_all_alerts,
            CronTrigger(hour=12, minute=30),
            id="fetch_and_alert_midday",
            max_instances=1,
        )
        scheduler.add_job(
            fetch_rates_daily_backfill,
            CronTrigger(hour=2, minute=0),
            id="fetch_daily_backfill",
            max_instances=1,
        )

        self.stdout.write("Scheduler started. Jobs: 07:00, 12:30, 02:00 UTC.")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write("Scheduler stopped.")
