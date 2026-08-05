import datetime
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from html.parser import HTMLParser

import requests

from rates.services.payment_calculations import add_months

DEFAULT_CUB_SOURCE_URL = "https://www.sindusconbc.com.br/cub/"
DEFAULT_CUB_CURRENT_SOURCE_URL = "https://sinduscon-fpolis.org.br/servico/cub-mensal/"

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


def _month_number(value: str) -> int:
    return int(value) if value.isdigit() else MONTHS[value.lower()]


def _page_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return " ".join(parser.parts)


def parse_cub_history(html: str, source_url: str = DEFAULT_CUB_SOURCE_URL) -> list[CubPreview]:
    text = _page_text(html)
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


def parse_current_cub(
    html: str, source_url: str = DEFAULT_CUB_CURRENT_SOURCE_URL
) -> CubPreview:
    text = _page_text(html)
    residential_match = re.search(
        r"Residencial\s+M[ée]dio(?P<block>.*?)(?:Comercial\s+M[ée]dio|$)",
        text,
        flags=re.IGNORECASE,
    )
    if residential_match is None:
        raise CubFetchError('No se encontró el bloque "Residencial Médio" en la fuente mensual.')

    block = residential_match.group("block")
    month_token = rf"(\d{{1,2}}|{'|'.join(MONTHS)})"
    reference_match = re.search(
        rf"M[eê]s\s+de\s+Refer[êe]ncia\s*:\s*{month_token}\s*/\s*(20\d{{2}})",
        block,
        flags=re.IGNORECASE,
    )
    applicable_match = re.search(
        rf"Para\s+ser\s+usado\s+em\s*:\s*{month_token}\s*/\s*(20\d{{2}})",
        block,
        flags=re.IGNORECASE,
    )
    value_match = re.search(r"R\$\s*([\d.]+,\d{2})", block, flags=re.IGNORECASE)
    variation_match = re.search(r"([+\-–]?\s*[\d.,]+)\s*%", block)
    if reference_match is None or applicable_match is None or value_match is None:
        raise CubFetchError(
            'El bloque "Residencial Médio" no contiene un mes y valor CUB válidos.'
        )

    reference_month, reference_year = reference_match.groups()
    applicable_month, applicable_year = applicable_match.groups()
    variation = None
    if variation_match:
        normalized = variation_match.group(1).replace(" ", "").replace("–", "-")
        variation = _br_decimal(normalized.lstrip("+"))
    return CubPreview(
        reference_month=datetime.date(int(reference_year), _month_number(reference_month), 1),
        applicable_month=datetime.date(
            int(applicable_year), _month_number(applicable_month), 1
        ),
        value=_br_decimal(value_match.group(1)),
        monthly_variation=variation,
        source_url=source_url,
    )


def _fetch_html(url: str, *, bypass_cache: bool = False) -> str:
    try:
        request_kwargs = {"timeout": 15}
        if bypass_cache:
            # This WordPress page can serve an outdated full-page cache even after
            # its visible monthly card has been updated.
            request_kwargs["params"] = {"_": int(time.time())}
            request_kwargs["headers"] = {"User-Agent": "Mozilla/5.0 RatesMonitor/0.1"}
        response = requests.get(url, **request_kwargs)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CubFetchError(f"No se pudo consultar la fuente CUB: {exc}") from exc
    return response.text


def fetch_cub_history(
    url: str = DEFAULT_CUB_SOURCE_URL,
    current_url: str | None = None,
) -> list[CubPreview]:
    history = parse_cub_history(_fetch_html(url), source_url=url)
    if current_url is None:
        return history

    current = parse_current_cub(
        _fetch_html(current_url, bypass_cache=True), source_url=current_url
    )
    combined = {item.applicable_month: item for item in history}
    combined[current.applicable_month] = current
    return sorted(combined.values(), key=lambda item: item.applicable_month, reverse=True)
