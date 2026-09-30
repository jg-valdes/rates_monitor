import datetime
import io
import subprocess
import zipfile
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from rates.services.cub_fetcher import (
    CubFetchError,
    CubPreview,
    _ocr_image,
    extract_cub_sheet_images,
    fetch_cub_history,
    fetch_cub_sheet,
    parse_cub_sheet_table,
)

SHEET_URL = "https://sheet.example/export"
CURRENT_URL = "https://official.example/cub-current"
HISTORY_URL = "https://official.example/cub-history"

# Real tesseract output for the 2026 tab, including its OCR noise.
OCR_TEXT = """Dados do més de: | Para ser usado em:| CUB médio (R)_| % Més. % Ano | % 12 meses

‘AGO SET 3.158,88, 0,249 485% 554%.
JUL ‘AGO 3.151,24 0,95% 4,60% 5.82%
JUN JUL 3.121,62 0,829 362% 526%
MAL JUN 3.096,25 1,05% 2,78%: 551%
‘ABR MAL 3.064,10 0,879 L719 481%
MAR ‘ABR 3.037,72 0.31% 0,83% 417%
FEV MAR 3.028,45) 0,30% 052% 4,15%
JAN FEV 3.019,26 0,229 0,229 4,07%

DEZ JAN 3.012,64 0,13% 4,32% 4,32%
"""

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DOC_RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _rels(targets):
    items = "".join(
        f'<Relationship Id="{rel_id}" Type="x" Target="{target}"/>'
        for rel_id, target in targets.items()
    )
    return f'<Relationships xmlns="{_RELS}">{items}</Relationships>'


def _xlsx(tabs):
    """Build a minimal workbook: {tab name: image bytes or None}."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        sheets, workbook_rels = [], {}
        for index, (name, image) in enumerate(tabs.items(), start=1):
            sheets.append(f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>')
            workbook_rels[f"rId{index}"] = f"worksheets/sheet{index}.xml"
            archive.writestr(f"xl/worksheets/sheet{index}.xml", "<worksheet/>")
            if image is None:
                continue
            archive.writestr(
                f"xl/worksheets/_rels/sheet{index}.xml.rels",
                _rels({"rId1": f"../drawings/drawing{index}.xml"}),
            )
            archive.writestr(f"xl/drawings/drawing{index}.xml", "<wsDr/>")
            archive.writestr(
                f"xl/drawings/_rels/drawing{index}.xml.rels",
                _rels({"rId1": f"../media/image{index}.jpg"}),
            )
            archive.writestr(f"xl/media/image{index}.jpg", image)
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{_MAIN}" xmlns:r="{_DOC_RELS}"><sheets>{"".join(sheets)}'
            "</sheets></workbook>",
        )
        archive.writestr("xl/_rels/workbook.xml.rels", _rels(workbook_rels))
    return buffer.getvalue()


def _preview(month, value="3158.88", source_url=SHEET_URL):
    return CubPreview(
        reference_month=datetime.date(2026, month - 1, 1),
        applicable_month=datetime.date(2026, month, 1),
        value=Decimal(value),
        monthly_variation=None,
        source_url=source_url,
    )


class TestCubSheetWorkbook:
    def test_extracts_images_from_latest_year_tab(self):
        content = _xlsx({"2025": b"old", "2026": b"new", "Notas": b"skip"})

        year, images = extract_cub_sheet_images(content)

        assert year == 2026
        assert images == [b"new"]

    def test_rejects_non_xlsx_content(self):
        with pytest.raises(CubFetchError, match="xlsx válido"):
            extract_cub_sheet_images(b"<html>login</html>")

    def test_rejects_workbook_without_year_tabs(self):
        with pytest.raises(CubFetchError, match="pestañas por año"):
            extract_cub_sheet_images(_xlsx({"Notas": b"img"}))

    def test_rejects_year_tab_without_image(self):
        with pytest.raises(CubFetchError, match="pestaña 2026"):
            extract_cub_sheet_images(_xlsx({"2026": None}))


class TestCubSheetTable:
    def test_reads_newest_row_from_noisy_ocr(self):
        result = parse_cub_sheet_table(OCR_TEXT, 2026)

        assert result.applicable_month == datetime.date(2026, 9, 1)
        assert result.reference_month == datetime.date(2026, 8, 1)
        assert result.value == Decimal("3158.88")
        assert result.monthly_variation == Decimal("0.24")
        assert result.source_url.startswith("https://docs.google.com/spreadsheets/")

    def test_january_row_has_no_variation(self):
        result = parse_cub_sheet_table("DEZ JAN 3.012,64 0,13%", 2027, SHEET_URL)

        assert result.applicable_month == datetime.date(2027, 1, 1)
        assert result.reference_month == datetime.date(2026, 12, 1)
        assert result.monthly_variation is None
        assert result.source_url == SHEET_URL

    def test_rejects_text_without_values(self):
        with pytest.raises(CubFetchError, match="formato reconocible"):
            parse_cub_sheet_table("Dados do mês de:", 2026)

    def test_rejects_missing_row_detected_by_month_labels(self):
        text = OCR_TEXT.replace("JUN JUL 3.121,62 0,829 362% 526%\n", "")

        with pytest.raises(CubFetchError, match="mes esperado"):
            parse_cub_sheet_table(text, 2026)

    def test_rejects_misread_values(self):
        text = OCR_TEXT.replace("3.151,24", "8.151,24")

        with pytest.raises(CubFetchError, match="inconsistentes"):
            parse_cub_sheet_table(text, 2026)


class TestCubSheetOcr:
    def test_runs_tesseract_on_image_bytes(self):
        completed = SimpleNamespace(stdout="AGO SET 3.158,88".encode())
        with patch("rates.services.cub_fetcher.subprocess.run", return_value=completed) as run:
            assert _ocr_image(b"img") == "AGO SET 3.158,88"

        assert run.call_args.args[0][0] == "tesseract"
        assert run.call_args.kwargs["input"] == b"img"

    def test_reports_missing_tesseract(self):
        with (
            patch("rates.services.cub_fetcher.subprocess.run", side_effect=FileNotFoundError),
            pytest.raises(CubFetchError, match="tesseract no está instalado"),
        ):
            _ocr_image(b"img")

    def test_wraps_tesseract_failures(self):
        with (
            patch(
                "rates.services.cub_fetcher.subprocess.run",
                side_effect=subprocess.TimeoutExpired("tesseract", 30),
            ),
            pytest.raises(CubFetchError, match="No se pudo leer"),
        ):
            _ocr_image(b"img")


class TestFetchCubSheet:
    def _response(self, content):
        return SimpleNamespace(content=content, raise_for_status=lambda: None)

    def test_downloads_and_reads_the_sheet(self):
        response = self._response(_xlsx({"2026": b"img"}))
        with (
            patch("rates.services.cub_fetcher.requests.get", return_value=response) as get,
            patch("rates.services.cub_fetcher._ocr_image", return_value=OCR_TEXT),
        ):
            result = fetch_cub_sheet(SHEET_URL)

        get.assert_called_once_with(SHEET_URL, timeout=30)
        assert result.value == Decimal("3158.88")
        assert result.source_url == SHEET_URL

    def test_tries_next_image_when_one_is_unreadable(self):
        content = _xlsx({"2026": b"img"})
        with (
            patch("rates.services.cub_fetcher.requests.get", return_value=self._response(content)),
            patch(
                "rates.services.cub_fetcher.extract_cub_sheet_images",
                return_value=(2026, [b"logo", b"table"]),
            ),
            patch("rates.services.cub_fetcher._ocr_image", side_effect=["logo", OCR_TEXT]),
        ):
            assert fetch_cub_sheet(SHEET_URL).value == Decimal("3158.88")

    def test_raises_last_error_when_no_image_is_readable(self):
        with (
            patch(
                "rates.services.cub_fetcher.requests.get",
                return_value=self._response(_xlsx({"2026": b"img"})),
            ),
            patch("rates.services.cub_fetcher._ocr_image", return_value="logo"),
            pytest.raises(CubFetchError, match="formato reconocible"),
        ):
            fetch_cub_sheet(SHEET_URL)

    def test_wraps_network_failures(self):
        with (
            patch(
                "rates.services.cub_fetcher.requests.get",
                side_effect=requests.RequestException("timeout"),
            ),
            pytest.raises(CubFetchError, match="planilla CUB"),
        ):
            fetch_cub_sheet(SHEET_URL)


class TestCubSourcePriority:
    TODAY = datetime.date(2026, 9, 1)

    def _history(self):
        return patch(
            "rates.services.cub_fetcher.parse_cub_history",
            return_value=[_preview(8, "3151.24", HISTORY_URL)],
        )

    def _fetch(self):
        with patch("rates.services.cub_fetcher._fetch_html", return_value="<html/>"):
            return fetch_cub_history(HISTORY_URL, CURRENT_URL, SHEET_URL, today=self.TODAY)

    def test_up_to_date_sheet_skips_the_monthly_card(self):
        with (
            self._history(),
            patch("rates.services.cub_fetcher.fetch_cub_sheet", return_value=_preview(9)),
            patch("rates.services.cub_fetcher.parse_current_cub") as current,
        ):
            results = self._fetch()

        current.assert_not_called()
        assert [item.source_url for item in results] == [SHEET_URL, HISTORY_URL]

    def test_falls_back_to_monthly_card_when_sheet_fails(self):
        with (
            self._history(),
            patch(
                "rates.services.cub_fetcher.fetch_cub_sheet",
                side_effect=CubFetchError("sin tesseract"),
            ),
            patch(
                "rates.services.cub_fetcher.parse_current_cub",
                return_value=_preview(9, source_url=CURRENT_URL),
            ),
        ):
            results = self._fetch()

        assert results[0].applicable_month == datetime.date(2026, 9, 1)
        assert results[0].source_url == CURRENT_URL

    def test_lagging_sheet_also_checks_monthly_card(self):
        with (
            self._history(),
            patch("rates.services.cub_fetcher.fetch_cub_sheet", return_value=_preview(8)),
            patch(
                "rates.services.cub_fetcher.parse_current_cub",
                return_value=_preview(9, source_url=CURRENT_URL),
            ),
        ):
            results = self._fetch()

        assert [(item.applicable_month.month, item.source_url) for item in results] == [
            (9, CURRENT_URL),
            (8, SHEET_URL),
        ]

    def test_sheet_wins_when_both_sources_report_the_same_month(self):
        with (
            self._history(),
            patch("rates.services.cub_fetcher.fetch_cub_sheet", return_value=_preview(8)),
            patch(
                "rates.services.cub_fetcher.parse_current_cub",
                return_value=_preview(8, source_url=CURRENT_URL),
            ),
        ):
            results = self._fetch()

        assert [item.source_url for item in results] == [SHEET_URL]

    def test_lagging_sheet_survives_monthly_card_failure(self):
        with (
            self._history(),
            patch("rates.services.cub_fetcher.fetch_cub_sheet", return_value=_preview(8)),
            patch(
                "rates.services.cub_fetcher.parse_current_cub",
                side_effect=CubFetchError("sin bloque"),
            ),
        ):
            results = self._fetch()

        assert [item.source_url for item in results] == [SHEET_URL]

    def test_raises_when_both_sources_fail(self):
        with (
            self._history(),
            patch("rates.services.cub_fetcher.fetch_cub_sheet", side_effect=CubFetchError("a")),
            patch(
                "rates.services.cub_fetcher.parse_current_cub",
                side_effect=CubFetchError("sin bloque"),
            ),
            pytest.raises(CubFetchError, match="sin bloque"),
        ):
            self._fetch()

    def test_sheet_error_is_raised_without_fallback_url(self):
        with (
            self._history(),
            patch("rates.services.cub_fetcher._fetch_html", return_value="<html/>"),
            patch("rates.services.cub_fetcher.fetch_cub_sheet", side_effect=CubFetchError("a")),
            pytest.raises(CubFetchError, match="a"),
        ):
            fetch_cub_history(HISTORY_URL, None, SHEET_URL, today=self.TODAY)
