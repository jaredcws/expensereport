from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import hashlib
import re
import shutil

import fitz
from PIL import Image, ImageEnhance, ImageOps
from rapidocr_onnxruntime import RapidOCR


@dataclass(slots=True)
class ParsedReceipt:
    stored_path: str
    date: str = ""
    receipt_number: str = ""
    description: str = ""
    reimbursable_expense: str = ""
    amount: str = ""
    receipt_enclosed: bool = True
    raw_text: str = ""


class ReceiptService:
    def __init__(self, receipts_dir: Path) -> None:
        self.receipts_dir = receipts_dir
        self._ocr_engine: RapidOCR | None = None

    def attach_receipt(self, source_path: Path) -> ParsedReceipt:
        if not source_path.exists():
            raise FileNotFoundError(f"Receipt not found: {source_path}")

        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        stored_path = self._copy_receipt(source_path)

        try:
            raw_text = self._extract_text(stored_path)
        except Exception:
            raw_text = ""

        merchant = self._extract_merchant(raw_text)
        email_fields = self._extract_email_header_fields(raw_text)
        description = email_fields.get("description") or self._extract_description(raw_text, merchant, source_path)
        reimbursable_expense = self._suggest_expense_category(raw_text, description, merchant)

        return ParsedReceipt(
            stored_path=str(stored_path),
            date=email_fields.get("date") or self._extract_date(raw_text),
            receipt_number=self._generate_receipt_number(stored_path),
            description=description,
            reimbursable_expense=reimbursable_expense,
            amount=email_fields.get("amount") or self._extract_total(raw_text),
            raw_text=raw_text,
        )

    def _copy_receipt(self, source_path: Path) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.receipts_dir / f"{source_path.stem}_{timestamp}{source_path.suffix.lower()}"
        counter = 1
        while target.exists():
            target = self.receipts_dir / f"{source_path.stem}_{timestamp}_{counter}{source_path.suffix.lower()}"
            counter += 1
        shutil.copy2(source_path, target)
        return target

    def _extract_text(self, source_path: Path) -> str:
        if source_path.suffix.lower() == ".pdf":
            return self._extract_pdf_text(source_path)
        return self._extract_image_text(source_path)

    def _extract_pdf_text(self, source_path: Path) -> str:
        pages: list[str] = []
        with fitz.open(source_path) as document:
            for page in document:
                page_text = page.get_text("text").strip()
                if len(page_text.split()) >= 3:
                    pages.append(page_text)
                    continue
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pages.append(self._run_ocr(pixmap.tobytes("png")))
        return "\n".join(part for part in pages if part.strip())

    def _extract_image_text(self, source_path: Path) -> str:
        return self._run_ocr(source_path)

    def _run_ocr(self, image_source: Path | bytes) -> str:
        attempts: list[Path | bytes] = [image_source]
        preprocessed = self._preprocess_image(image_source)
        if preprocessed:
            attempts.extend(preprocessed)

        lines: list[str] = []
        seen: set[str] = set()
        for candidate in attempts:
            result = self._get_ocr_engine()(candidate)
            entries = result[0] if result else []
            for entry in entries:
                if len(entry) < 2:
                    continue
                text = self._normalize_ocr_line(str(entry[1]))
                if not text:
                    continue
                marker = text.lower()
                if marker in seen:
                    continue
                seen.add(marker)
                lines.append(text)
        return "\n".join(lines)

    def _preprocess_image(self, image_source: Path | bytes) -> list[bytes]:
        try:
            if isinstance(image_source, bytes):
                base_image = Image.open(BytesIO(image_source))
            else:
                base_image = Image.open(image_source)
        except Exception:
            return []

        with base_image:
            grayscale = ImageOps.exif_transpose(base_image).convert("L")
            grayscale = ImageOps.autocontrast(grayscale)
            enlarged = grayscale.resize(
                (max(1, grayscale.width * 2), max(1, grayscale.height * 2)),
                Image.Resampling.LANCZOS,
            )
            boosted = ImageEnhance.Contrast(enlarged).enhance(2.2)
            thresholded = boosted.point(lambda value: 255 if value > 165 else 0)
            return [self._image_to_png_bytes(boosted), self._image_to_png_bytes(thresholded)]

    def _image_to_png_bytes(self, image: Image.Image) -> bytes:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _get_ocr_engine(self) -> RapidOCR:
        if self._ocr_engine is None:
            self._ocr_engine = RapidOCR()
        return self._ocr_engine

    def _extract_date(self, raw_text: str) -> str:
        dated_candidates: list[tuple[int, datetime]] = []
        for line_number, line in enumerate(raw_text.splitlines()):
            line_score = self._score_date_line(line)
            for candidate in self._find_date_candidates(line):
                parsed = self._parse_date(candidate)
                if parsed:
                    dated_candidates.append((line_score - line_number, parsed))

        if dated_candidates:
            dated_candidates.sort(key=lambda item: item[0], reverse=True)
            return dated_candidates[0][1].strftime("%Y-%m-%d")
        return ""

    def _extract_email_header_fields(self, raw_text: str) -> dict[str, str]:
        top_lines = [
            self._normalize_ocr_line(line)
            for line in raw_text.splitlines()
            if self._normalize_ocr_line(line)
        ][:30]
        fields = self._extract_email_body_triplet_fields(top_lines)
        labels = ("date", "description", "amount")

        for index, line in enumerate(top_lines):
            lowered = line.lower().strip()
            for label in labels:
                if label in fields:
                    continue

                inline_match = re.match(rf"^{label}\s*[:\-]\s*(.+)$", line, flags=re.IGNORECASE)
                if inline_match:
                    value = inline_match.group(1).strip()
                elif lowered == label:
                    value = self._next_email_value_line(top_lines, index)
                elif lowered.startswith(f"{label} "):
                    value = line[len(label):].strip(" :-")
                else:
                    continue

                normalized = self._normalize_email_field(label, value)
                if normalized:
                    fields[label] = normalized
        return fields

    def _extract_email_body_triplet_fields(self, lines: list[str]) -> dict[str, str]:
        filtered_lines = [line for line in lines if not self._is_email_metadata_line(line)]
        max_start = min(len(filtered_lines) - 2, 9)
        for start in range(max(0, max_start + 1)):
            date_value = self._normalize_email_field("date", filtered_lines[start])
            description_value = self._normalize_email_field("description", filtered_lines[start + 1])
            amount_value = self._normalize_email_field("amount", filtered_lines[start + 2])
            if not date_value or not amount_value:
                continue
            if not description_value or not re.search(r"[A-Za-z]", description_value):
                continue
            return {
                "date": date_value,
                "description": description_value,
                "amount": amount_value,
            }
        return {}

    def _is_email_metadata_line(self, line: str) -> bool:
        lowered = line.lower().strip()
        if lowered.startswith(("from:", "to:", "subject:", "date:", "sent:", "cc:", "bcc:")):
            return True
        if lowered in {"from", "to", "subject", "date", "sent", "cc", "bcc"}:
            return True
        if lowered.startswith("http://") or lowered.startswith("https://"):
            return True
        return False

    def _next_email_value_line(self, lines: list[str], index: int) -> str:
        for next_line in lines[index + 1 :]:
            lowered = next_line.lower().strip()
            if lowered in {"date", "description", "amount"}:
                return ""
            return next_line
        return ""

    def _normalize_email_field(self, label: str, value: str) -> str:
        if not value:
            return ""
        if label == "date":
            return self._extract_date(value)
        if label == "amount":
            return self._extract_total(value)
        if label == "description":
            return self._strip_amounts_from_line(value)[:120]
        return ""

    def _find_date_candidates(self, raw_text: str) -> list[str]:
        patterns = [
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
            r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b",
            r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}\b",
            r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*,?\s+\d{2,4}\b",
        ]
        candidates: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, raw_text, flags=re.IGNORECASE):
                candidates.append(match.group(0))
        return candidates

    def _score_date_line(self, line: str) -> int:
        lowered = line.lower()
        score = 0
        if "date" in lowered:
            score += 10
        if any(token in lowered for token in ("sale", "transaction", "invoice", "issued", "purchased")):
            score += 6
        if any(token in lowered for token in ("due", "delivery", "ship", "arrival")):
            score -= 3
        return score

    def _parse_date(self, candidate: str) -> datetime | None:
        normalized = " ".join(candidate.replace(",", " ").replace("O", "0").replace("o", "0").split())
        formats = [
            "%m/%d/%Y",
            "%m/%d/%y",
            "%m-%d-%Y",
            "%m-%d-%y",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%m.%d.%Y",
            "%m.%d.%y",
            "%B %d %Y",
            "%b %d %Y",
            "%d %B %Y",
            "%d %b %Y",
        ]
        for date_format in formats:
            try:
                parsed = datetime.strptime(normalized, date_format)
            except ValueError:
                continue
            if parsed.year < 100:
                parsed = parsed.replace(year=parsed.year + 2000)
            if parsed.year < 2000 or parsed.year > datetime.now().year + 1:
                continue
            return parsed
        return None

    def _generate_receipt_number(self, stored_path: Path) -> str:
        digest = hashlib.sha1(str(stored_path).encode("utf-8")).hexdigest()[:8].upper()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"RCPT-{timestamp}-{digest}"

    def _extract_total(self, raw_text: str) -> str:
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        preferred_labels = ("grand total", "amount due", "balance due", "order total", "total due", "total")
        excluded_labels = ("subtotal", "sub total", "tax", "tip", "change", "discount", "cash", "visa", "mastercard", "amex")

        for line in lines:
            lowered = line.lower()
            if any(label in lowered for label in preferred_labels) and not any(skip in lowered for skip in excluded_labels):
                amounts = self._extract_amount_candidates(line)
                if amounts:
                    return f"{amounts[-1]:.2f}"

        all_amounts: list[Decimal] = []
        for line in lines:
            all_amounts.extend(self._extract_amount_candidates(line))
        if all_amounts:
            return f"{max(all_amounts):.2f}"
        return ""

    def _extract_amount_candidates(self, line: str) -> list[Decimal]:
        matches = re.findall(
            r"(?<!\d)(?:USD\s*)?\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})|[0-9]+\.[0-9]{2})(?!\d)",
            line,
            flags=re.IGNORECASE,
        )
        amounts: list[Decimal] = []
        for match in matches:
            normalized = match.replace(",", "")
            try:
                amounts.append(Decimal(normalized))
            except (InvalidOperation, ValueError):
                continue
        return amounts

    def _extract_merchant(self, raw_text: str) -> str:
        for line in raw_text.splitlines():
            cleaned = " ".join(line.split())
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if any(
                token in lowered
                for token in ("receipt", "invoice", "order", "transaction", "total", "date", "thank", "visa", "mastercard", "amex", "http", "www")
            ):
                continue
            if sum(char.isalpha() for char in cleaned) < 4:
                continue
            return cleaned[:60]
        return ""

    def _extract_description(self, raw_text: str, merchant: str, source_path: Path) -> str:
        candidate_lines = self._extract_item_lines(raw_text, merchant)
        if candidate_lines:
            return "; ".join(candidate_lines[:3])[:120]
        if merchant:
            return merchant
        return source_path.stem.replace("_", " ").replace("-", " ").strip()[:120]

    def _extract_item_lines(self, raw_text: str, merchant: str) -> list[str]:
        cleaned_lines = [self._normalize_ocr_line(line) for line in raw_text.splitlines()]
        cleaned_lines = [line for line in cleaned_lines if line]
        if not cleaned_lines:
            return []

        merchant_key = merchant.lower().strip()
        stop_index = len(cleaned_lines)
        for index, line in enumerate(cleaned_lines):
            lowered = line.lower()
            if any(token in lowered for token in ("subtotal", "sub total", "tax", "tip", "grand total", "total", "amount due", "balance due")):
                stop_index = index
                break

        candidates: list[tuple[int, str]] = []
        for index, line in enumerate(cleaned_lines[:stop_index]):
            lowered = line.lower()
            if merchant_key and lowered == merchant_key:
                continue
            if self._is_non_item_line(lowered, line):
                continue
            score = self._score_item_line(index, lowered, line, stop_index)
            normalized_line = self._strip_amounts_from_line(line)
            if normalized_line:
                candidates.append((score, normalized_line))

        candidates.sort(key=lambda item: item[0], reverse=True)
        selected: list[str] = []
        seen: set[str] = set()
        for _score, line in candidates:
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            selected.append(line)
            if len(selected) >= 3:
                break
        return selected

    def _is_non_item_line(self, lowered: str, original: str) -> bool:
        if any(
            token in lowered
            for token in (
                "receipt",
                "invoice",
                "transaction",
                "approval",
                "auth",
                "server",
                "table",
                "guest",
                "order",
                "cash",
                "change",
                "debit",
                "credit",
                "visa",
                "mastercard",
                "amex",
                "discover",
                "subtotal",
                "sub total",
                "total",
                "tax",
                "tip",
                "balance",
                "amount due",
                "date",
                "time",
                "phone",
                "tel",
                "store",
                "location",
                "thank",
                "visit",
                "www",
                "http",
                "approval",
                "change due",
            )
        ):
            return True
        if re.fullmatch(r"[A-Z0-9 .:/#-]+", original) and sum(char.isalpha() for char in original) < 4:
            return True
        if re.search(r"\d{3}[-.\s]\d{3}[-.\s]\d{4}", original):
            return True
        if re.search(r"\b(?:st|street|ave|avenue|rd|road|blvd|suite|ste|zip)\b", lowered):
            return True
        return False

    def _score_item_line(self, index: int, lowered: str, original: str, stop_index: int) -> int:
        score = 0
        if re.search(r"[A-Za-z]", original):
            score += 8
        if len(original) <= 45:
            score += 3
        if re.search(r"\d+\.\d{2}", original):
            score += 4
        if index > 1:
            score += 2
        score += max(0, stop_index - index)
        return score

    def _strip_amounts_from_line(self, line: str) -> str:
        stripped = re.sub(
            r"\s+(?:USD\s*)?\$?[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})\s*$",
            "",
            line,
            flags=re.IGNORECASE,
        )
        stripped = re.sub(r"\s{2,}", " ", stripped).strip(" -:")
        return stripped

    def _suggest_expense_category(self, raw_text: str, description: str, merchant: str) -> str:
        lowered = f"{raw_text}\n{description}\n{merchant}".lower()
        if any(token in lowered for token in ("coffee", "latte", "espresso", "cappuccino", "americano", "mocha", "starbucks", "dunkin", "peet")):
            return "Meals & Entertainment"
        if any(token in lowered for token in ("restaurant", "grill", "bistro", "cafe", "pizza", "bar", "diner", "lunch", "dinner", "breakfast", "sandwich")):
            return "Meals & Entertainment"
        if any(token in lowered for token in ("uber", "lyft", "taxi", "cab", "rideshare", "parking", "garage", "toll")):
            return "Transportation"
        if any(token in lowered for token in ("hotel", "inn", "marriott", "hilton", "hyatt", "lodging", "room")):
            return "Travel"
        if any(token in lowered for token in ("delta", "united", "southwest", "airlines", "flight", "airport", "boarding")):
            return "Travel"
        if any(token in lowered for token in ("office depot", "staples", "office max", "supplies", "paper", "printer", "ink")):
            return "Office Supplies"
        return ""

    def _normalize_ocr_line(self, line: str) -> str:
        line = " ".join(line.split())
        line = line.replace("|", "I").strip()
        return line
