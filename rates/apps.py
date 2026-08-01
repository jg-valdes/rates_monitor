from django.apps import AppConfig
from django.conf import settings

_scheduler = None


class RatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "rates"

    def ready(self):
        if settings.RUN_SCHEDULER and _scheduler is None:
            _start_scheduler()


def _start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler

    from rates.scheduler import configure_scheduler

    global _scheduler
    scheduler = BackgroundScheduler(
        timezone="UTC",
        job_defaults={"coalesce": True, "misfire_grace_time": 3600, "max_instances": 1},
    )
    configure_scheduler(scheduler)
    scheduler.start()
    _scheduler = scheduler
