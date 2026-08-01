import datetime
from decimal import Decimal

from django import forms

from rates.models import PaymentObligation, PaymentTransaction
from rates.services.payment_calculations import add_months

INPUT_CLASS = (
    "w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm "
    "focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
)
CHECKBOX_CLASS = "rounded border-gray-600 bg-gray-900 text-indigo-500 focus:ring-indigo-500"


def date_widget():
    return forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


def month_widget():
    return forms.DateInput(format="%Y-%m", attrs={"type": "month"})


class PaymentPlanSetupForm(forms.Form):
    name = forms.CharField(label="Vivienda", max_length=120)
    contract_date = forms.DateField(label="Fecha del contrato", widget=date_widget())
    base_cub_month = forms.DateField(
        label="Mes CUB base",
        widget=month_widget(),
        input_formats=["%Y-%m"],
    )
    base_cub_value = forms.DecimalField(
        label="Valor CUB base", min_value=Decimal("0.01"), decimal_places=2
    )
    down_payment_enabled = forms.BooleanField(label="Tiene pago de entrada", required=False)
    down_payment_first_due_date = forms.DateField(
        label="Primer vencimiento", required=False, widget=date_widget()
    )
    down_payment_count = forms.IntegerField(label="Cantidad de plazos", min_value=1, required=False)
    down_payment_interval_months = forms.IntegerField(
        label="Frecuencia en meses", min_value=1, required=False, initial=1
    )
    down_payment_amount = forms.DecimalField(
        label="Importe por plazo", min_value=Decimal("0.01"), decimal_places=2, required=False
    )
    down_payment_applies_cub = forms.BooleanField(
        label="Ajustar entrada por CUB", required=False, initial=False
    )
    monthly_first_due_date = forms.DateField(label="Primera cuota", widget=date_widget())
    monthly_count = forms.IntegerField(label="Cantidad de cuotas", min_value=1)
    monthly_amount = forms.DecimalField(
        label="Cuota base", min_value=Decimal("0.01"), decimal_places=2
    )
    monthly_applies_cub = forms.BooleanField(
        label="Ajustar cuotas por CUB", required=False, initial=True
    )
    reinforcement_enabled = forms.BooleanField(label="Tiene refuerzos anuales", required=False)
    reinforcement_first_due_date = forms.DateField(
        label="Primer refuerzo", required=False, widget=date_widget()
    )
    reinforcement_count = forms.IntegerField(
        label="Cantidad de refuerzos", min_value=1, required=False
    )
    reinforcement_amount = forms.DecimalField(
        label="Refuerzo base", min_value=Decimal("0.01"), decimal_places=2, required=False
    )
    reinforcement_applies_cub = forms.BooleanField(
        label="Ajustar refuerzos por CUB", required=False, initial=True
    )
    keys_enabled = forms.BooleanField(label="Tiene pago de entrega de llaves", required=False)
    keys_due_date = forms.DateField(label="Fecha de llaves", required=False, widget=date_widget())
    keys_amount = forms.DecimalField(
        label="Pago de llaves", min_value=Decimal("0.01"), decimal_places=2, required=False
    )
    keys_applies_cub = forms.BooleanField(
        label="Ajustar llaves por CUB", required=False, initial=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = CHECKBOX_CLASS
            else:
                field.widget.attrs["class"] = INPUT_CLASS

    def clean_base_cub_month(self):
        return self.cleaned_data["base_cub_month"].replace(day=1)

    def clean(self):
        cleaned = super().clean()
        required_groups = [
            (
                "down_payment_enabled",
                (
                    "down_payment_first_due_date",
                    "down_payment_count",
                    "down_payment_interval_months",
                    "down_payment_amount",
                ),
            ),
            (
                "reinforcement_enabled",
                ("reinforcement_first_due_date", "reinforcement_count", "reinforcement_amount"),
            ),
            ("keys_enabled", ("keys_due_date", "keys_amount")),
        ]
        for toggle, fields in required_groups:
            if cleaned.get(toggle):
                for field_name in fields:
                    if cleaned.get(field_name) in (None, ""):
                        self.add_error(
                            field_name, "Este campo es obligatorio cuando la opción está activa."
                        )
        return cleaned

    def schedule_preview(self):
        if not self.is_valid():
            return []
        data = self.cleaned_data
        rows = []
        if data.get("down_payment_enabled"):
            for index in range(data["down_payment_count"]):
                rows.append(
                    (
                        "DOWN_PAYMENT",
                        index + 1,
                        add_months(
                            data["down_payment_first_due_date"],
                            index * data["down_payment_interval_months"],
                        ),
                        data["down_payment_amount"],
                        data["down_payment_applies_cub"],
                    )
                )
        for index in range(data["monthly_count"]):
            rows.append(
                (
                    "MONTHLY",
                    index + 1,
                    add_months(data["monthly_first_due_date"], index),
                    data["monthly_amount"],
                    data["monthly_applies_cub"],
                )
            )
        if data.get("reinforcement_enabled"):
            for index in range(data["reinforcement_count"]):
                rows.append(
                    (
                        "REINFORCEMENT",
                        index + 1,
                        add_months(data["reinforcement_first_due_date"], index * 12),
                        data["reinforcement_amount"],
                        data["reinforcement_applies_cub"],
                    )
                )
        if data.get("keys_enabled"):
            rows.append(
                ("KEYS", 1, data["keys_due_date"], data["keys_amount"], data["keys_applies_cub"])
            )
        return sorted(rows, key=lambda row: (row[2], row[0]))


class CubIndexValueForm(forms.Form):
    applicable_month = forms.DateField(
        label="Mes de uso", widget=month_widget(), input_formats=["%Y-%m"]
    )
    value = forms.DecimalField(label="Valor CUB", min_value=Decimal("0.01"), decimal_places=2)
    monthly_variation = forms.DecimalField(
        label="Variación mensual (%)", required=False, decimal_places=4
    )
    source_url = forms.URLField(label="Fuente", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASS

    def clean_applicable_month(self):
        return self.cleaned_data["applicable_month"].replace(day=1)

    def reference_month(self):
        return add_months(self.cleaned_data["applicable_month"], -1)


class PaymentTransactionForm(forms.ModelForm):
    class Meta:
        model = PaymentTransaction
        fields = ["paid_on", "amount", "note"]
        widgets = {"paid_on": date_widget()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paid_on"].initial = datetime.date.today()
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASS


class PaymentObligationForm(forms.ModelForm):
    class Meta:
        model = PaymentObligation
        fields = ["due_date", "base_amount", "applies_cub", "final_amount_override"]
        widgets = {"due_date": date_widget()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = CHECKBOX_CLASS
            else:
                field.widget.attrs["class"] = INPUT_CLASS
