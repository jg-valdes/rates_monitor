import datetime
import re
from dataclasses import dataclass
from decimal import Decimal
from html.parser import HTMLParser

import requests

from rates.services.payment_calculations import add_months

DEFAULT_CUB_SOURCE_URL = "https://www.sindusconbc.com.br/cub/"

MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


class CubFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class CubPreview:
    reference_month: datetime.date
    applicable_month: datetime.date
    value: Decimal
    monthly_variation: Decimal | None
    source_url: str


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        value = data.strip()
        if value:
            self.parts.append(value)


def _br_decimal(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(",", "."))


def parse_cub_history(html: str, source_url: str = DEFAULT_CUB_SOURCE_URL) -> list[CubPreview]:
    parser = _TextExtractor()
    parser.feed(html)
    text = " ".join(parser.parts)
    standard_text = re.split(r"CUB\s*/?\s*Desonerado", text, maxsplit=1, flags=re.IGNORECASE)[0]
    month_names = "|".join(MONTHS)
    heading_pattern = re.compile(
        rf"CUB\s*/\s*({month_names})\s*(?:de|/)?\s*(20\d{{2}})",
        re.IGNORECASE,
    )
    headings = list(heading_pattern.finditer(standard_text))
    previews = []
    for index, heading in enumerate(headings):
        block_end = headings[index + 1].start() if index + 1 < len(headings) else len(standard_text)
        block = standard_text[heading.end() : block_end]
        value_match = re.search(r"R\$\s*([\d.]+,\d{2})", block, flags=re.IGNORECASE)
        if value_match is None:
            continue
        variation_match = re.search(
            r"varia(?:ção|cao)\s*([+\-–]?\s*[\d.,]+)\s*%", block, flags=re.IGNORECASE
        )
        month_name, year = heading.groups()
        raw_value = value_match.group(1)
        raw_variation = variation_match.group(1) if variation_match else None
        applicable = datetime.date(int(year), MONTHS[month_name.lower()], 1)
        variation = None
        if raw_variation:
            normalized = raw_variation.replace(" ", "").replace("–", "-")
            variation = _br_decimal(normalized.lstrip("+"))
        previews.append(
            CubPreview(
                reference_month=add_months(applicable, -1),
                applicable_month=applicable,
                value=_br_decimal(raw_value),
                monthly_variation=variation,
                source_url=source_url,
            )
        )
    if not previews:
        raise CubFetchError("No se encontraron valores CUB estándar en la fuente oficial.")
    unique = {item.applicable_month: item for item in previews}
    return sorted(unique.values(), key=lambda item: item.applicable_month, reverse=True)


def fetch_cub_history(url: str = DEFAULT_CUB_SOURCE_URL) -> list[CubPreview]:
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CubFetchError(f"No se pudo consultar la fuente CUB: {exc}") from exc
    return parse_cub_history(response.text, source_url=url)
