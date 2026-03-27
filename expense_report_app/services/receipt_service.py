from __future__ import annotations

from pathlib import Path


class ReceiptService:
    """Phase-1 placeholder for receipt copy/parsing workflows."""

    def attach_receipt(self, source_path: Path, receipts_dir: Path) -> Path:
        receipts_dir.mkdir(parents=True, exist_ok=True)
        raise NotImplementedError("Receipt attachment file handling will be expanded in a later phase.")
