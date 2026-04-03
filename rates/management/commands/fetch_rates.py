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
    help = "Obtiene cotizaciones de todos los pares activos, calcula señales y dispara alertas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Cantidad de días a obtener (por defecto: 90). Usar 2-3 para actualizaciones diarias.",
        )
        parser.add_argument(
            "--pair",
            type=str,
            default=None,
            help="Código de par específico a actualizar (ej: usd-brl). Por defecto: todos los activos.",
        )
        parser.add_argument(
            "--no-alerts",
            action="store_true",
            help="Omitir verificación de alertas.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        pair_filter = options["pair"]

        pairs = CurrencyPair.objects.filter(active=True)
        if pair_filter:
            pairs = pairs.filter(code=pair_filter.upper())
            if not pairs.exists():
                self.stderr.write(self.style.ERROR(f"Par no encontrado: {pair_filter}"))
                return

        for pair in pairs:
            self._process_pair(pair, days, no_alerts=options["no_alerts"])

        # Cross-pair route comparison after all pairs are updated
        cross = compute_cross_pair()
        if cross:
            self.stdout.write("\n── Comparador de Rutas UYU → BRL ───────────────")
            self.stdout.write(f"  Ruta directa   (UYU→BRL):         {cross['direct_rate']:.6f} BRL/UYU")
            self.stdout.write(f"  Ruta indirecta (UYU→USD→BRL):     {cross['indirect_rate']:.6f} BRL/UYU")
            mejor = "DIRECTA" if cross["best_route"] == "directa" else "INDIRECTA"
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Mejor ruta: {mejor}  (+{cross['advantage_pct']:.4f}% más BRL por peso)"
                )
            )
            self.stdout.write("─────────────────────────────────────────────────\n")

    def _process_pair(self, pair, days, no_alerts):
        self.stdout.write(f"\nObteniendo últimos {days} días de {pair.code} — {pair.name}…")

        try:
            created, updated = fetch_and_store(pair, days=days)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"  Error al obtener {pair.code}: {exc}"))
            return

        self.stdout.write(
            self.style.SUCCESS(f"  {created} registros nuevos, {updated} actualizados")
        )

        rates_list = list(ExchangeRate.objects.filter(pair=pair).order_by("date"))
        if not rates_list:
            self.stderr.write(f"  Sin datos para {pair.code}.")
            return

        config, _ = PairConfig.objects.get_or_create(pair=pair)
        indicators = compute_all(rates_list)
        decision   = build_decision(indicators, config)

        signal_es    = SIGNAL_LABELS.get(decision["signal"], decision["signal"])
        confidence_es = CONFIDENCE_LABELS.get(decision["confidence"], decision["confidence"])
        momentum_es  = MOMENTUM_LABELS.get(indicators["momentum"], indicators["momentum"])
        direction    = "sobre" if indicators["deviation"] > 0 else "bajo"

        self.stdout.write(f"  ── Indicadores {pair.code} ──────────────────────")
        self.stdout.write(f"    Fecha:       {indicators['current_date']}")
        self.stdout.write(f"    Cotización:  {indicators['current_rate']:.4f}")
        self.stdout.write(f"    MA 30:       {indicators['ma30']:.4f}")
        self.stdout.write(f"    MA 90:       {indicators['ma90']:.4f}")
        self.stdout.write(
            f"    Desviación:  {indicators['deviation']:+.2f}%  ({direction} de la MA90)"
        )
        self.stdout.write(
            f"    Tendencia:   {momentum_es}   Volatilidad: {indicators['volatility']:.4f}"
        )
        self.stdout.write(
            self.style.SUCCESS(f"    Señal: {signal_es}  [confianza {confidence_es}]")
        )
        self.stdout.write(
            f"    Asignación:  ${decision['suggested_amount']:.0f}  "
            f"({decision['allocation_pct']}% de ${config.monthly_budget:.0f} presupuesto)"
        )

        if not no_alerts:
            triggered = check_and_send(indicators, decision, config, pair_name=pair.name)
            if triggered:
                for alert in triggered:
                    self.stdout.write(self.style.WARNING(f"    🔔 {alert}"))
            else:
                self.stdout.write("    Sin alertas disparadas.")
