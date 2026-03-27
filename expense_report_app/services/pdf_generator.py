from __future__ import annotations

from pathlib import Path


class PdfGenerator:
    """Phase-1 placeholder for future ReportLab implementation."""

    def generate_report_pdf(self, report_data: dict, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        raise NotImplementedError("PDF generation is planned for Phase 2.")
