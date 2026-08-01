from apscheduler.schedulers.blocking import BlockingScheduler
from django.core.management.base import BaseCommand

from rates.scheduler import configure_scheduler


class Command(BaseCommand):
    help = "Run the dedicated APScheduler process (blocking)."

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(
            timezone="UTC",
            job_defaults={"coalesce": True, "misfire_grace_time": 3600, "max_instances": 1},
        )

        configure_scheduler(scheduler)

        self.stdout.write("Scheduler started. Jobs: weekday 07:00, weekday 12:30, daily 02:00 UTC.")
        try:
            scheduler.start()
        except KeyboardInterrupt, SystemExit:
            self.stdout.write("Scheduler stopped.")
