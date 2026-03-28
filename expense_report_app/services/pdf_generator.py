from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from xml.sax.saxutils import escape

import fitz
from PIL import Image, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from expense_report_app.utils.formatters import as_currency

PAGE_WIDTH, PAGE_HEIGHT = LETTER
REPORT_LEFT_MARGIN = 0.55 * inch
REPORT_RIGHT_MARGIN = 0.55 * inch
REPORT_TOP_MARGIN = 0.6 * inch
REPORT_BOTTOM_MARGIN = 0.6 * inch
REPORT_CONTENT_WIDTH = PAGE_WIDTH - REPORT_LEFT_MARGIN - REPORT_RIGHT_MARGIN


class PdfGenerator:
    def generate_report_pdf(
        self,
        report_data: dict,
        output_dir: Path,
        settings: dict[str, str] | None = None,
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / self._build_filename(report_data)
        if output_path.exists():
            output_path.unlink()

        with NamedTemporaryFile(delete=False, suffix=".pdf") as temporary_file:
            temp_path = Path(temporary_file.name)

        try:
            self._build_main_report_pdf(report_data, temp_path, settings or {})
            self._compose_final_pdf(temp_path, output_path, report_data.get("misc_items", []))
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return output_path

    def _build_main_report_pdf(self, report_data: dict, output_path: Path, settings: dict[str, str]) -> None:
        styles = self._build_styles()
        document = SimpleDocTemplate(
            str(output_path),
            pagesize=LETTER,
            leftMargin=REPORT_LEFT_MARGIN,
            rightMargin=REPORT_RIGHT_MARGIN,
            topMargin=REPORT_TOP_MARGIN,
            bottomMargin=REPORT_BOTTOM_MARGIN,
        )

        story = [
            Paragraph("Expense Report", styles["title"]),
            Spacer(1, 0.12 * inch),
            self._build_summary_table(report_data, styles),
            Spacer(1, 0.2 * inch),
            Paragraph("Mileage Entries", styles["section"]),
            self._build_mileage_table(report_data.get("mileage_items", []), styles),
            Spacer(1, 0.2 * inch),
            Paragraph("Miscellaneous Entries", styles["section"]),
            self._build_misc_table(report_data.get("misc_items", []), styles),
            Spacer(1, 0.2 * inch),
            Paragraph("Totals", styles["section"]),
            self._build_totals_table(report_data, styles),
        ]

        signature_table = self._build_signature_table(report_data, settings, styles)
        if signature_table is not None:
            story.extend([Spacer(1, 0.25 * inch), Paragraph("Signatures", styles["section"]), signature_table])

        document.build(story)

    def _compose_final_pdf(self, main_report_path: Path, output_path: Path, misc_items: list[dict]) -> None:
        final_document = fitz.open()
        main_document = fitz.open(main_report_path)
        try:
            final_document.insert_pdf(main_document)
            for receipt_number, receipt_path in self._ordered_receipt_attachments(misc_items):
                if receipt_path.suffix.lower() == ".pdf":
                    self._append_pdf_receipt(final_document, receipt_path, receipt_number)
                else:
                    self._append_image_receipt(final_document, receipt_path, receipt_number)
            final_document.save(str(output_path), garbage=4, deflate=True)
        finally:
            main_document.close()
            final_document.close()

    def _ordered_receipt_attachments(self, misc_items: list[dict]) -> list[tuple[str, Path]]:
        ordered: list[tuple[int, int, str, Path]] = []
        for index, item in enumerate(misc_items, start=1):
            receipt_path_value = str(item.get("receipt_file", "")).strip()
            if not receipt_path_value:
                continue
            receipt_path = Path(receipt_path_value)
            if not receipt_path.exists():
                continue
            receipt_number = str(item.get("receipt_number", "")).strip() or str(index)
            sort_key = int(receipt_number) if receipt_number.isdigit() else index
            ordered.append((sort_key, index, receipt_number, receipt_path))
        ordered.sort(key=lambda value: (value[0], value[1]))
        return [(receipt_number, receipt_path) for _, _, receipt_number, receipt_path in ordered]

    def _append_pdf_receipt(self, final_document: fitz.Document, receipt_path: Path, receipt_number: str) -> None:
        source_document = fitz.open(receipt_path)
        try:
            start_page = final_document.page_count
            final_document.insert_pdf(source_document)
            for page_number in range(start_page, final_document.page_count):
                self._stamp_receipt_label(final_document.load_page(page_number), receipt_number)
        finally:
            source_document.close()

    def _append_image_receipt(self, final_document: fitz.Document, receipt_path: Path, receipt_number: str) -> None:
        page = final_document.new_page(width=LETTER[0], height=LETTER[1])
        self._stamp_receipt_label(page, receipt_number)

        with Image.open(receipt_path) as source_image:
            image = ImageOps.exif_transpose(source_image)
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")

            buffer = BytesIO()
            image.save(buffer, format="PNG")
            image_width, image_height = image.size

        available_left = 36
        available_top = 56
        available_width = LETTER[0] - 72
        available_height = LETTER[1] - 92
        scale = min(
            available_width / max(image_width, 1),
            available_height / max(image_height, 1),
        )
        render_width = image_width * scale
        render_height = image_height * scale
        x_offset = available_left + max(0, (available_width - render_width) / 2)
        y_offset = available_top + max(0, (available_height - render_height) / 2)
        image_rect = fitz.Rect(x_offset, y_offset, x_offset + render_width, y_offset + render_height)
        page.insert_image(image_rect, stream=buffer.getvalue(), keep_proportion=True)

    def _stamp_receipt_label(self, page: fitz.Page, receipt_number: str) -> None:
        label_rect = fitz.Rect(18, 14, 125, 36)
        page.draw_rect(
            label_rect,
            color=(0.75, 0.8, 0.87),
            fill=(1, 1, 1),
            width=0.8,
            overlay=True,
        )
        page.insert_text(
            fitz.Point(24, 29),
            f"Receipt #{receipt_number}",
            fontsize=12,
            fontname="helv",
            color=(0.1, 0.18, 0.27),
            overlay=True,
        )

    def _build_styles(self) -> dict[str, ParagraphStyle]:
        base_styles = getSampleStyleSheet()
        return {
            "title": ParagraphStyle(
                "ExpenseTitle",
                parent=base_styles["Heading1"],
                fontName="Helvetica-Bold",
                fontSize=18,
                leading=22,
                textColor=colors.HexColor("#1d2d44"),
                spaceAfter=0,
            ),
            "section": ParagraphStyle(
                "ExpenseSection",
                parent=base_styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=14,
                textColor=colors.HexColor("#274c77"),
                spaceAfter=6,
                spaceBefore=0,
            ),
            "body": ParagraphStyle(
                "ExpenseBody",
                parent=base_styles["BodyText"],
                fontName="Helvetica",
                fontSize=8,
                leading=10,
                alignment=TA_LEFT,
            ),
            "small": ParagraphStyle(
                "ExpenseSmall",
                parent=base_styles["BodyText"],
                fontName="Helvetica",
                fontSize=7,
                leading=9,
                textColor=colors.HexColor("#4a5568"),
            ),
            "signature_name": ParagraphStyle(
                "ExpenseSignatureName",
                parent=base_styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=9,
                leading=11,
                alignment=TA_LEFT,
                textColor=colors.HexColor("#1d2d44"),
            ),
            "table_header": ParagraphStyle(
                "ExpenseTableHeader",
                parent=base_styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=9,
                alignment=TA_LEFT,
                textColor=colors.HexColor("#102a43"),
            ),
            "table_header_center": ParagraphStyle(
                "ExpenseTableHeaderCenter",
                parent=base_styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=9,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#102a43"),
            ),
            "table_header_right": ParagraphStyle(
                "ExpenseTableHeaderRight",
                parent=base_styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=9,
                alignment=TA_RIGHT,
                textColor=colors.HexColor("#102a43"),
            ),
            "table_body": ParagraphStyle(
                "ExpenseTableBody",
                parent=base_styles["BodyText"],
                fontName="Helvetica",
                fontSize=7.6,
                leading=9,
                alignment=TA_LEFT,
            ),
            "table_body_center": ParagraphStyle(
                "ExpenseTableBodyCenter",
                parent=base_styles["BodyText"],
                fontName="Helvetica",
                fontSize=7.6,
                leading=9,
                alignment=TA_CENTER,
            ),
            "table_body_right": ParagraphStyle(
                "ExpenseTableBodyRight",
                parent=base_styles["BodyText"],
                fontName="Helvetica",
                fontSize=7.6,
                leading=9,
                alignment=TA_RIGHT,
            ),
        }

    def _build_summary_table(self, report_data: dict, styles: dict[str, ParagraphStyle]) -> Table:
        generated_on = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        rows = [
            ["Employee", self._text(report_data.get("employee_name", ""), styles["body"]), "Generated", self._text(generated_on, styles["body"])],
            ["Date From", self._text(report_data.get("date_from", ""), styles["body"]), "Date To", self._text(report_data.get("date_to", ""), styles["body"])],
            ["Mileage Rate", self._text(as_currency(float(report_data.get("mileage_rate", 0))), styles["body"]), "Draft ID", self._text(str(report_data.get("id", "")), styles["body"])],
        ]
        table = Table(rows, colWidths=[1.15 * inch, 2.35 * inch, 1.15 * inch, 2.35 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9e2ec")),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def _build_mileage_table(self, items: list[dict], styles: dict[str, ParagraphStyle]) -> Table:
        rows = [
            [
                self._header_text("Date", styles["table_header"]),
                self._header_text("Project", styles["table_header"]),
                self._header_text("From", styles["table_header"]),
                self._header_text("To", styles["table_header"]),
                self._header_text("Expense", styles["table_header"]),
                self._header_text("Round<br/>Trip", styles["table_header_center"]),
                self._header_text("Miles", styles["table_header_center"]),
                self._header_text("Reimb.", styles["table_header_right"]),
            ]
        ]

        if not items:
            rows.append([self._table_text("No mileage entries", styles["table_body"]), "", "", "", "", "", "", ""])
        else:
            for item in items:
                rows.append(
                    [
                        self._table_text(item.get("date", ""), styles["table_body"]),
                        self._table_text(item.get("project_number", ""), styles["table_body"]),
                        self._table_text(item.get("start_location", ""), styles["table_body"]),
                        self._table_text(item.get("end_location", ""), styles["table_body"]),
                        self._table_text(item.get("reimbursable_expense", ""), styles["table_body"]),
                        self._table_text("Yes" if item.get("round_trip") else "No", styles["table_body_center"]),
                        self._table_text(str(item.get("number_of_miles", "")), styles["table_body_center"]),
                        self._table_text(as_currency(float(item.get("miles_reimbursement", 0) or 0)), styles["table_body_right"]),
                    ]
                )

        table = Table(
            rows,
            repeatRows=1,
            colWidths=self._fit_widths([0.78, 0.74, 1.32, 1.32, 1.56, 0.62, 0.51, 0.55]),
            hAlign="LEFT",
        )
        table.setStyle(self._table_style(compact=True))
        return table

    def _build_misc_table(self, items: list[dict], styles: dict[str, ParagraphStyle]) -> Table:
        rows = [[
            self._header_text("Receipt #", styles["table_header"]),
            self._header_text("Date", styles["table_header"]),
            self._header_text("Description", styles["table_header"]),
            self._header_text("Expense", styles["table_header"]),
            self._header_text("Enclosed", styles["table_header_center"]),
            self._header_text("Amount", styles["table_header_right"]),
        ]]

        if not items:
            rows.append([self._table_text("No miscellaneous entries", styles["table_body"]), "", "", "", "", ""])
        else:
            for index, item in enumerate(items, start=1):
                rows.append(
                    [
                        self._table_text(str(index), styles["table_body_center"]),
                        self._table_text(item.get("date", ""), styles["table_body"]),
                        self._table_text(item.get("description", ""), styles["table_body"]),
                        self._table_text(item.get("reimbursable_expense", ""), styles["table_body"]),
                        self._table_text("Yes" if item.get("receipt_enclosed") else "No", styles["table_body_center"]),
                        self._table_text(as_currency(float(item.get("amount", 0) or 0)), styles["table_body_right"]),
                    ]
                )

        table = Table(
            rows,
            repeatRows=1,
            colWidths=self._fit_widths([0.78, 0.86, 2.6, 1.6, 0.8, 0.76]),
            hAlign="LEFT",
        )
        table.setStyle(self._table_style())
        return table

    def _build_totals_table(self, report_data: dict, styles: dict[str, ParagraphStyle]) -> Table:
        rows = [
            [self._table_text("Mileage Subtotal", styles["table_header"]), self._table_text(as_currency(float(report_data.get("mileage_subtotal", 0) or 0)), styles["table_body_right"])],
            [self._table_text("Miscellaneous Subtotal", styles["table_header"]), self._table_text(as_currency(float(report_data.get("misc_subtotal", 0) or 0)), styles["table_body_right"])],
            [self._table_text("Total This Period", styles["table_header"]), self._table_text(as_currency(float(report_data.get("total_period", 0) or 0)), styles["table_body_right"])],
        ]
        table = Table(rows, colWidths=self._fit_widths([2.4, 1.15]), hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9e2ec")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (0, 2), (1, 2), "Helvetica-Bold"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def _build_signature_table(
        self,
        report_data: dict,
        settings: dict[str, str],
        styles: dict[str, ParagraphStyle],
    ) -> Table | None:
        employee_name = str(report_data.get("employee_name", "")).strip() or settings.get("default_employee_name", "").strip()
        partner_name = settings.get("partner_name", "").strip()
        employee_signature = self._signature_cell(
            settings.get("employee_signature_image_path", ""),
            employee_name,
            "Employee Signature",
            styles,
        )
        partner_signature = self._signature_cell(
            settings.get("partner_signature_image_path", "") or settings.get("approver_signature_image_path", ""),
            partner_name,
            "Partner Signature",
            styles,
        )
        if employee_signature is None and partner_signature is None:
            return None

        table = Table(
            [[employee_signature or "", partner_signature or ""]],
            colWidths=[REPORT_CONTENT_WIDTH / 2, REPORT_CONTENT_WIDTH / 2],
            hAlign="LEFT",
        )
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9e2ec")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return table

    def _signature_cell(
        self,
        path_value: str,
        signer_name: str,
        role_label: str,
        styles: dict[str, ParagraphStyle],
    ):
        image_path = Path(path_value).expanduser() if path_value else None
        has_image = bool(image_path and image_path.exists())
        has_name = bool(signer_name.strip())
        if not has_image and not has_name:
            return None

        parts = [Paragraph(role_label, styles["small"])]
        if has_name:
            parts.extend([Spacer(1, 0.04 * inch), Paragraph(escape(signer_name), styles["signature_name"])])
        else:
            parts.extend([Spacer(1, 0.04 * inch), Paragraph("Name not set.", styles["small"])])
        if image_path and image_path.exists():
            image = PdfImage(str(image_path))
            scale = min((2.8 * inch) / max(image.imageWidth, 1), (0.85 * inch) / max(image.imageHeight, 1), 1)
            image.drawWidth = image.imageWidth * scale
            image.drawHeight = image.imageHeight * scale
            parts.extend([Spacer(1, 0.07 * inch), image])
        else:
            parts.append(Spacer(1, 0.22 * inch))
            parts.append(Paragraph("No signature file configured.", styles["small"]))
        return parts

    def _table_style(self, compact: bool = False) -> TableStyle:
        horizontal_padding = 3.5 if compact else 4.5
        vertical_padding = 3.5 if compact else 4.5
        return TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#102a43")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9e2ec")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), horizontal_padding),
                ("RIGHTPADDING", (0, 0), (-1, -1), horizontal_padding),
                ("TOPPADDING", (0, 0), (-1, -1), vertical_padding),
                ("BOTTOMPADDING", (0, 0), (-1, -1), vertical_padding),
                ("BOTTOMPADDING", (0, 0), (-1, 0), vertical_padding + 0.5),
            ]
        )

    def _build_filename(self, report_data: dict) -> str:
        employee = self._slugify(str(report_data.get("employee_name", "")).strip()) or "expense-report"
        date_from = str(report_data.get("date_from", "")).strip() or datetime.now().strftime("%Y-%m-%d")
        date_to = str(report_data.get("date_to", "")).strip() or date_from
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_id = report_data.get("id")
        if report_id:
            return f"expense_report_{report_id}_{employee}_{date_from}_to_{date_to}_{timestamp}.pdf"
        return f"expense_report_{employee}_{date_from}_to_{date_to}_{timestamp}.pdf"

    def _slugify(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    def _text(self, value: str, style: ParagraphStyle) -> Paragraph:
        return Paragraph(escape(str(value or "")), style)

    def _header_text(self, value: str, style: ParagraphStyle) -> Paragraph:
        return Paragraph(value, style)

    def _table_text(self, value: str, style: ParagraphStyle) -> Paragraph:
        return Paragraph(escape(str(value or "")), style)

    def _fit_widths(self, widths_in_inches: list[float]) -> list[float]:
        total_points = sum(width * inch for width in widths_in_inches)
        if total_points <= 0:
            return [REPORT_CONTENT_WIDTH]
        scale = REPORT_CONTENT_WIDTH / total_points
        return [width * inch * scale for width in widths_in_inches]
