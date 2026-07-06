import io
import unittest
import zipfile

from app.models import GeneratedReport
from app.services.report_exporter import export_report_pdf, export_report_xlsx
from app.services.templates import find_template
from app.services.week_five_presentation import build_report_presentation


class WeekFivePresentationTests(unittest.TestCase):
    def test_week_five_request_matches_stable_template(self) -> None:
        template = find_template(
            "Generate the Week 5 report with totals grouped by project type and manufacturing type.",
            "project",
        )

        self.assertIsNotNone(template)
        self.assertEqual(template.title, "Week Five Report")
        self.assertIn("p.project_mfg_type", template.sql)

    def test_non_week_five_report_has_no_presentation(self) -> None:
        presentation = build_report_presentation(
            "Revision Report",
            "Show revisions",
            ["project_name"],
            [{"project_name": "Alpha"}],
        )

        self.assertEqual(presentation, {})

    def test_project_and_total_rows_receive_expected_colors(self) -> None:
        columns = ["project_type", "project_mfg_type", "total_tasks", "row_type"]
        rows = [
            {"project_type": "CAD", "project_mfg_type": "CAD_CAM", "total_tasks": 4},
            {"project_type": "BIM", "project_mfg_type": "BIM", "total_tasks": 5},
            {"project_type": "Grand Total", "row_type": "grand_total", "total_tasks": 9},
        ]

        presentation = build_report_presentation("Week 5 Report", "Week 5 totals", columns, rows)

        self.assertEqual(presentation["cell_styles"]["0"]["project_type"]["background"], "#00FFFF")
        self.assertEqual(presentation["cell_styles"]["1"]["project_type"]["background"], "#008000")
        self.assertEqual(presentation["row_styles"]["2"]["background"], "#28A745")
        self.assertEqual(presentation["header_style"]["background"], "#00CED1")

    def test_week_color_priority_is_production_then_approval_then_tasks(self) -> None:
        columns = [
            "project_name",
            "project_type_id",
            "week_1",
            "week_1_start",
            "week_1_end",
            "project_production_date",
            "out_for_approval_date",
        ]
        base = {
            "project_name": "Alpha",
            "project_type_id": 7,
            "week_1_start": "2026-06-01",
            "week_1_end": "2026-06-07",
        }
        rows = [
            {
                **base,
                "week_1": 3,
                "project_production_date": "2026-06-03",
                "out_for_approval_date": "2026-06-04",
            },
            {**base, "week_1": 3, "out_for_approval_date": "2026-06-04"},
            {**base, "week_1": 3},
            {**base, "week_1": 0},
        ]

        presentation = build_report_presentation("Dai Week 5 Report", "Weekly details", columns, rows)

        self.assertEqual(presentation["cell_styles"]["0"]["week_1"]["background"], "#FF00FF")
        self.assertEqual(presentation["cell_styles"]["1"]["week_1"]["background"], "#CED4DA")
        self.assertEqual(presentation["cell_styles"]["2"]["week_1"]["background"], "#FFFF00")
        self.assertEqual(presentation["cell_styles"]["3"]["week_1"]["background"], "#FFFFFF")

    def test_xlsx_and_pdf_exports_accept_week_five_presentation(self) -> None:
        columns = ["project_type", "project_mfg_type", "total_tasks"]
        rows = [{"project_type": "CAD", "project_mfg_type": "CAD_CAM", "total_tasks": 4}]
        presentation = build_report_presentation("Week 5 Report", "Week 5 totals", columns, rows)
        report = GeneratedReport(
            title="Week 5 Report",
            question="Week 5 totals",
            sql="SELECT 1",
            explanation="Weekly project totals.",
            columns=columns,
            rows=rows,
            row_count=1,
            presentation=presentation,
            report_variant="week_five",
        )

        workbook = export_report_xlsx(report)
        with zipfile.ZipFile(io.BytesIO(workbook)) as archive:
            styles = archive.read("xl/styles.xml").decode("utf-8")
            sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            strings = archive.read("xl/sharedStrings.xml").decode("utf-8")

        self.assertIn('rgb="FF00CED1"', styles)
        self.assertIn('s="1"', sheet)
        self.assertIn("Project in process", strings)
        self.assertTrue(export_report_pdf(report).startswith(b"%PDF-1.4"))


if __name__ == "__main__":
    unittest.main()
