from apscheduler.triggers.cron import CronTrigger

from rates.cron import fetch_rates_and_send_all_alerts, fetch_rates_daily_backfill


def configure_scheduler(scheduler):
    """Register the product's periodic jobs on an APScheduler instance."""
    scheduler.add_job(
        fetch_rates_and_send_all_alerts,
        CronTrigger(hour=7, minute=0, day_of_week="mon-fri"),
        id="fetch_and_alert_morning",
    )
    scheduler.add_job(
        fetch_rates_and_send_all_alerts,
        CronTrigger(hour=12, minute=30, day_of_week="mon-fri"),
        id="fetch_and_alert_midday",
    )
    scheduler.add_job(
        fetch_rates_daily_backfill,
        CronTrigger(hour=2, minute=0),
        id="fetch_daily_backfill",
    )
