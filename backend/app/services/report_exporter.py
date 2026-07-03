import html
import io
import re
import zipfile
from datetime import datetime
from typing import Any

from app.models import GeneratedReport


def export_report_xlsx(report: GeneratedReport) -> bytes:
    shared_strings: list[str] = []
    shared_index: dict[str, int] = {}

    def shared(value: Any) -> int:
        text = "" if value is None else str(value)
        if text not in shared_index:
            shared_index[text] = len(shared_strings)
            shared_strings.append(text)
        return shared_index[text]

    rows = [report.columns] + [[row.get(column, "") for column in report.columns] for row in report.rows]
    sheet_rows = []
    for row_number, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            ref = f"{_excel_column(column_index)}{row_number}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="s"><v>{shared(value)}</v></c>')
        sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')

    shared_xml = "".join(
        f"<si><t>{html.escape(value)}</t></si>"
        for value in shared_strings
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/styles.xml", _styles_xml())
        archive.writestr(
            "xl/sharedStrings.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">{shared_xml}</sst>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>',
        )
    return buffer.getvalue()


def export_report_pdf(report: GeneratedReport) -> bytes:
    pages = _report_pdf_pages(report)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]

    page_refs: list[str] = []
    for page_number, page_rows in enumerate(pages, start=1):
        page_object_number = len(objects) + 1
        content_object_number = page_object_number + 1
        page_refs.append(f"{page_object_number} 0 R")
        stream = _pdf_report_page_stream(report, page_rows, page_number, len(pages))
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_object_number} 0 R >>".encode("ascii")
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        )

    objects[1] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>".encode("ascii")
    return _build_pdf(objects)


def export_filename(report: GeneratedReport, extension: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", report.title.lower()).strip("-") or "report"
    return f"{slug[:48]}.{extension}"


def _report_pdf_pages(report: GeneratedReport) -> list[list[dict[str, Any]]]:
    if not report.rows:
        return [[]]
    first_page_rows = 12
    later_page_rows = 17
    pages = [report.rows[:first_page_rows]]
    remaining = report.rows[first_page_rows:]
    while remaining:
        pages.append(remaining[:later_page_rows])
        remaining = remaining[later_page_rows:]
    return pages


def _pdf_report_page_stream(
    report: GeneratedReport,
    rows: list[dict[str, Any]],
    page_number: int,
    page_count: int,
) -> bytes:
    canvas = _PdfCanvas()
    width = 842
    height = 595
    margin = 36
    table_width = width - (margin * 2)

    canvas.rect(0, 0, width, height, fill=(0.96, 0.98, 1.0), stroke=None)
    canvas.rect(margin, 515, table_width, 44, fill=(0.13, 0.27, 0.55), stroke=None)
    canvas.text(margin + 16, 540, _fit_text(report.title, 70), size=18, bold=True, color=(1, 1, 1))
    canvas.text(margin + 16, 523, "DEVITA AI Reporting", size=9, bold=True, color=(0.84, 0.9, 1))
    canvas.text(width - 132, 523, f"Page {page_number} of {page_count}", size=9, color=(0.84, 0.9, 1))

    if page_number == 1:
        canvas.rect(margin, 426, table_width, 76, fill=(1, 1, 1), stroke=(0.78, 0.84, 0.92))
        canvas.text(margin + 14, 482, "Report Question", size=9, bold=True, color=(0.34, 0.41, 0.52))
        canvas.text(margin + 14, 466, _fit_text(report.question, 112), size=10, color=(0.08, 0.13, 0.22))
        if report.explanation:
            canvas.text(margin + 14, 448, _fit_text(report.explanation, 118), size=9, color=(0.34, 0.41, 0.52))

        box_y = 376
        _summary_box(canvas, margin, box_y, 178, "Rows Returned", str(report.row_count))
        _summary_box(canvas, margin + 194, box_y, 178, "Columns", str(len(report.columns)))
        _summary_box(canvas, margin + 388, box_y, 178, "Generated", datetime.now().strftime("%d %b %Y"))
        _summary_box(canvas, margin + 582, box_y, 188, "Status", "Saved Report")
        table_top = 338
    else:
        table_top = 492

    canvas.text(margin, table_top + 17, "Report Data", size=12, bold=True, color=(0.08, 0.13, 0.22))
    _draw_report_table(canvas, report, rows, margin, table_top, table_width)

    return canvas.render()


def _summary_box(canvas: "_PdfCanvas", x: float, y: float, width: float, label: str, value: str) -> None:
    canvas.rect(x, y, width, 38, fill=(1, 1, 1), stroke=(0.78, 0.84, 0.92))
    canvas.text(x + 10, y + 23, label, size=8, bold=True, color=(0.34, 0.41, 0.52))
    canvas.text(x + 10, y + 9, _fit_text(value, 24), size=11, bold=True, color=(0.08, 0.13, 0.22))


def _draw_report_table(
    canvas: "_PdfCanvas",
    report: GeneratedReport,
    rows: list[dict[str, Any]],
    x: float,
    y: float,
    width: float,
) -> None:
    if not report.columns:
        canvas.rect(x, y - 34, width, 34, fill=(1, 1, 1), stroke=(0.78, 0.84, 0.92))
        canvas.text(x + 12, y - 21, "No rows returned.", size=10, color=(0.34, 0.41, 0.52))
        return

    columns = report.columns[:8]
    column_width = width / max(len(columns), 1)
    header_height = 24
    row_height = 24
    bottom = y - header_height - (len(rows) * row_height)

    canvas.rect(x, bottom, width, header_height + (len(rows) * row_height), fill=(1, 1, 1), stroke=(0.78, 0.84, 0.92))
    canvas.rect(x, y - header_height, width, header_height, fill=(0.9, 0.94, 1), stroke=(0.78, 0.84, 0.92))
    for index, column in enumerate(columns):
        cell_x = x + (index * column_width)
        if index:
            canvas.line(cell_x, bottom, cell_x, y, color=(0.78, 0.84, 0.92))
        canvas.text(cell_x + 7, y - 16, _fit_text(_humanize_column(column), int(column_width / 5.2)), size=8, bold=True, color=(0.12, 0.22, 0.38))

    for row_index, row in enumerate(rows):
        row_top = y - header_height - (row_index * row_height)
        row_bottom = row_top - row_height
        if row_index % 2 == 1:
            canvas.rect(x, row_bottom, width, row_height, fill=(0.98, 0.99, 1), stroke=None)
        canvas.line(x, row_bottom, x + width, row_bottom, color=(0.86, 0.9, 0.96))
        for column_index, column in enumerate(columns):
            cell_x = x + (column_index * column_width)
            value = _cell_text(row.get(column, ""))
            canvas.text(cell_x + 7, row_bottom + 8, _fit_text(value, int(column_width / 4.8)), size=8, color=(0.12, 0.16, 0.24))

    if len(report.columns) > len(columns):
        canvas.text(x, bottom - 14, f"{len(report.columns) - len(columns)} additional columns are available in the Excel export.", size=8, color=(0.34, 0.41, 0.52))


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _humanize_column(column: str) -> str:
    return column.replace("_", " ").title().replace(" Id", " ID").replace(" Cr", " CR")


def _fit_text(value: Any, max_length: int) -> str:
    text = _cell_text(value)
    if len(text) <= max_length:
        return text
    return text[: max(1, max_length - 1)].rstrip() + "."


def _clip(value: Any, max_length: int = 28) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= max_length else text[: max_length - 1] + "."


def _wrap_lines(lines: list[str], width: int) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        text = str(line)
        if not text:
            wrapped.append("")
            continue
        while len(text) > width:
            wrapped.append(text[:width])
            text = text[width:]
        wrapped.append(text)
    return wrapped


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _PdfCanvas:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        fill: tuple[float, float, float] | None = None,
        stroke: tuple[float, float, float] | None = None,
    ) -> None:
        self.commands.append("q")
        if fill:
            self.commands.append(f"{fill[0]} {fill[1]} {fill[2]} rg")
        if stroke:
            self.commands.append(f"{stroke[0]} {stroke[1]} {stroke[2]} RG")
        self.commands.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re")
        self.commands.append("B" if fill and stroke else "f" if fill else "S")
        self.commands.append("Q")

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        color: tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        self.commands.append("q")
        self.commands.append(f"{color[0]} {color[1]} {color[2]} RG")
        self.commands.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")
        self.commands.append("Q")

    def text(
        self,
        x: float,
        y: float,
        value: str,
        *,
        size: int = 10,
        bold: bool = False,
        color: tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        font = "F2" if bold else "F1"
        self.commands.append("BT")
        self.commands.append(f"{color[0]} {color[1]} {color[2]} rg")
        self.commands.append(f"/{font} {size} Tf")
        self.commands.append(f"{x:.2f} {y:.2f} Td")
        self.commands.append(f"({_pdf_escape(value)}) Tj")
        self.commands.append("ET")

    def render(self) -> bytes:
        return "\n".join(self.commands).encode("latin-1", errors="replace")


def _build_pdf(objects: list[bytes]) -> bytes:
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n".encode("ascii"))
        output.write(obj)
        output.write(b"\nendobj\n")
    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return output.getvalue()


def _excel_column(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""


def _root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _workbook_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""


def _workbook_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>"""


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>"""
