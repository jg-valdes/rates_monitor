import datetime
import io
import posixpath
import re
import subprocess
import time
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from html.parser import HTMLParser
from xml.etree import ElementTree

import requests

from rates.services.payment_calculations import add_months

DEFAULT_CUB_SOURCE_URL = "https://www.sindusconbc.com.br/cub/"
DEFAULT_CUB_CURRENT_SOURCE_URL = "https://sinduscon-fpolis.org.br/servico/cub-mensal/"
# "Tabelas CUB > 1 - CUB NORMA 2006 > 1 - CUB RESIDENCIAL MÉDIO" on the Sinduscon
# page is this public Google Sheet. It is updated on the 1st, before the monthly card.
DEFAULT_CUB_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1_XfU1kxOT36xot8o6iRMBOPZ63VYNhvTtXHFMw4Hr2E/export?format=xlsx"
)

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


def parse_current_cub(html: str, source_url: str = DEFAULT_CUB_CURRENT_SOURCE_URL) -> CubPreview:
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
        raise CubFetchError('El bloque "Residencial Médio" no contiene un mes y valor CUB válidos.')

    reference_month, reference_year = reference_match.groups()
    applicable_month, applicable_year = applicable_match.groups()
    variation = None
    if variation_match:
        normalized = variation_match.group(1).replace(" ", "").replace("–", "-")
        variation = _br_decimal(normalized.lstrip("+"))
    return CubPreview(
        reference_month=datetime.date(int(reference_year), _month_number(reference_month), 1),
        applicable_month=datetime.date(int(applicable_year), _month_number(applicable_month), 1),
        value=_br_decimal(value_match.group(1)),
        monthly_variation=variation,
        source_url=source_url,
    )


_XLSX_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_XLSX_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _xlsx_rels(archive: zipfile.ZipFile, part: str) -> dict[str, str]:
    folder, name = posixpath.split(part)
    rels_path = posixpath.join(folder, "_rels", f"{name}.rels")
    if rels_path not in archive.namelist():
        return {}
    root = ElementTree.fromstring(archive.read(rels_path))
    return {
        rel.get("Id"): posixpath.normpath(posixpath.join(folder, rel.get("Target")))
        for rel in root.findall("rel:Relationship", _XLSX_NS)
    }


def extract_cub_sheet_images(content: bytes) -> tuple[int, list[bytes]]:
    """Return the latest year tab and the images pasted on it.

    Sinduscon pastes the yearly table as a picture, so the cells carry no values.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise CubFetchError("La planilla CUB no es un archivo xlsx válido.") from exc

    sheets = {
        int(sheet.get("name").strip()): sheet.get(_XLSX_REL_ID)
        for sheet in workbook.findall("main:sheets/main:sheet", _XLSX_NS)
        if sheet.get("name", "").strip().isdigit()
    }
    if not sheets:
        raise CubFetchError("La planilla CUB no contiene pestañas por año.")

    year = max(sheets)
    sheet_part = _xlsx_rels(archive, "xl/workbook.xml").get(sheets[year])
    images = []
    for drawing_part in _xlsx_rels(archive, sheet_part).values():
        if "/drawings/" not in drawing_part:
            continue
        for media_part in _xlsx_rels(archive, drawing_part).values():
            if "/media/" in media_part:
                images.append(archive.read(media_part))
    if not images:
        raise CubFetchError(f"La pestaña {year} de la planilla CUB no contiene la tabla.")
    return year, images


def _ocr_image(image: bytes) -> str:
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "--psm", "4"],
            input=image,
            capture_output=True,
            timeout=30,
            check=True,
        )
    except FileNotFoundError as exc:
        raise CubFetchError("tesseract no está instalado para leer la planilla CUB.") from exc
    except (subprocess.SubprocessError, OSError) as exc:
        raise CubFetchError(f"No se pudo leer la tabla de la planilla CUB: {exc}") from exc
    return result.stdout.decode("utf-8", errors="replace")


_ABBREVIATIONS = (
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
)


def parse_cub_sheet_table(
    text: str, year: int, source_url: str = DEFAULT_CUB_SHEET_URL
) -> CubPreview:
    """Read the newest row of the OCR'd yearly table.

    Rows run newest first and the tab always ends with "DEZ -> JAN", so the row
    count gives the applicable month. OCR is noisy on month labels and
    percentages but reliable on the R$ values, which are used for the variation.
    """
    rows = []
    for line in text.splitlines():
        value_match = re.search(r"(\d\.\d{3},\d{2})", line)
        if value_match:
            labels = re.findall(r"[a-z]{3}", line[: value_match.start()].lower())
            rows.append((labels, _br_decimal(value_match.group(1))))
    if not rows or len(rows) > 12:
        raise CubFetchError("La tabla de la planilla CUB no tiene un formato reconocible.")

    applicable = datetime.date(year, len(rows), 1)
    # A dropped row shifts the month, so check the labels OCR could read.
    labels = [label for label in rows[0][0] if label in _ABBREVIATIONS]
    expected = _ABBREVIATIONS[applicable.month - 1]
    previous = _ABBREVIATIONS[applicable.month - 2]
    if (len(labels) >= 2 and labels[-1] != expected) or (
        len(labels) == 1 and labels[0] not in (expected, previous)
    ):
        raise CubFetchError("La tabla de la planilla CUB no coincide con el mes esperado.")

    values = [value for _, value in rows]
    for newer, older in zip(values, values[1:]):
        if abs(newer / older - 1) > Decimal("0.1"):
            raise CubFetchError("La tabla de la planilla CUB tiene valores inconsistentes.")

    variation = None
    if len(values) > 1:
        variation = ((values[0] / values[1] - 1) * 100).quantize(Decimal("0.01"))
    return CubPreview(
        reference_month=add_months(applicable, -1),
        applicable_month=applicable,
        value=values[0],
        monthly_variation=variation,
        source_url=source_url,
    )


def fetch_cub_sheet(url: str = DEFAULT_CUB_SHEET_URL) -> CubPreview:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CubFetchError(f"No se pudo consultar la planilla CUB: {exc}") from exc
    year, images = extract_cub_sheet_images(response.content)
    error = None
    for image in images:
        try:
            return parse_cub_sheet_table(_ocr_image(image), year, source_url=url)
        except CubFetchError as exc:
            error = exc
    raise error


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


def _fetch_current_cub(
    current_url: str | None, sheet_url: str | None, today: datetime.date
) -> list[CubPreview]:
    """Prefer the Google Sheet; use the monthly card when it fails or lags."""
    found = []
    sheet_error = None
    if sheet_url:
        try:
            found.append(fetch_cub_sheet(sheet_url))
        except CubFetchError as exc:
            sheet_error = exc
        if found and found[0].applicable_month >= today.replace(day=1):
            return found
    if current_url:
        try:
            html = _fetch_html(current_url, bypass_cache=True)
            found.append(parse_current_cub(html, source_url=current_url))
        except CubFetchError:
            if not found:
                raise
    elif sheet_error is not None:
        raise sheet_error
    return found


def fetch_cub_history(
    url: str = DEFAULT_CUB_SOURCE_URL,
    current_url: str | None = None,
    sheet_url: str | None = None,
    today: datetime.date | None = None,
) -> list[CubPreview]:
    history = parse_cub_history(_fetch_html(url), source_url=url)
    current = _fetch_current_cub(current_url, sheet_url, today or datetime.date.today())
    combined = {item.applicable_month: item for item in history}
    # Later sources are fallbacks, so they never replace a month already found.
    for item in reversed(current):
        combined[item.applicable_month] = item
    return sorted(combined.values(), key=lambda item: item.applicable_month, reverse=True)
