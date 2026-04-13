from unittest.mock import patch

from rates import cron


class TestCronJobs:
    def test_fetch_rates_and_send_all_alerts_runs_combined_job(self):
        with (
            patch("rates.cron.call_command") as mock_call_command,
            patch("rates.services.alerts.send_all_current_alerts", return_value={"sent": 3, "failed": 0, "total": 3}) as mock_send,
        ):
            cron.fetch_rates_and_send_all_alerts()

        mock_call_command.assert_called_once_with("fetch_rates", days=3, no_alerts=True)
        mock_send.assert_called_once_with()
