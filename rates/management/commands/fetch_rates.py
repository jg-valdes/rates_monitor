import logging

from django.core.management.base import BaseCommand

from rates.models import ExchangeRate, UserConfig
from rates.services.alerts import check_and_send
from rates.services.decision import build_decision
from rates.services.fetcher import fetch_and_store
from rates.services.indicators import compute_all

logger = logging.getLogger(__name__)

MOMENTUM_ICONS = {"up": "↑", "down": "↓", "neutral": "→"}


class Command(BaseCommand):
    help = "Fetch USD/BRL exchange rates, compute signals, and trigger alerts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Number of days to fetch (default: 90). Use 2-3 for daily updates.",
        )
        parser.add_argument(
            "--no-alerts",
            action="store_true",
            help="Skip alert checks.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        self.stdout.write(f"Fetching last {days} days of USD/BRL…")

        try:
            created, updated = fetch_and_store(days=days)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Fetch failed: {exc}"))
            return

        self.stdout.write(
            self.style.SUCCESS(f"  {created} new records, {updated} updated")
        )

        rates_list = list(ExchangeRate.objects.order_by("date"))
        if not rates_list:
            self.stderr.write("No data in database.")
            return

        config = UserConfig.get_solo()
        indicators = compute_all(rates_list)
        decision = build_decision(indicators, config)

        momentum_icon = MOMENTUM_ICONS.get(indicators["momentum"], "→")

        self.stdout.write("\n── Current Indicators ──────────────────")
        self.stdout.write(f"  Date:       {indicators['current_date']}")
        self.stdout.write(f"  Rate:       {indicators['current_rate']:.4f} BRL")
        self.stdout.write(f"  MA 30:      {indicators['ma30']:.4f}")
        self.stdout.write(f"  MA 90:      {indicators['ma90']:.4f}")
        self.stdout.write(
            f"  Deviation:  {indicators['deviation']:+.2f}%  "
            f"({'above' if indicators['deviation'] > 0 else 'below'} MA90)"
        )
        self.stdout.write(
            f"  Momentum:   {momentum_icon} {indicators['momentum']}  "
            f"  Volatility: {indicators['volatility']:.4f}"
        )
        self.stdout.write("────────────────────────────────────────")
        self.stdout.write(
            self.style.SUCCESS(
                f"  Signal:     {decision['signal']}  [{decision['confidence']} confidence]"
            )
        )
        self.stdout.write(
            f"  Allocation: ${decision['suggested_amount']:.0f}  "
            f"({decision['allocation_pct']}% of ${config.monthly_usd_budget:.0f} budget)"
        )
        self.stdout.write("")

        if not options["no_alerts"]:
            triggered = check_and_send(indicators, decision, config)
            if triggered:
                for alert in triggered:
                    self.stdout.write(self.style.WARNING(f"  🔔 {alert}"))
            else:
                self.stdout.write("  No alerts triggered.")
