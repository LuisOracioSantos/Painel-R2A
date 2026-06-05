import re
import unicodedata
from pathlib import Path


class CommissionExtractionError(Exception):
    pass


class CommissionExtractor:
    DATE_PATTERN = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")
    DUE_DATE_PATTERN = re.compile(
        r"\bVenc(?:imento)?\.?\s*(?::|-)?\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})",
        re.IGNORECASE,
    )

    def extract(self, pdf_path, original_name=None):
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise CommissionExtractionError("Arquivo PDF de comissoes nao encontrado.")

        try:
            import pdfplumber
        except ImportError as exc:
            raise CommissionExtractionError("A biblioteca pdfplumber nao esta instalada.") from exc

        records = {}
        text_parts = []
        pages_count = 0

        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages_count = len(pdf.pages)
                for page in pdf.pages:
                    text_parts.append(page.extract_text(layout=True) or page.extract_text() or "")
                    for raw_table in page.extract_tables() or []:
                        self._collect_records_from_table(raw_table, records)
        except Exception as exc:
            raise CommissionExtractionError(f"Nao foi possivel ler o PDF de comissoes: {exc}") from exc

        full_text = "\n".join(text_parts)
        due_date = self._extract_due_date(full_text)
        for record in records.values():
            record["Vencimento"] = record.get("Vencimento") or due_date

        return {
            "filename": original_name or pdf_path.name,
            "pages": pages_count,
            "due_date": due_date,
            "records": records,
            "count": len(records),
        }

    def apply_to_extraction(self, extraction, commission_data):
        buyer_table = self._find_buyer_table(extraction)
        if not buyer_table:
            return {"matched": 0, "records": commission_data.get("count", 0)}

        self._ensure_buyer_columns(buyer_table)
        records = commission_data.get("records", {})
        matched = 0

        for row in buyer_table.get("rows", []):
            row.setdefault("Vencimento", "")
            row.setdefault("Valor", "")
            if not row.get("Observação"):
                row["Observação"] = self._build_commission_note(
                    row.get("Leilao", ""),
                    row.get("Data do Leilao", ""),
                )

            buyer_key = self.normalize_name(row.get("Comprador", ""))
            commission_record = records.get(buyer_key)
            if commission_record:
                row["Vencimento"] = commission_record.get("Vencimento", "")
                row["Valor"] = commission_record.get("Valor", "")
                matched += 1

        metadata = extraction.setdefault("metadata", {})
        metadata["commission_filename"] = commission_data.get("filename", "")
        metadata["commission_due_date"] = commission_data.get("due_date", "")

        quality = extraction.setdefault("quality", {})
        quality["commission_records"] = commission_data.get("count", 0)
        quality["commission_matches"] = matched
        quality.setdefault("notes", []).append(
            "PDF de comissoes importado: "
            f"{commission_data.get('count', 0)} comprador(es), {matched} vinculado(s) por nome."
        )

        return {"matched": matched, "records": commission_data.get("count", 0)}

    def _collect_records_from_table(self, raw_table, records):
        rows = []
        for raw_row in raw_table or []:
            row = [self._clean_cell(cell) for cell in raw_row or []]
            if any(row):
                rows.append(row)

        if len(rows) < 2:
            return

        headers = rows[0]
        buyer_index = self._find_column(headers, ("comprador",))
        value_index = self._find_guillermo_column(headers)
        due_index = self._find_column(headers, ("venc",))

        if buyer_index is None or value_index is None:
            return

        required_width = max(index for index in [buyer_index, value_index, due_index] if index is not None) + 1
        for row in rows[1:]:
            normalized_row = row + [""] * max(0, required_width - len(row))
            buyer_name = normalized_row[buyer_index]
            value = normalized_row[value_index]
            due_date = normalized_row[due_index] if due_index is not None else ""

            if not buyer_name or not value or self._is_total_row(buyer_name):
                continue

            buyer_key = self.normalize_name(buyer_name)
            if not buyer_key:
                continue

            existing = records.get(buyer_key)
            if existing and existing.get("Valor"):
                continue

            records[buyer_key] = {
                "Comprador": buyer_name,
                "Vencimento": due_date,
                "Valor": value,
            }

    def _ensure_buyer_columns(self, buyer_table):
        headers = buyer_table.setdefault("headers", [])
        insert_after = "Documento"
        insert_at = headers.index(insert_after) + 1 if insert_after in headers else len(headers)

        for column in ["Vencimento", "Valor", "Observação"]:
            if column not in headers:
                headers.insert(insert_at, column)
                insert_at += 1
            else:
                insert_at = headers.index(column) + 1

    def _find_buyer_table(self, extraction):
        return next((table for table in extraction.get("tables", []) if table.get("id") == "buyers"), None)

    def _find_column(self, headers, fragments):
        for index, header in enumerate(headers):
            normalized = self._normalize_text(header)
            if any(fragment in normalized for fragment in fragments):
                return index
        return None

    def _find_guillermo_column(self, headers):
        for index, header in enumerate(headers):
            normalized = self._normalize_text(header)
            if "guillermo" in normalized or "guilhermo" in normalized:
                return index
            if "garces" in normalized and "junior" in normalized:
                return index

        if len(headers) >= 5 and any("comissao" in self._normalize_text(header) for header in headers):
            return 4
        return None

    def _build_commission_note(self, auction_label, auction_date):
        auction_text = self._clean_cell(auction_label)
        date_text = self._clean_cell(auction_date)

        if date_text and date_text not in auction_text:
            auction_text = " ".join(part for part in [auction_text, date_text] if part)

        if not auction_text:
            return "Comissão de compra"
        return f"Comissão de compra - {auction_text}"

    def _extract_due_date(self, text):
        due_match = self.DUE_DATE_PATTERN.search(text or "")
        if due_match:
            return due_match.group("date")

        date_match = self.DATE_PATTERN.search(text or "")
        return date_match.group(0) if date_match else ""

    def _is_total_row(self, value):
        normalized = self._normalize_text(value)
        return normalized in {"total", "totais"} or not any(char.isalpha() for char in normalized)

    def _clean_cell(self, value):
        value = "" if value is None else str(value)
        value = value.replace("\x00", " ")
        return re.sub(r"\s+", " ", value).strip()

    def _normalize_text(self, value):
        normalized = unicodedata.normalize("NFKD", self._clean_cell(value))
        no_accents = "".join(char for char in normalized if not unicodedata.combining(char))
        return re.sub(r"\s+", " ", no_accents).strip().lower()

    @classmethod
    def normalize_name(cls, value):
        value = "" if value is None else str(value)
        normalized = unicodedata.normalize("NFKD", value)
        no_accents = "".join(char for char in normalized if not unicodedata.combining(char))
        no_punctuation = re.sub(r"[^A-Za-z0-9]+", " ", no_accents)
        return re.sub(r"\s+", " ", no_punctuation).strip().upper()
