import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from apps.comum.seguranca import usuario_tem_acesso_aplicacao

from .service.commission_extractor import CommissionExtractionError, CommissionExtractor
from .service.excel_exporter import ExcelExporter
from .service.pdf_extractor import PDFExtractor, PDFExtractionError
from .utils.storage import JsonStorage


cadastrocomissao_bp = Blueprint(
    "cadastrocomissao",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="static",
    url_prefix="/cadastrocomissao",
)
SHARED_BUYER_FIELDS = {"Leilao", "Data do Leilao", "ObservaÃ§Ã£o"}


@cadastrocomissao_bp.before_request
def exigir_acesso_cadastro_comissao():
    if request.endpoint == "cadastrocomissao.static":
        return None

    if not current_user.is_authenticated:
        return redirect(url_for("autenticacao.exibir_login", next=request.full_path))

    if current_user.tem_perfil_admin or usuario_tem_acesso_aplicacao("cadastrocomissao.index"):
        return None

    abort(403)


def _allowed_file(filename):
    suffix = Path(filename).suffix.lower().replace(".", "")
    return suffix in current_app.config["ALLOWED_EXTENSIONS"]


@cadastrocomissao_bp.get("/")
def index():
    return render_template("index.html")


@cadastrocomissao_bp.post("/extract")
def extract_pdf():
    uploaded_file = request.files.get("pdf_file")
    commission_file = request.files.get("commission_file")
    if not uploaded_file or uploaded_file.filename == "":
        flash("Selecione um arquivo PDF para continuar.", "warning")
        return redirect(url_for("cadastrocomissao.index"))

    if not _allowed_file(uploaded_file.filename):
        flash("Formato invalido. Envie um arquivo com extensao .pdf.", "danger")
        return redirect(url_for("cadastrocomissao.index"))

    has_commission_file = commission_file and commission_file.filename
    if has_commission_file and not _allowed_file(commission_file.filename):
        flash("Formato invalido no PDF de comissoes. Envie um arquivo com extensao .pdf.", "danger")
        return redirect(url_for("cadastrocomissao.index"))

    original_name = secure_filename(uploaded_file.filename)
    extraction_id = uuid4().hex
    stored_name = f"{extraction_id}_{original_name}"
    pdf_path = current_app.config["UPLOAD_FOLDER"] / stored_name
    uploaded_file.save(pdf_path)

    commission_path = None
    if has_commission_file:
        commission_name = secure_filename(commission_file.filename)
        commission_stored_name = f"{extraction_id}_comissoes_{commission_name}"
        commission_path = current_app.config["UPLOAD_FOLDER"] / commission_stored_name
        commission_file.save(commission_path)

    try:
        extraction = PDFExtractor().extract(pdf_path, original_name=uploaded_file.filename)
    except PDFExtractionError as exc:
        _delete_uploaded_pdf(extraction_id)
        flash(str(exc), "danger")
        return redirect(url_for("cadastrocomissao.index"))

    if commission_path:
        commission_extractor = CommissionExtractor()
        try:
            commission_data = commission_extractor.extract(
                commission_path,
                original_name=commission_file.filename,
            )
            commission_result = commission_extractor.apply_to_extraction(extraction, commission_data)
            if commission_result["records"] == 0:
                flash("O PDF de comissoes foi lido, mas nenhum valor do Guillermo foi encontrado.", "warning")
            elif commission_result["matched"] == 0:
                flash("O PDF de comissoes foi lido, mas nenhum comprador foi vinculado por nome.", "warning")
        except CommissionExtractionError as exc:
            flash(str(exc), "warning")

    buyer_table = _find_buyer_table(extraction)
    if buyer_table:
        _refresh_buyer_annotations(buyer_table)

    JsonStorage(current_app.config["EXTRACTION_FOLDER"]).save(extraction_id, extraction)
    return render_template("review.html", extraction_id=extraction_id, extraction=extraction)


@cadastrocomissao_bp.get("/review/<extraction_id>")
def review_extraction(extraction_id):
    extraction = JsonStorage(current_app.config["EXTRACTION_FOLDER"]).load(extraction_id)
    if extraction is None:
        flash("Extracao expirada ou nao encontrada. Envie o PDF novamente.", "warning")
        return redirect(url_for("cadastrocomissao.index"))

    buyer_table = _find_buyer_table(extraction)
    if buyer_table:
        _refresh_buyer_annotations(buyer_table)
        JsonStorage(current_app.config["EXTRACTION_FOLDER"]).save(extraction_id, extraction)

    return render_template("review.html", extraction_id=extraction_id, extraction=extraction)


@cadastrocomissao_bp.post("/clear/<extraction_id>")
def clear_extraction(extraction_id):
    storage = JsonStorage(current_app.config["EXTRACTION_FOLDER"])
    storage.delete(extraction_id)
    _delete_uploaded_pdf(extraction_id)
    return redirect(url_for("cadastrocomissao.index"))


@cadastrocomissao_bp.post("/buyers/<extraction_id>/rows/<int:row_index>")
def update_buyer_row(extraction_id, row_index):
    storage = JsonStorage(current_app.config["EXTRACTION_FOLDER"])
    extraction = storage.load(extraction_id)
    if extraction is None:
        return jsonify({"ok": False, "message": "Extracao expirada ou nao encontrada."}), 404

    buyer_table = _find_buyer_table(extraction)
    rows = buyer_table.get("rows", []) if buyer_table else []
    if not buyer_table or row_index < 0 or row_index >= len(rows):
        return jsonify({"ok": False, "message": "Linha de comprador nao encontrada."}), 404

    payload = request.get_json(silent=True) or {}
    values = payload.get("values", {})
    if not isinstance(values, dict):
        return jsonify({"ok": False, "message": "Dados invalidos para salvar a linha."}), 400

    row = rows[row_index]
    old_observation = _clean_scalar(row.get("ObservaÃ§Ã£o", ""))
    old_auto_observation = _build_commission_note(row.get("Leilao", ""), row.get("Data do Leilao", ""))

    allowed_columns = set(buyer_table.get("headers", []))
    cleaned_values = {
        key: _clean_scalar(value)
        for key, value in values.items()
        if key in allowed_columns and not key.startswith("__")
    }
    changed_shared_fields = {
        key
        for key in SHARED_BUYER_FIELDS
        if key in cleaned_values and cleaned_values[key] != _clean_scalar(row.get(key, ""))
    }
    should_replicate_shared = bool(payload.get("replicate_shared")) and bool(changed_shared_fields)

    for key, value in cleaned_values.items():
        if not should_replicate_shared or key not in SHARED_BUYER_FIELDS:
            row[key] = value

    shared_targets = rows if should_replicate_shared else [row]
    for target in shared_targets:
        for key in ["Leilao", "Data do Leilao"]:
            if key in cleaned_values:
                target[key] = cleaned_values[key]

        if "ObservaÃ§Ã£o" in cleaned_values and cleaned_values["ObservaÃ§Ã£o"] not in {"", old_auto_observation}:
            target["ObservaÃ§Ã£o"] = cleaned_values["ObservaÃ§Ã£o"]
        elif changed_shared_fields:
            target["ObservaÃ§Ã£o"] = _build_commission_note(
                target.get("Leilao", ""),
                target.get("Data do Leilao", ""),
            )

        if "Bairro" in allowed_columns and not target.get("Bairro"):
            target["Bairro"] = "Centro"

    _refresh_buyer_annotations(buyer_table)
    if isinstance(extraction.get("buyers"), list):
        for index, target in enumerate(rows):
            if index < len(extraction["buyers"]):
                extraction["buyers"][index] = target

    storage.save(extraction_id, extraction)
    updated_rows = [{"index": index, "row": target} for index, target in enumerate(rows)]
    return jsonify({
        "ok": True,
        "message": "Linha salva com sucesso.",
        "row": row,
        "rows": updated_rows,
        "replicated": should_replicate_shared,
        "missing_count": buyer_table.get("missing_count", 0),
        "missing_rows": buyer_table.get("missing_rows", 0),
    })


@cadastrocomissao_bp.post("/export")
def export_excel():
    extraction_id = request.form.get("extraction_id", "").strip()
    selection_payload = request.form.get("selection_payload", "").strip()

    if not extraction_id or not selection_payload:
        flash("A selecao para exportacao nao foi recebida. Revise o PDF novamente.", "warning")
        return redirect(url_for("cadastrocomissao.index"))

    storage = JsonStorage(current_app.config["EXTRACTION_FOLDER"])
    extraction = storage.load(extraction_id)
    if extraction is None:
        flash("Extracao expirada ou nao encontrada. Envie o PDF novamente.", "warning")
        return redirect(url_for("cadastrocomissao.index"))

    try:
        selection = json.loads(selection_payload)
    except json.JSONDecodeError:
        flash("Nao foi possivel interpretar a selecao de colunas.", "danger")
        return redirect(url_for("cadastrocomissao.index"))

    exporter = ExcelExporter(current_app.config["EXPORT_FOLDER"])
    output_path = exporter.export(extraction, selection, id_cadastro=current_user.id_cadastro)
    return send_file(output_path, as_attachment=True, download_name=output_path.name)


def _delete_uploaded_pdf(extraction_id):
    if not all(char.isalnum() or char in {"_", "-"} for char in extraction_id):
        return

    for upload_path in current_app.config["UPLOAD_FOLDER"].glob(f"{extraction_id}_*"):
        if upload_path.is_file():
            upload_path.unlink()


def _find_buyer_table(extraction):
    return next((table for table in extraction.get("tables", []) if table.get("id") == "buyers"), None)


def _refresh_buyer_annotations(buyer_table):
    missing_count = 0
    missing_rows = 0
    duplicate_summary = _annotate_duplicate_buyers(buyer_table)

    for row in buyer_table.get("rows", []):
        missing_fields = []
        for field in ["Leilao", "Comprador", "Data do Leilao", "Documento"]:
            if _is_blank(row.get(field)):
                missing_fields.append(field)

        row["__missing_fields"] = missing_fields
        if missing_fields:
            missing_rows += 1
            missing_count += len(missing_fields)

    buyer_table["missing_count"] = missing_count
    buyer_table["missing_rows"] = missing_rows
    buyer_table.update(duplicate_summary)


def _annotate_duplicate_buyers(buyer_table):
    rows = buyer_table.get("rows", [])
    name_counts = defaultdict(int)
    name_value_counts = defaultdict(int)
    duplicate_name_rows = 0
    duplicate_name_value_rows = 0

    for row in rows:
        row.pop("__duplicate_status", None)
        row.pop("__duplicate_message", None)

        name_key = _normalize_duplicate_key(row.get("Comprador", ""))
        value_key = _normalize_value_key(row.get("Valor", ""))
        if not name_key:
            continue

        name_counts[name_key] += 1
        if value_key:
            name_value_counts[(name_key, value_key)] += 1

    for row in rows:
        name_key = _normalize_duplicate_key(row.get("Comprador", ""))
        value_key = _normalize_value_key(row.get("Valor", ""))
        if not name_key or name_counts[name_key] <= 1:
            continue

        if value_key and name_value_counts[(name_key, value_key)] > 1:
            row["__duplicate_status"] = "name_value"
            row["__duplicate_message"] = "Comprador duplicado com o mesmo valor."
            duplicate_name_value_rows += 1
        else:
            row["__duplicate_status"] = "name"
            row["__duplicate_message"] = "Comprador duplicado."
            duplicate_name_rows += 1

    return {
        "duplicate_name_rows": duplicate_name_rows,
        "duplicate_name_value_rows": duplicate_name_value_rows,
        "duplicate_rows": duplicate_name_rows + duplicate_name_value_rows,
    }


def _build_commission_note(auction_label, auction_date):
    auction_text = _clean_scalar(auction_label)
    date_text = _clean_scalar(auction_date)

    if date_text and date_text not in auction_text:
        auction_text = " ".join(part for part in [auction_text, date_text] if part)

    if not auction_text:
        return "ComissÃ£o de compra"
    return f"ComissÃ£o de compra - {auction_text}"


def _is_blank(value):
    return _clean_scalar(value) in {"", "-", "None", "null"}


def _clean_scalar(value):
    value = "" if value is None else str(value)
    value = value.replace("\x00", " ")
    return " ".join(value.split()).strip()


def _normalize_duplicate_key(value):
    value = unicodedata.normalize("NFKD", _clean_scalar(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^A-Za-z0-9]+", " ", value)
    return " ".join(value.upper().split())


def _normalize_value_key(value):
    value = _clean_scalar(value)
    if not value:
        return ""

    normalized = value.replace("R$", "").replace(".", "").replace(" ", "").replace(",", ".")
    normalized = re.sub(r"[^0-9.-]", "", normalized)
    if not normalized:
        return ""

    try:
        return f"{float(normalized):.2f}"
    except ValueError:
        return _normalize_duplicate_key(value)

