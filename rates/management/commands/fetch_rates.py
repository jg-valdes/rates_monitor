import logging

from django.core.management.base import BaseCommand

from rates.models import CurrencyPair, ExchangeRate, PairConfig
from rates.services.alerts import check_and_send
from rates.services.cross_pair import compute_cross_pair
from rates.services.decision import build_decision
from rates.services.fetcher import fetch_and_store
from rates.services.indicators import compute_all
from rates.translations import CONFIDENCE_LABELS, MOMENTUM_LABELS, SIGNAL_LABELS

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fetch rates for all active pairs, compute signals, and fire alerts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Number of days to fetch (default: 90). Use 2-3 for daily updates.",
        )
        parser.add_argument(
            "--pair",
            type=str,
            default=None,
            help="Specific pair code to update (e.g. usd-brl). Default: all active pairs.",
        )
        parser.add_argument(
            "--no-alerts",
            action="store_true",
            help="Skip alert evaluation on this run.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        pair_filter = options["pair"]

        pairs = CurrencyPair.objects.filter(active=True)
        if pair_filter:
            pairs = pairs.filter(code=pair_filter.upper())
            if not pairs.exists():
                self.stderr.write(self.style.ERROR(f"Pair not found: {pair_filter}"))
                return

        for pair in pairs:
            self._process_pair(pair, days, no_alerts=options["no_alerts"])

        # Cross-pair route comparison after all pairs are updated
        cross = compute_cross_pair()
        if cross:
            self.stdout.write("\n── UYU → BRL Route Comparator ──────────────────")
            self.stdout.write(
                f"  Direct route   (UYU→BRL):         {cross['direct_rate']:.6f} BRL/UYU"
            )
            self.stdout.write(
                f"  Indirect route (UYU→USD→BRL):     {cross['indirect_rate']:.6f} BRL/UYU"
            )
            best = "DIRECT" if cross["best_route"] == "direct" else "INDIRECT"
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Best route: {best}  (+{cross['advantage_pct']:.4f}% more BRL per peso)"
                )
            )
            self.stdout.write("─────────────────────────────────────────────────\n")

    def _process_pair(self, pair, days, no_alerts):
        self.stdout.write(f"\nFetching last {days} days of {pair.code} — {pair.name}…")

        try:
            created, updated = fetch_and_store(pair, days=days)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"  Error fetching {pair.code}: {exc}"))
            return

        self.stdout.write(self.style.SUCCESS(f"  {created} new records, {updated} updated"))

        rates_list = list(ExchangeRate.objects.filter(pair=pair).order_by("date"))
        if not rates_list:
            self.stderr.write(f"  No data for {pair.code}.")
            return

        config, _ = PairConfig.objects.get_or_create(pair=pair)
        indicators = compute_all(rates_list)
        decision = build_decision(indicators, config)

        signal_es = SIGNAL_LABELS.get(decision["signal"], decision["signal"])
        confidence_es = CONFIDENCE_LABELS.get(decision["confidence"], decision["confidence"])
        momentum_es = MOMENTUM_LABELS.get(indicators["momentum"], indicators["momentum"])
        direction = "above" if indicators["deviation"] > 0 else "below"

        self.stdout.write(f"  ── Indicators {pair.code} ───────────────────────")
        self.stdout.write(f"    Date:        {indicators['current_date']}")
        self.stdout.write(f"    Rate:        {indicators['current_rate']:.4f}")
        self.stdout.write(f"    MA 30:       {indicators['ma30']:.4f}")
        self.stdout.write(f"    MA 90:       {indicators['ma90']:.4f}")
        self.stdout.write(f"    Deviation:   {indicators['deviation']:+.2f}%  ({direction} MA90)")
        self.stdout.write(
            f"    Momentum:    {momentum_es}   Volatility: {indicators['volatility']:.4f}"
        )
        self.stdout.write(
            self.style.SUCCESS(f"    Signal: {signal_es}  [confidence {confidence_es}]")
        )
        self.stdout.write(
            f"    Allocation:  ${decision['suggested_amount']:.0f}  "
            f"({decision['allocation_pct']}% of ${config.monthly_budget:.0f} budget)"
        )

        if not no_alerts:
            triggered = check_and_send(indicators, decision, config, pair_name=pair.name)
            if triggered:
                for alert in triggered:
                    self.stdout.write(self.style.WARNING(f"    🔔 {alert}"))
            else:
                self.stdout.write("    No alerts triggered.")
