import importlib
from unittest.mock import patch

from django.core.management import call_command
from django.test import override_settings

from rates import apps, cron
from rates.apps import RatesConfig


class TestCronJobs:
    @override_settings(RUN_SCHEDULER=False)
    def test_django_import_does_not_start_scheduler_by_default(self):
        config = RatesConfig("rates", importlib.import_module("rates"))
        with patch("rates.apps._start_scheduler") as start_scheduler:
            config.ready()
        start_scheduler.assert_not_called()

    @override_settings(RUN_SCHEDULER=True)
    def test_production_flag_starts_in_process_scheduler(self):
        config = RatesConfig("rates", importlib.import_module("rates"))
        with patch("rates.apps._start_scheduler") as start_scheduler:
            config.ready()
        start_scheduler.assert_called_once_with()

    def test_in_process_scheduler_uses_the_shared_job_configuration(self):
        apps._scheduler = None
        with patch("apscheduler.schedulers.background.BackgroundScheduler") as scheduler_class:
            scheduler = scheduler_class.return_value
            apps._start_scheduler()

        scheduler_class.assert_called_once_with(
            timezone="UTC",
            job_defaults={"coalesce": True, "misfire_grace_time": 3600, "max_instances": 1},
        )
        assert scheduler.add_job.call_count == 3
        scheduler.start.assert_called_once_with()
        assert apps._scheduler is scheduler
        apps._scheduler = None

    def test_fetch_rates_and_send_all_alerts_runs_combined_job(self):
        with (
            patch("rates.cron.call_command") as mock_call_command,
            patch(
                "rates.services.alerts.send_all_current_alerts",
                return_value={"sent": 3, "failed": 0, "total": 3},
            ) as mock_send,
        ):
            cron.fetch_rates_and_send_all_alerts()

        mock_call_command.assert_called_once_with("fetch_rates", days=3, no_alerts=True)
        mock_send.assert_called_once_with()

    def test_scheduler_command_registers_one_owner_for_all_jobs(self):
        with patch("rates.management.commands.run_scheduler.BlockingScheduler") as scheduler_class:
            scheduler = scheduler_class.return_value
            call_command("run_scheduler")

        scheduler_class.assert_called_once_with(
            timezone="UTC",
            job_defaults={"coalesce": True, "misfire_grace_time": 3600, "max_instances": 1},
        )
        assert scheduler.add_job.call_count == 3
        assert [call.kwargs["id"] for call in scheduler.add_job.call_args_list] == [
            "fetch_and_alert_morning",
            "fetch_and_alert_midday",
            "fetch_daily_backfill",
        ]
        scheduler.start.assert_called_once_with()
