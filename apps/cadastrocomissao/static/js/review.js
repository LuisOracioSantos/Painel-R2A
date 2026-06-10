const exportForm = document.getElementById("exportForm");
const selectionPayload = document.getElementById("selectionPayload");
const excludeMissingDocument = document.getElementById("excludeMissingDocument");
const editBuyerModalElement = document.getElementById("editBuyerModal");
const editBuyerForm = document.getElementById("editBuyerForm");
const editBuyerFields = document.getElementById("editBuyerFields");
const editRowIndex = document.getElementById("editRowIndex");
const editBuyerStatus = document.getElementById("editBuyerStatus");
const editAuctionLengthAlert = document.getElementById("editAuctionLengthAlert");
const saveBuyerRowButton = document.getElementById("saveBuyerRowButton");
const replicateSharedFields = document.getElementById("replicateSharedFields");
const editBuyerModal = editBuyerModalElement ? new bootstrap.Modal(editBuyerModalElement) : null;
const AUCTION_LENGTH_LIMIT = 39;

function collectBuyerSelection() {
  const buyersTable = document.querySelector("[data-table-id='buyers']");
  if (!buyersTable) {
    return [];
  }

  const columns = Array.from(buyersTable.querySelectorAll("[data-column-key]")).map((column) => ({
    key: column.dataset.columnKey,
    include: true,
    label: column.dataset.columnKey,
  }));

  return [{
    id: "buyers",
    include: true,
    title: "Compradores",
    columns,
  }];
}

exportForm?.addEventListener("submit", () => {
  selectionPayload.value = JSON.stringify({
    fields: [],
    tables: collectBuyerSelection(),
    custom_columns: [],
    options: {
      exclude_missing_document: Boolean(excludeMissingDocument?.checked),
    },
  });
});

function getBuyerColumns() {
  return Array.from(document.querySelectorAll("[data-table-id='buyers'] [data-column-key]")).map((column) => column.dataset.columnKey);
}

function getRowValues(row) {
  return Array.from(row.querySelectorAll("[data-field]")).reduce((values, cell) => {
    values[cell.dataset.field] = cell.dataset.value || "";
    return values;
  }, {});
}

function shouldUseTextarea(field, value) {
  return ["Leilao", "Endereco", "Observação"].includes(field) || value.length > 90;
}

function updateAuctionLengthAlert() {
  const auctionInput = editBuyerFields?.querySelector("[name='Leilao']");
  const value = auctionInput?.value || "";
  editAuctionLengthAlert?.classList.toggle("d-none", value.length <= AUCTION_LENGTH_LIMIT);
}

function createFieldControl(field, value) {
  const wrapper = document.createElement("div");
  wrapper.className = "edit-field";

  const label = document.createElement("label");
  label.className = "form-label";
  label.textContent = field;

  const control = shouldUseTextarea(field, value) ? document.createElement("textarea") : document.createElement("input");
  control.className = "form-control form-control-sm";
  control.name = field;
  control.value = value;
  if (control.tagName === "TEXTAREA") {
    control.rows = field === "Endereco" || field === "Observação" ? 3 : 2;
  } else {
    control.type = "text";
  }

  if (field === "Leilao") {
    control.addEventListener("input", updateAuctionLengthAlert);
  }

  wrapper.append(label, control);
  return wrapper;
}

function appendDuplicateIndicator(cell, status, message) {
  if (status === "name_value") {
    const badge = document.createElement("span");
    badge.className = "duplicate-badge duplicate-badge-strong";
    badge.title = message || "";
    badge.textContent = "! Nome e valor";
    cell.appendChild(badge);
    return;
  }

  if (status === "name") {
    const icon = document.createElement("span");
    icon.className = "duplicate-icon";
    icon.title = message || "";
    icon.textContent = "!";
    cell.appendChild(icon);
  }
}

function renderCellValue(cell, field, value, rowData) {
  const cleanValue = value || "";
  const missingFields = Array.isArray(rowData.__missing_fields) ? rowData.__missing_fields : [];
  const duplicateStatus = field === "Comprador" ? rowData.__duplicate_status || "" : "";
  const duplicateMessage = field === "Comprador" ? rowData.__duplicate_message || "" : "";
  const isMissing = missingFields.includes(field);
  const isLongAuction = field === "Leilao" && cleanValue.length > AUCTION_LENGTH_LIMIT;

  cell.dataset.value = cleanValue;
  cell.classList.toggle("missing-cell", isMissing);
  cell.classList.toggle("long-cell", !isMissing && isLongAuction);
  cell.classList.toggle("duplicate-cell", !isMissing && !isLongAuction && Boolean(duplicateStatus));
  cell.classList.toggle("duplicate-name-value", !isMissing && !isLongAuction && duplicateStatus === "name_value");
  cell.classList.toggle("duplicate-name", !isMissing && !isLongAuction && duplicateStatus === "name");
  cell.classList.toggle("empty-cell", !isMissing && !isLongAuction && !duplicateStatus && !cleanValue);

  cell.innerHTML = "";
  if (isMissing) {
    const badge = document.createElement("span");
    badge.className = "missing-badge";
    badge.textContent = "Pendente";
    cell.appendChild(badge);
    return;
  }

  if (cleanValue) {
    cell.appendChild(document.createTextNode(cleanValue));
    if (isLongAuction) {
      cell.appendChild(document.createElement("br"));
      const badge = document.createElement("span");
      badge.className = "length-badge";
      badge.textContent = "Mais de 39";
      cell.appendChild(badge);
    } else if (duplicateStatus) {
      appendDuplicateIndicator(cell, duplicateStatus, duplicateMessage);
    }
    return;
  }

  const dash = document.createElement("span");
  dash.className = "empty-dash";
  dash.textContent = "-";
  cell.appendChild(dash);
}

function applySavedRow(rowIndex, savedRow) {
  const tableRow = document.querySelector(`tr[data-row-index="${rowIndex}"]`);
  if (!tableRow) {
    return;
  }

  tableRow.querySelectorAll("[data-field]").forEach((cell) => {
    const field = cell.dataset.field;
    renderCellValue(cell, field, savedRow[field] || "", savedRow);
  });
  updateLongAuctionSummary();
}

function applySavedRows(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return;
  }

  rows.forEach((item) => {
    applySavedRow(item.index, item.row);
  });
}

function updateLongAuctionSummary() {
  const longAuctionCells = Array.from(document.querySelectorAll("[data-field='Leilao']")).filter((cell) => (cell.dataset.value || "").length > AUCTION_LENGTH_LIMIT);
  const alert = document.getElementById("longAuctionAlert");
  if (!alert) {
    return;
  }

  if (longAuctionCells.length === 0) {
    alert.classList.add("d-none");
    return;
  }

  alert.classList.remove("d-none");
  alert.textContent = `${longAuctionCells.length} linha(s) com o campo Leilao acima de 39 caracteres. Use Editar para ajustar antes de exportar.`;
}

document.addEventListener("click", (event) => {
  const button = event.target.closest(".edit-row-btn");
  if (!button || !editBuyerModal || !editBuyerFields || !editRowIndex) {
    return;
  }

  const row = button.closest("tr");
  if (!row) {
    return;
  }

  const values = getRowValues(row);
  editRowIndex.value = button.dataset.rowIndex;
  editBuyerFields.innerHTML = "";
  editBuyerStatus.textContent = "";
  saveBuyerRowButton.disabled = false;
  if (replicateSharedFields) {
    replicateSharedFields.checked = true;
  }

  getBuyerColumns().forEach((field) => {
    editBuyerFields.appendChild(createFieldControl(field, values[field] || ""));
  });

  updateAuctionLengthAlert();
  editBuyerModal.show();
});

editBuyerForm?.addEventListener("submit", async (event) => {
  event.preventDefault();

  const buyersTable = document.querySelector("[data-table-id='buyers']");
  const extractionId = buyersTable?.dataset.extractionId;
  const rowIndex = editRowIndex?.value;
  if (!extractionId || rowIndex === "") {
    return;
  }

  const values = Array.from(editBuyerFields.querySelectorAll("input, textarea")).reduce((payload, field) => {
    payload[field.name] = field.value;
    return payload;
  }, {});

  saveBuyerRowButton.disabled = true;
  editBuyerStatus.textContent = "Salvando...";

  try {
    const response = await fetch(`/cadastrocomissao/buyers/${encodeURIComponent(extractionId)}/rows/${rowIndex}`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": window.csrfToken || "",
      },
      body: JSON.stringify({
        values,
        replicate_shared: Boolean(replicateSharedFields?.checked),
      }),
    });
    const result = await response.json();

    if (!response.ok || !result.ok) {
      editBuyerStatus.textContent = result.message || "Nao foi possivel salvar a linha.";
      saveBuyerRowButton.disabled = false;
      return;
    }

    editBuyerStatus.textContent = "Linha salva.";
    if (Array.isArray(result.rows) && result.rows.length > 0) {
      applySavedRows(result.rows);
    } else {
      applySavedRow(rowIndex, result.row || values);
    }
    editBuyerModal?.hide();
  } catch (error) {
    editBuyerStatus.textContent = "Nao foi possivel salvar a linha.";
    saveBuyerRowButton.disabled = false;
  }
});
