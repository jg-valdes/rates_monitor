import pytest

from rates.services.oer_quota import can_make_request, get_quota_status, record_request


@pytest.mark.django_db
class TestOERQuota:
    def test_records_and_reports_monthly_usage(self, settings):
        settings.OER_MONTHLY_REQUEST_QUOTA = 1000
        settings.OER_TARGET_USAGE_RATIO = 0.95

        record_request()
        status = get_quota_status()

        assert status["used"] == 1
        assert status["target_quota"] == 950
        assert status["remaining_target"] == 949

    def test_blocks_when_target_cap_is_reached(self, settings):
        settings.OER_MONTHLY_REQUEST_QUOTA = 10
        settings.OER_TARGET_USAGE_RATIO = 0.5

        for _ in range(5):
            record_request()

        allowed, reason = can_make_request()

        assert allowed is False
        assert "monthly cap" in reason

    def test_interval_guard_can_be_bypassed_for_manual_refresh(self, settings):
        settings.OER_MONTHLY_REQUEST_QUOTA = 100
        settings.OER_TARGET_USAGE_RATIO = 0.9
        settings.OER_MIN_REQUEST_INTERVAL_MINUTES = 240
        record_request()

        allowed, _ = can_make_request(ignore_interval=True)

        assert allowed is True
