import logging

import requests
from django.conf import settings

from rates.services.oer_fetcher import BASE_URL, OERError

logger = logging.getLogger(__name__)


def fetch_usage_summary() -> dict:
    """Fetch and normalize the Open Exchange Rates usage payload."""
    app_id = getattr(settings, "OPENEXCHANGERATES_APP_ID", "")
    if not app_id:
        raise OERError("OPENEXCHANGERATES_APP_ID is not set")

    try:
        resp = requests.get(
            f"{BASE_URL}/usage.json",
            params={"app_id": app_id, "prettyprint": "true"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise OERError(f"Network error: {exc}") from exc

    if not resp.ok:
        raise OERError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    payload = resp.json().get("data", {})
    plan = payload.get("plan", {})
    usage = payload.get("usage", {})
    quota = usage.get("requests_quota") or 0
    requests_used = usage.get("requests") or 0
    usage_pct = round((requests_used / quota) * 100, 2) if quota else 0.0

    return {
        "app_id": payload.get("app_id", ""),
        "status": payload.get("status", "unknown"),
        "plan_name": plan.get("name", "Unknown"),
        "quota_label": plan.get("quota", "Unknown"),
        "update_frequency": plan.get("update_frequency", "Unknown"),
        "features": plan.get("features", {}),
        "requests_used": requests_used,
        "requests_quota": quota,
        "requests_remaining": usage.get("requests_remaining") or 0,
        "days_elapsed": usage.get("days_elapsed") or 0,
        "days_remaining": usage.get("days_remaining") or 0,
        "daily_average": usage.get("daily_average") or 0,
        "usage_pct": min(usage_pct, 100.0),
    }
