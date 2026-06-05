import os
import re
import shutil
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


class PDFExtractionError(Exception):
    pass


class PDFExtractor:
    KEY_VALUE_PATTERN = re.compile(
        r"^\s*(?P<label>[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9\s\-/().,%]{1,80}?)\s*(?::|=| - | – | — |\t)\s*(?P<value>.+?)\s*$"
    )
    EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
    DATE_PATTERN = re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
    MONEY_PATTERN = re.compile(r"(?:R\$\s*)?\d{1,3}(?:\.\d{3})*,\d{2}|\b\d+\.\d{2}\b")
    PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}")
    CPF_PATTERN = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
    CNPJ_PATTERN = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
    CEP_PATTERN = re.compile(r"\bCEP\s*:?\s*(?P<cep>\d{5}[-\s]*-?\d{2,3})\b", re.IGNORECASE)
    CODE_PATTERN = re.compile(r"Cod\.?\s*de\s*Est\.?\s*:\s*(?P<code>[0-9.\-/]*)", re.IGNORECASE)
    INSCRICAO_PATTERN = re.compile(
        r"Inscri(?:c|ç|cao|ção)[a-z]*\s*:\s*(?P<value>.*?)(?=\s*-\s*Cod\.?\s*de\s*Est\.?\s*:|$)",
        re.IGNORECASE,
    )
    FARM_CITY_UF_PATTERN = re.compile(
        r"([A-Za-zÀ-ÿ0-9 .'ºª-]+)/(AC|AL|AP|AM|BA|CE|DF|ES|EX|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b"
    )

    def extract(self, pdf_path, original_name=None):
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise PDFExtractionError("Arquivo PDF nao encontrado.")

        ocr_used = False
        pages, tables, metadata = self._extract_with_pdfplumber(pdf_path)
        if not pages:
            pages, metadata = self._extract_with_pypdf(pdf_path)

        if not self._pages_have_text(pages):
            ocr_pages = self._try_ocr(pdf_path)
            if self._pages_have_text(ocr_pages):
                pages = ocr_pages
                ocr_used = True

        text = "\n".join(page["text"] for page in pages if page["text"])
        auction_date = self._extract_auction_date(text)
        auction_label = self._extract_auction_label(text, auction_date)
        fields = self._extract_fields(text, metadata)
        buyer_table = self._find_table(tables, "buyers")
        if not buyer_table and text:
            text_buyer_records = self._collect_buyers_from_text(text)
            buyer_table = self._build_buyer_table(text_buyer_records)
            if buyer_table:
                for table in tables:
                    table["selected"] = False
                tables.insert(0, buyer_table)
        if buyer_table:
            self._apply_auction_info_to_buyers(buyer_table, auction_date, auction_label)
            self._annotate_buyer_missing_fields(buyer_table)
        buyers = buyer_table.get("rows", []) if buyer_table else []
        if buyers:
            for field in fields:
                field["selected"] = False
        quality = self._build_quality_summary(pages, tables, fields, buyers)
        if ocr_used:
            quality["engine"] = "ocr"
            quality["notes"].insert(0, "Texto extraido por OCR porque o PDF nao possui texto selecionavel.")

        return {
            "metadata": {
                "filename": original_name or pdf_path.name,
                "pages": len(pages),
                "auction_date": auction_date,
                "auction_label": auction_label,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "engine": quality["engine"],
            },
            "quality": quality,
            "fields": fields,
            "tables": tables,
            "buyers": buyers,
            "pages": pages,
            "full_text": text,
        }

    def _pages_have_text(self, pages):
        return any(self._clean_scalar(page.get("text", "")) for page in pages or [])

    def _extract_with_pdfplumber(self, pdf_path):
        try:
            import pdfplumber
        except ImportError:
            return [], [], {}

        pages = []
        tables = []
        buyer_records = []
        current_buyer = None
        metadata = {}

        try:
            with pdfplumber.open(pdf_path) as pdf:
                metadata = dict(pdf.metadata or {})
                for page_number, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text(layout=True) or page.extract_text() or ""
                    pages.append({"number": page_number, "text": self._clean_text(text)})

                    for table_index, raw_table in enumerate(page.extract_tables() or [], start=1):
                        current_buyer = self._collect_buyers_from_raw_table(
                            raw_table,
                            page_number,
                            buyer_records,
                            current_buyer,
                        )
                        table = self._normalize_table(raw_table, page_number, table_index)
                        if table:
                            tables.append(table)
        except Exception as exc:
            raise PDFExtractionError(f"Nao foi possivel ler o PDF: {exc}") from exc

        if current_buyer:
            buyer_records.append(self._finalize_buyer_record(current_buyer))

        buyer_table = self._build_buyer_table(buyer_records)
        if buyer_table:
            for table in tables:
                table["selected"] = False
            tables.insert(0, buyer_table)

        return pages, tables, metadata

    def _collect_buyers_from_raw_table(self, raw_table, page_number, buyer_records, current_buyer):
        for raw_row in raw_table or []:
            row = list(raw_row or [])
            while len(row) < 2:
                row.append("")

            left = self._clean_cell_text(row[0])
            right = self._clean_cell_text(row[1])

            if self._is_noise_table_row(left, right):
                continue

            if self._is_buyer_start_row(left, right):
                if current_buyer:
                    buyer_records.append(self._finalize_buyer_record(current_buyer))
                current_buyer = self._parse_buyer_start(left, right, page_number)
                continue

            if not current_buyer:
                continue

            contact_type = self._contact_type(left)
            if contact_type:
                self._append_contact_chunk(current_buyer, contact_type, self._strip_contact_label(left))
                continue

            if left and current_buyer.get("_last_contact"):
                self._append_contact_chunk(current_buyer, current_buyer["_last_contact"], left)
            elif right:
                current_buyer["address_farm_raw"] = self._join_parts([current_buyer.get("address_farm_raw"), right])

        return current_buyer

    def _is_noise_table_row(self, left, right):
        left_normalized = self._clean_scalar(left).lower()
        right_normalized = self._clean_scalar(right).lower()
        if not left_normalized and not right_normalized:
            return True
        noise_fragments = [
            "relacao de compradores",
            "relação de compradores",
            "nelore gibertoni",
            "taquaritinga - sp",
        ]
        if any(fragment in left_normalized for fragment in noise_fragments):
            return True
        return left_normalized in {"nome documento", "nome\n documento", "nome\ndocumento"} or (
            "nome" in left_normalized
            and "documento" in left_normalized
            and "endereco" in right_normalized.replace("ç", "c")
        )

    def _is_buyer_start_row(self, left, right):
        if not left or not right:
            return False
        if self._contact_type(left):
            return False
        if self.CPF_PATTERN.search(left) or self.CNPJ_PATTERN.search(left):
            return True

        buyer_right_markers = [
            "cep",
            "inscri",
            "cod. de est",
            "fazenda",
            "sitio",
            "sítio",
            "estancia",
            "estância",
            "investidor",
            "agropec",
            "boitel",
            "cabana",
            "cabaña",
        ]
        normalized_right = self._strip_accents(right).lower()
        return any(marker in normalized_right for marker in buyer_right_markers)

    def _parse_buyer_start(self, left, right, page_number):
        identity = self._parse_identity(left)
        address_info = self._parse_address_and_farm(right)
        buyer = {
            "name": identity["name"],
            "document": identity["document"],
            "document_type": identity["document_type"],
            "cpf": identity["cpf"],
            "cnpj": identity["cnpj"],
            "page": page_number,
            "address_farm_raw": right,
            "phone_chunks": [],
            "email_chunks": [],
            "_last_contact": None,
        }
        buyer.update(address_info)
        return buyer

    def _parse_identity(self, value):
        lines = [line for line in self._clean_cell_text(value).splitlines() if line]
        joined = self._clean_scalar(" ".join(lines))
        cnpj_match = self.CNPJ_PATTERN.search(joined)
        cpf_match = self.CPF_PATTERN.search(joined)
        doc_match = cnpj_match or cpf_match

        if doc_match:
            document = doc_match.group(0)
            name = self._clean_scalar(joined[: doc_match.start()])
        else:
            document = ""
            name = joined

        document_type = ""
        cpf = ""
        cnpj = ""
        if cpf_match:
            document_type = "CPF"
            cpf = cpf_match.group(0)
        elif cnpj_match:
            document_type = "CNPJ"
            cnpj = cnpj_match.group(0)

        return {
            "name": name,
            "document": document,
            "document_type": document_type,
            "cpf": cpf,
            "cnpj": cnpj,
        }

    def _parse_address_and_farm(self, value):
        text = self._clean_scalar(value)
        cep_match = self.CEP_PATTERN.search(text)

        if cep_match:
            address = text[: cep_match.end()].strip(" -")
            farm_text = text[cep_match.end() :].strip(" -")
            cep = cep_match.group("cep")
            address_city, address_uf = self._parse_city_uf_from_address(text[: cep_match.start()])
        else:
            split_index = self._find_farm_start(text)
            address = text[:split_index].strip(" -") if split_index > 0 else text
            farm_text = text[split_index:].strip(" -") if split_index > 0 else ""
            cep = ""
            address_city, address_uf = self._parse_city_uf_from_address(address)

        farm_info = self._parse_farm_info(farm_text)
        return {
            "address": address,
            "address_neighborhood": self._parse_neighborhood_from_address(address, address_city, address_uf),
            "address_city": address_city,
            "address_uf": address_uf,
            "cep": cep,
            **farm_info,
        }

    def _find_farm_start(self, text):
        normalized = self._strip_accents(text).lower()
        markers = [
            " fazenda ",
            " sitio ",
            " estancia ",
            " investidor",
            " agropec",
            " boitel ",
            " haras ",
            " cabana ",
        ]
        positions = [normalized.find(marker) for marker in markers if normalized.find(marker) > 0]
        return min(positions) if positions else -1

    def _parse_city_uf_from_address(self, value):
        parts = [part.strip(" .") for part in re.split(r"\s+-\s+", value) if part.strip(" .")]
        for index in range(len(parts) - 1, 0, -1):
            if re.fullmatch(r"[A-Z]{2}|EX", parts[index]):
                return parts[index - 1], parts[index]
        return "", ""

    def _parse_farm_info(self, value):
        text = self._clean_scalar(value)
        inscription = ""
        establishment_code = ""

        inscription_match = self.INSCRICAO_PATTERN.search(text)
        if inscription_match:
            inscription = inscription_match.group("value").strip(" -")

        code_match = self.CODE_PATTERN.search(text)
        if code_match:
            establishment_code = code_match.group("code").strip(" -")

        detail_end = len(text)
        markers = [match.start() for match in [inscription_match, code_match] if match]
        if markers:
            detail_end = min(markers)

        farm_detail = text[:detail_end].strip(" -")
        farm_name = farm_detail
        if " - " in farm_detail:
            farm_name = farm_detail.split(" - ", 1)[0].strip()

        farm_city = ""
        farm_uf = ""
        city_match = self.FARM_CITY_UF_PATTERN.search(farm_detail)
        if city_match:
            farm_city = self._clean_scalar(city_match.group(1).split(" - ")[-1])
            farm_uf = city_match.group(2)

        return {
            "farm": farm_name,
            "farm_detail": farm_detail,
            "farm_neighborhood": self._parse_neighborhood_from_address(farm_detail, farm_city, farm_uf),
            "farm_city": farm_city,
            "farm_uf": farm_uf,
            "state_registration": inscription,
            "establishment_code": establishment_code,
        }

    def _append_contact_chunk(self, buyer, contact_type, value):
        value = self._clean_scalar(value)
        if not value:
            return
        key = "phone_chunks" if contact_type == "phone" else "email_chunks"
        buyer.setdefault(key, []).append(value)
        buyer["_last_contact"] = contact_type

    def _contact_type(self, value):
        normalized = self._strip_accents(value).lower().strip()
        if normalized.startswith("telefone(s):") or normalized.startswith("telefones:"):
            return "phone"
        if normalized.startswith("e-mail(s):") or normalized.startswith("email(s):") or normalized.startswith("emails:"):
            return "email"
        return None

    def _strip_contact_label(self, value):
        return re.sub(r"^\s*(?:Telefone\(s\)|Telefones|E-mail\(s\)|Email\(s\)|Emails)\s*:\s*", "", value, flags=re.IGNORECASE)

    def _finalize_buyer_record(self, buyer):
        phones_raw = self._clean_scalar(" ".join(buyer.get("phone_chunks", [])))
        emails_raw = self._clean_scalar(" ".join(buyer.get("email_chunks", [])))
        phones = self._dedupe_preserve_order(self.PHONE_PATTERN.findall(phones_raw))[:3]
        emails = self._dedupe_preserve_order(self.EMAIL_PATTERN.findall(emails_raw))[:3]
        address_data = self._select_address_data(buyer)

        return {
            "Comprador": buyer.get("name", ""),
            "Documento": buyer.get("document", ""),
            "Vencimento": "",
            "Valor": "",
            "Observação": "",
            "Tipo Documento": buyer.get("document_type", ""),
            "CPF": buyer.get("cpf", ""),
            "CNPJ": buyer.get("cnpj", ""),
            "Endereco": address_data["address"],
            "Bairro": address_data["neighborhood"] or "Centro",
            "Cidade": address_data["city"],
            "UF": address_data["uf"],
            "CEP": buyer.get("cep", ""),
            "Fazenda": buyer.get("farm", ""),
            "Endereco Fazenda": buyer.get("farm_detail", ""),
            "Cidade Fazenda": buyer.get("farm_city", ""),
            "UF Fazenda": buyer.get("farm_uf", ""),
            "Inscricao Estadual": buyer.get("state_registration", ""),
            "Codigo Estabelecimento": buyer.get("establishment_code", ""),
            "Telefone 1": self._list_value(phones, 0),
            "Telefone 2": self._list_value(phones, 1),
            "Telefone 3": self._list_value(phones, 2),
            "Email 1": self._list_value(emails, 0),
            "Email 2": self._list_value(emails, 1),
            "Email 3": self._list_value(emails, 2),
            "Pagina": buyer.get("page", ""),
        }

    def _collect_buyers_from_text(self, text):
        buyer_records = []
        current_buyer = None
        previous_line = ""
        lines = [self._clean_scalar(line) for line in text.splitlines()]
        lines = [line for line in lines if line and not self._is_text_noise_line(line)]

        for index, line in enumerate(lines):
            doc_match = self.CNPJ_PATTERN.search(line) or self.CPF_PATTERN.search(line)
            if doc_match:
                if current_buyer:
                    buyer_records.append(self._finalize_text_buyer_record(current_buyer))

                before_document = self._clean_scalar(line[: doc_match.start()])
                name_source = before_document or previous_line
                name, first_address = self._split_text_buyer_name_address(name_source)
                document = doc_match.group(0)
                after_document = self._clean_scalar(line[doc_match.end() :].strip(" -"))

                current_buyer = {
                    "name": name,
                    "document": document,
                    "document_type": "CNPJ" if self.CNPJ_PATTERN.fullmatch(document) else "CPF",
                    "cpf": document if self.CPF_PATTERN.fullmatch(document) else "",
                    "cnpj": document if self.CNPJ_PATTERN.fullmatch(document) else "",
                    "page": "",
                    "address_farm_raw": self._join_parts([first_address, after_document]),
                    "phone_chunks": [],
                    "email_chunks": [],
                    "_last_contact": None,
                }
                previous_line = line
                continue

            if current_buyer:
                contact_type = self._contact_type(line)
                if contact_type:
                    self._append_contact_chunk(current_buyer, contact_type, self._strip_contact_label(line))
                    previous_line = line
                    continue

                next_line = lines[index + 1] if index + 1 < len(lines) else ""
                if self.CNPJ_PATTERN.search(next_line) or self.CPF_PATTERN.search(next_line):
                    previous_line = line
                    continue

                if current_buyer.get("_last_contact") and self._looks_like_contact_continuation(line):
                    self._append_contact_chunk(current_buyer, current_buyer["_last_contact"], line)
                else:
                    current_buyer["address_farm_raw"] = self._join_parts(
                        [current_buyer.get("address_farm_raw"), line]
                    )
                    current_buyer["_last_contact"] = None

            previous_line = line

        if current_buyer:
            buyer_records.append(self._finalize_text_buyer_record(current_buyer))

        return buyer_records

    def _finalize_text_buyer_record(self, buyer):
        buyer.update(self._parse_address_and_farm(buyer.get("address_farm_raw", "")))
        return self._finalize_buyer_record(buyer)

    def _split_text_buyer_name_address(self, value):
        text = self._clean_scalar(value)
        if not text:
            return "", ""

        normalized = self._strip_accents(text).lower()
        markers = [
            " rua ",
            " r. ",
            " av. ",
            " avenida ",
            " alameda ",
            " estrada ",
            " rod. ",
            " rodovia ",
            " praca ",
            " travessa ",
            " fazenda ",
            " sitio ",
            " chacara ",
        ]
        search_text = f" {normalized} "
        positions = []
        for marker in markers:
            position = search_text.find(marker)
            if position > 3:
                positions.append(position - 1)

        if not positions:
            return text, ""

        split_at = min(positions)
        name = text[:split_at].strip(" -")
        address = text[split_at:].strip(" -")
        if not name:
            return text, ""
        return name, address

    def _looks_like_contact_continuation(self, value):
        return bool(self.PHONE_PATTERN.search(value) or self.EMAIL_PATTERN.search(value) or "|" in value)

    def _is_text_noise_line(self, value):
        normalized = self._strip_accents(value).lower()
        noise_fragments = [
            "relacao de compradores",
            "taquaritinga - sp",
            "nome endereco",
            "documento fazenda",
        ]
        return any(fragment in normalized for fragment in noise_fragments)

    def _build_buyer_table(self, buyer_records):
        rows = [row for row in buyer_records if row.get("Comprador") or row.get("Nome/Razao Social")]
        if not rows:
            return None

        headers = [
            "Leilao",
            "Comprador",
            "Data do Leilao",
            "Documento",
            "Vencimento",
            "Valor",
            "Observação",
            "Endereco",
            "Bairro",
            "Cidade",
            "UF",
            "CEP",
            "Fazenda",
            "Telefone 1",
            "Telefone 2",
            "Telefone 3",
            "Email 1",
            "Email 2",
            "Email 3",
        ]
        return {
            "id": "buyers",
            "title": "Compradores detectados",
            "page": "varias",
            "headers": headers,
            "rows": rows,
            "selected": True,
            "kind": "buyers",
        }

    def _extract_auction_date(self, text):
        for line in text.splitlines():
            normalized = self._strip_accents(line).lower()
            if "relacao de compradores" in normalized:
                continue
            match = self.DATE_PATTERN.search(line)
            if match:
                return match.group(0)
        match = self.DATE_PATTERN.search(text)
        return match.group(0) if match else ""

    def _extract_auction_label(self, text, auction_date):
        for line in text.splitlines():
            clean_line = self._clean_scalar(line)
            if not clean_line or not auction_date or auction_date not in clean_line:
                continue
            normalized = self._strip_accents(clean_line).lower()
            if "relacao de compradores" in normalized:
                continue
            return clean_line

        return auction_date

    def _apply_auction_info_to_buyers(self, buyer_table, auction_date, auction_label):
        headers = buyer_table.get("headers", [])
        if "Leilao" not in headers:
            headers.insert(0, "Leilao")

        if "Comprador" not in headers and "Nome/Razao Social" in headers:
            for row in buyer_table.get("rows", []):
                row["Comprador"] = row.pop("Nome/Razao Social", "")
            headers[headers.index("Nome/Razao Social")] = "Comprador"

        if "Data do Leilao" not in headers:
            insert_at = 1 if headers else 0
            headers.insert(insert_at, "Data do Leilao")

        for hidden_header in [
            "Tipo Documento",
            "CPF",
            "CNPJ",
            "Inscricao Estadual",
            "Codigo Estabelecimento",
            "Endereco Fazenda",
            "Cidade Fazenda",
            "UF Fazenda",
            "Telefones",
            "Emails",
        ]:
            while hidden_header in headers:
                headers.remove(hidden_header)

        for row in buyer_table.get("rows", []):
            row["Leilao"] = auction_label
            row["Data do Leilao"] = auction_date
            row["Observação"] = self._build_commission_note(auction_label, auction_date)

    def _build_commission_note(self, auction_label, auction_date):
        auction_text = self._clean_scalar(auction_label)
        date_text = self._clean_scalar(auction_date)

        if date_text and date_text not in auction_text:
            auction_text = self._join_parts([auction_text, date_text])

        if not auction_text:
            return "Comissão de compra"
        return f"Comissão de compra - {auction_text}"

    def _annotate_buyer_missing_fields(self, buyer_table):
        missing_count = 0
        missing_rows = 0

        for row in buyer_table.get("rows", []):
            missing_fields = []
            if self._is_blank(row.get("Leilao")):
                missing_fields.append("Leilao")
            if self._is_blank(row.get("Comprador")):
                missing_fields.append("Comprador")
            if self._is_blank(row.get("Data do Leilao")):
                missing_fields.append("Data do Leilao")

            if self._is_blank(row.get("Documento")):
                missing_fields.append("Documento")

            row["__missing_fields"] = missing_fields
            if missing_fields:
                missing_rows += 1
                missing_count += len(missing_fields)

        buyer_table["missing_count"] = missing_count
        buyer_table["missing_rows"] = missing_rows

    def _is_blank(self, value):
        return self._clean_scalar(value) in {"", "-", "None", "null"}

    def _is_blank_address(self, value):
        clean_value = self._clean_scalar(value)
        normalized = self._strip_accents(clean_value).lower()
        return normalized in {"", "-", ".", ". -", "- -", ". - -", "none", "null"} or normalized.startswith(". - - inscri")

    def _select_address_data(self, buyer):
        use_farm_address = self._is_blank_address(buyer.get("address")) and not self._is_blank_address(buyer.get("farm_detail"))
        if use_farm_address:
            return {
                "address": buyer.get("farm_detail", ""),
                "neighborhood": buyer.get("farm_neighborhood", ""),
                "city": buyer.get("farm_city", ""),
                "uf": buyer.get("farm_uf", ""),
            }

        return {
            "address": buyer.get("address", ""),
            "neighborhood": buyer.get("address_neighborhood", ""),
            "city": buyer.get("address_city", ""),
            "uf": buyer.get("address_uf", ""),
        }

    def _parse_neighborhood_from_address(self, value, city="", uf=""):
        text = self._clean_scalar(value)
        if not text:
            return ""

        explicit_match = re.search(r"\bBairro\s*:\s*([^|-]+)", text, flags=re.IGNORECASE)
        if explicit_match:
            return self._clean_scalar(explicit_match.group(1)).strip(" .")

        cep_match = self.CEP_PATTERN.search(text)
        before_cep = text[: cep_match.start()] if cep_match else text
        parts = [part.strip(" .") for part in re.split(r"\s+-\s+", before_cep) if part.strip(" .")]
        if len(parts) < 3:
            return ""

        city_index = self._find_city_part_index(parts, city, uf)
        if city_index is None or city_index <= 1:
            return ""

        for candidate in reversed(parts[1:city_index]):
            if self._looks_like_neighborhood(candidate):
                return candidate
        return ""

    def _find_city_part_index(self, parts, city="", uf=""):
        normalized_city = self._strip_accents(city).lower()
        normalized_uf = self._strip_accents(uf).upper()
        for index in range(1, len(parts)):
            current = self._strip_accents(parts[index]).lower()
            next_part = self._strip_accents(parts[index + 1]).upper() if index + 1 < len(parts) else ""
            if normalized_city and current == normalized_city:
                return index
            if normalized_uf and next_part == normalized_uf:
                return index
        return None

    def _looks_like_neighborhood(self, value):
        normalized = self._strip_accents(value).lower()
        if not normalized:
            return False
        ignored_prefixes = ("caixa postal", "apto", "ap ", "apartamento", "casa ", "sala ", "loja ", "lote ")
        return not normalized.startswith(ignored_prefixes)

    def _extract_with_pypdf(self, pdf_path):
        try:
            from pypdf import PdfReader
        except ImportError:
            return [], {}

        try:
            reader = PdfReader(str(pdf_path))
            metadata = {k.replace("/", ""): v for k, v in dict(reader.metadata or {}).items()}
            pages = [
                {"number": index + 1, "text": self._clean_text(page.extract_text() or "")}
                for index, page in enumerate(reader.pages)
            ]
        except Exception as exc:
            raise PDFExtractionError(f"Nao foi possivel ler o PDF: {exc}") from exc

        return pages, metadata

    def _project_root(self):
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parents[2]

    def _resolve_tesseract_cmd(self):
        root = self._project_root()
        candidates = [
            os.environ.get("LEITOR_PDFS_TESSERACT_CMD"),
            os.environ.get("TESSERACT_CMD"),
            shutil.which("tesseract"),
            root / "tools" / "Tesseract-OCR" / "tesseract.exe",
            root / "tools" / "tesseract" / "tesseract.exe",
            Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
            Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
        ]

        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.exists():
                return str(path)
        return ""

    def _resolve_poppler_path(self):
        if shutil.which("pdftoppm"):
            return ""

        root = self._project_root()
        candidates = [
            os.environ.get("LEITOR_PDFS_POPPLER_PATH"),
            os.environ.get("POPPLER_PATH"),
            root / "tools" / "poppler" / "Library" / "bin",
            root / "tools" / "poppler" / "bin",
            root / "tools" / "Poppler" / "Library" / "bin",
        ]

        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if (path / "pdftoppm.exe").exists():
                return str(path)

        poppler_root = root / "tools" / "poppler"
        if poppler_root.exists():
            for path in poppler_root.glob("*/Library/bin"):
                if (path / "pdftoppm.exe").exists():
                    return str(path)
        return ""

    def _tesseract_config(self, tesseract_cmd):
        if not tesseract_cmd:
            return ""
        tessdata_dir = Path(tesseract_cmd).with_name("tessdata")
        if tessdata_dir.exists():
            os.environ["TESSDATA_PREFIX"] = str(tessdata_dir)
        return ""

    def _try_ocr(self, pdf_path):
        try:
            from pdf2image import convert_from_path
            import pytesseract
        except ImportError:
            return []

        tesseract_cmd = self._resolve_tesseract_cmd()
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        poppler_path = self._resolve_poppler_path()
        convert_options = {"dpi": 220, "first_page": 1}
        if poppler_path:
            convert_options["poppler_path"] = poppler_path

        try:
            images = convert_from_path(str(pdf_path), **convert_options)
        except Exception:
            return []

        pages = []
        config = self._tesseract_config(tesseract_cmd)
        for page_number, image in enumerate(images, start=1):
            text = self._ocr_image_to_text(pytesseract, image, config)
            pages.append({"number": page_number, "text": self._clean_text(text)})
        return pages

    def _ocr_image_to_text(self, pytesseract, image, config):
        for language in ("por+eng", "eng"):
            try:
                return pytesseract.image_to_string(image, lang=language, config=config)
            except Exception:
                continue
        return ""

    def _extract_fields(self, text, metadata):
        fields = []
        used_keys = set()

        for key, value in (metadata or {}).items():
            clean_value = self._clean_scalar(value)
            if clean_value:
                self._append_field(
                    fields,
                    used_keys,
                    label=f"Metadado: {self._humanize_label(key)}",
                    value=clean_value,
                    source="metadata",
                    confidence=0.72,
                )

        for line in self._iter_relevant_lines(text):
            match = self.KEY_VALUE_PATTERN.match(line)
            if not match:
                continue

            label = self._clean_scalar(match.group("label"))
            value = self._clean_scalar(match.group("value"))
            if not self._looks_like_label(label) or not value:
                continue

            self._append_field(
                fields,
                used_keys,
                label=self._humanize_label(label),
                value=value,
                source="key_value",
                confidence=0.86,
            )

        self._append_detected_list(fields, used_keys, "Emails detectados", self.EMAIL_PATTERN.findall(text))
        self._append_detected_list(fields, used_keys, "Datas detectadas", self.DATE_PATTERN.findall(text))
        self._append_detected_list(fields, used_keys, "Valores monetarios detectados", self.MONEY_PATTERN.findall(text))
        self._append_detected_list(fields, used_keys, "Telefones detectados", self.PHONE_PATTERN.findall(text))

        return fields[:250]

    def _append_detected_list(self, fields, used_keys, label, values):
        unique_values = []
        seen = set()
        for value in values:
            normalized = self._clean_scalar(value)
            if normalized and normalized not in seen:
                unique_values.append(normalized)
                seen.add(normalized)
        if unique_values:
            self._append_field(
                fields,
                used_keys,
                label=label,
                value="; ".join(unique_values[:50]),
                source="pattern",
                confidence=0.66,
            )

    def _append_field(self, fields, used_keys, label, value, source, confidence):
        key_base = self._slugify(label)
        if not key_base:
            return

        key = key_base
        suffix = 2
        while key in used_keys:
            key = f"{key_base}_{suffix}"
            suffix += 1

        used_keys.add(key)
        fields.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "source": source,
                "confidence": confidence,
                "selected": source in {"key_value", "metadata"},
            }
        )

    def _normalize_table(self, raw_table, page_number, table_index):
        cleaned_rows = []
        for raw_row in raw_table or []:
            row = [self._clean_scalar(cell) for cell in raw_row]
            if any(row):
                cleaned_rows.append(row)

        if len(cleaned_rows) < 2:
            return None

        width = max(len(row) for row in cleaned_rows)
        normalized_rows = [row + [""] * (width - len(row)) for row in cleaned_rows]
        header = normalized_rows[0]

        if self._row_looks_like_data(header):
            headers = [f"Coluna {index}" for index in range(1, width + 1)]
            rows = normalized_rows
        else:
            headers = [cell or f"Coluna {index}" for index, cell in enumerate(header, start=1)]
            rows = normalized_rows[1:]

        headers = self._deduplicate_headers(headers)
        rows_as_dicts = [
            {headers[index]: row[index] for index in range(width)}
            for row in rows
            if any(row)
        ]

        if not rows_as_dicts:
            return None

        return {
            "id": f"table_{page_number}_{table_index}",
            "title": f"Tabela {table_index} - pagina {page_number}",
            "page": page_number,
            "headers": headers,
            "rows": rows_as_dicts,
            "selected": True,
        }

    def _build_quality_summary(self, pages, tables, fields, buyers=None):
        buyers = buyers or []
        characters = sum(len(page.get("text", "")) for page in pages)
        engine = "pdfplumber/pypdf"
        notes = []

        if characters == 0:
            engine = "ocr-or-empty"
            notes.append(
                "Nao foi encontrado texto selecionavel. Se o PDF for imagem, instale o suporte OCR opcional."
            )
        if not fields:
            notes.append("Nenhum campo chave-valor foi detectado automaticamente.")
        if not tables:
            notes.append("Nenhuma tabela estruturada foi detectada automaticamente.")
        if buyers:
            notes.append(f"Foram detectados {len(buyers)} compradores em formato tabular.")

        return {
            "engine": engine,
            "characters": characters,
            "tables": len(tables),
            "fields": len(fields),
            "buyers": len(buyers),
            "notes": notes,
        }

    def _iter_relevant_lines(self, text):
        for raw_line in text.splitlines():
            line = self._clean_scalar(raw_line)
            if 4 <= len(line) <= 220:
                yield line

    def _row_looks_like_data(self, row):
        non_empty = [cell for cell in row if cell]
        if not non_empty:
            return True
        numeric_like = sum(bool(re.search(r"\d", cell)) for cell in non_empty)
        return numeric_like >= max(1, len(non_empty) // 2)

    def _deduplicate_headers(self, headers):
        counts = Counter()
        result = []
        for header in headers:
            base = self._humanize_label(header) or "Coluna"
            counts[base] += 1
            result.append(base if counts[base] == 1 else f"{base} {counts[base]}")
        return result

    def _looks_like_label(self, label):
        if not label or len(label) > 90:
            return False
        if len(label.split()) > 12:
            return False
        letters = sum(char.isalpha() for char in label)
        return letters >= 2

    def _clean_text(self, value):
        value = value or ""
        value = value.replace("\x00", " ")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()

    def _clean_scalar(self, value):
        value = "" if value is None else str(value)
        value = value.replace("\x00", " ")
        return re.sub(r"\s+", " ", value).strip()

    def _clean_cell_text(self, value):
        if value is None:
            return ""
        lines = [self._clean_scalar(line) for line in str(value).replace("\x00", " ").splitlines()]
        return "\n".join(line for line in lines if line)

    def _humanize_label(self, label):
        label = self._clean_scalar(label)
        label = label.replace("_", " ").replace("-", " ")
        label = re.sub(r"\s+", " ", label)
        return label[:1].upper() + label[1:] if label else ""

    def _slugify(self, value):
        value = self._strip_accents(self._clean_scalar(value)).lower()
        value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
        return value[:64]

    def _strip_accents(self, value):
        normalized = unicodedata.normalize("NFKD", self._clean_scalar(value))
        return "".join(char for char in normalized if not unicodedata.combining(char))

    def _dedupe_preserve_order(self, values):
        result = []
        seen = set()
        for value in values:
            clean_value = self._clean_scalar(value)
            if clean_value and clean_value not in seen:
                result.append(clean_value)
                seen.add(clean_value)
        return result

    def _join_parts(self, values):
        return " ".join(self._clean_scalar(value) for value in values if self._clean_scalar(value))

    def _find_table(self, tables, table_id):
        return next((table for table in tables if table.get("id") == table_id), None)

    def _list_value(self, values, index):
        return values[index] if len(values) > index else ""
