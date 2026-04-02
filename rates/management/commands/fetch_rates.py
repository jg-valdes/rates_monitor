import logging

from django.core.management.base import BaseCommand

from rates.models import ExchangeRate, UserConfig
from rates.services.alerts import check_and_send
from rates.services.decision import build_decision
from rates.services.fetcher import fetch_and_store
from rates.services.indicators import compute_all
from rates.translations import CONFIDENCE_LABELS, MOMENTUM_LABELS, SIGNAL_LABELS

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Obtiene cotizaciones USD/BRL, calcula señales y dispara alertas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Cantidad de días a obtener (por defecto: 90). Usar 2-3 para actualizaciones diarias.",
        )
        parser.add_argument(
            "--no-alerts",
            action="store_true",
            help="Omitir verificación de alertas.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        self.stdout.write(f"Obteniendo últimos {days} días de USD/BRL…")

        try:
            created, updated = fetch_and_store(days=days)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Error al obtener datos: {exc}"))
            return

        self.stdout.write(
            self.style.SUCCESS(f"  {created} registros nuevos, {updated} actualizados")
        )

        rates_list = list(ExchangeRate.objects.order_by("date"))
        if not rates_list:
            self.stderr.write("No hay datos en la base de datos.")
            return

        config = UserConfig.get_solo()
        indicators = compute_all(rates_list)
        decision = build_decision(indicators, config)

        signal_es = SIGNAL_LABELS.get(decision["signal"], decision["signal"])
        confidence_es = CONFIDENCE_LABELS.get(decision["confidence"], decision["confidence"])
        momentum_es = MOMENTUM_LABELS.get(indicators["momentum"], indicators["momentum"])
        direction = "sobre" if indicators["deviation"] > 0 else "bajo"

        self.stdout.write("\n── Indicadores Actuales ─────────────────────")
        self.stdout.write(f"  Fecha:        {indicators['current_date']}")
        self.stdout.write(f"  Cotización:   {indicators['current_rate']:.4f} BRL")
        self.stdout.write(f"  MA 30:        {indicators['ma30']:.4f}")
        self.stdout.write(f"  MA 90:        {indicators['ma90']:.4f}")
        self.stdout.write(
            f"  Desviación:   {indicators['deviation']:+.2f}%  "
            f"({direction} de la MA90)"
        )
        self.stdout.write(
            f"  Tendencia:    {momentum_es}   "
            f"Volatilidad: {indicators['volatility']:.4f}"
        )
        self.stdout.write("─────────────────────────────────────────────")
        self.stdout.write(
            self.style.SUCCESS(
                f"  Señal:        {signal_es}  [confianza {confidence_es}]"
            )
        )
        self.stdout.write(
            f"  Asignación:   ${decision['suggested_amount']:.0f}  "
            f"({decision['allocation_pct']}% de ${config.monthly_usd_budget:.0f} presupuesto)"
        )
        self.stdout.write("")

        if not options["no_alerts"]:
            triggered = check_and_send(indicators, decision, config)
            if triggered:
                for alert in triggered:
                    self.stdout.write(self.style.WARNING(f"  🔔 {alert}"))
            else:
                self.stdout.write("  Sin alertas disparadas.")
