let parcelasData = [];
let configBanco = {};

const configBoleto = window.CADASTRO_BOLETO_CONFIG || {};

document.addEventListener("DOMContentLoaded", function () {
    configurarBanco();
    configurarFormularioArquivo();
    configurarCliente();

    const botaoExportar = document.querySelector('[data-acao="exportar-excel"]');

    if (botaoExportar) {
        botaoExportar.addEventListener("click", exportarExcel);
    }
});

function configurarBanco() {
    document.querySelectorAll(
        '[name="cod_banco"], [name="agencia"], [name="conta_corrente"], [name="cod_carteira"], [name="cod_cedente"]'
    ).forEach(function (input) {
        input.addEventListener("change", function () {
            atualizarConfigBanco();
            renderTabela(parcelasData);
        });
    });

    atualizarConfigBanco();
}

function configurarFormularioArquivo() {
    const formArquivo = document.getElementById("formArquivoBoleto");
    const bancoArquivo = document.getElementById("bancoArquivo");

    if (formArquivo) {
        formArquivo.addEventListener("submit", function (evento) {
            evento.preventDefault();
            carregarPDF(evento.currentTarget);
        });
    }

    if (bancoArquivo) {
        bancoArquivo.addEventListener("change", alterarBancoArquivo);
    }
}

function configurarCliente() {
    const select = document.getElementById("empresaSelect");

    if (!select) {
        return;
    }

    select.addEventListener("change", function () {
        const cnpj = this.value;

        if (!cnpj || !configBoleto.buscarDadosUrl) {
            return;
        }

        fetch(`${configBoleto.buscarDadosUrl}?cnpj=${encodeURIComponent(cnpj)}`)
            .then(function (resposta) {
                return resposta.json();
            })
            .then(function (data) {
                parcelasData = data.parcelas || [];
                renderTabela(parcelasData);
            });
    });

    if (!configBoleto.clientesUrl) {
        return;
    }

    fetch(configBoleto.clientesUrl)
        .then(function (resposta) {
            return resposta.json();
        })
        .then(function (data) {
            const clientes = Array.isArray(data) ? data : [];

            clientes.forEach(function (item) {
                select.appendChild(new Option(
                    `${item.cnpj} - ${item.descricao || item.nome || ""}`,
                    item.cnpj
                ));
            });
        });
}

function atualizarConfigBanco() {
    configBanco = {
        cod_banco: valorCampo('[name="cod_banco"]'),
        agencia: valorCampo('[name="agencia"]'),
        conta_corrente: valorCampo('[name="conta_corrente"]'),
        cod_carteira: valorCampo('[name="cod_carteira"]'),
        cod_cedente: valorCampo('[name="cod_cedente"]'),
    };
}

function valorCampo(seletor) {
    const campo = document.querySelector(seletor);
    return campo ? campo.value : "";
}

function renderTabela(parcelas) {
    const tbody = document.querySelector("#tabelaDados tbody");

    if (!tbody) {
        return;
    }

    tbody.innerHTML = "";

    parcelas.forEach(function (item) {
        const row = document.createElement("tr");
        const vencimentoParcela = formatarDataBR(item.VENCIMENTO);
        const vencimentoBoleto = item.STATUS === "PAGA" ? "PAGA" : (item.vencimento_boleto || "");

        [
            item.CPFCNPJ,
            item.CONTRATO,
            item.NUMERO,
            vencimentoParcela,
            configBanco.cod_banco,
            configBanco.cod_carteira,
            configBanco.cod_cedente,
            configBanco.agencia,
            configBanco.conta_corrente,
            item.nosso_numero,
            vencimentoBoleto,
            item.VALOR,
            item.multa,
            item.juros,
            item.data_documento,
            item.linha_digitavel,
            item.codigo_barras,
            item.numero_documento,
            item.instrucoes,
            item.mensagens,
            item.pix_copia_cola,
            item.url,
        ].forEach(function (valor, indice) {
            const td = document.createElement("td");

            if (indice >= 17) {
                td.classList.add("oculto");
            }

            td.textContent = valor || "";
            row.appendChild(td);
        });

        tbody.appendChild(row);
    });
}

function carregarPDF(form) {
    const banco = form.banco.value;

    if (!banco) {
        alert("Selecione o banco.");
        return;
    }

    if (banco === "sicredi") {
        alert("Importacao de Excel Sicredi ainda nao esta configurada neste painel.");
        return;
    }

    const formData = new FormData(form);

    fetch(configBoleto.pdfUrl, {
        method: "POST",
        headers: {
            "X-CSRF-Token": configBoleto.csrfToken,
        },
        body: formData,
    })
        .then(function (resposta) {
            return resposta.json();
        })
        .then(function (dadosPDF) {
            dadosPDF.forEach(function (pdf) {
                const item = parcelasData.find(function (parcela) {
                    const valorTabela = normalizarValor(parcela.VALOR);
                    const dataTabela = formatarDataBR(parcela.VENCIMENTO);
                    const dataOk = dataTabela === pdf.vencimento;
                    const valorOk = Math.abs(valorTabela - pdf.valor) < 0.01;

                    return dataOk && valorOk;
                });

                if (item) {
                    item.vencimento_boleto = formatarDataBR(pdf.vencimento);
                    item.nosso_numero = pdf.nosso_numero;
                    item.linha_digitavel = pdf.linha_digitavel;
                    item.codigo_barras = pdf.codigo_barras;
                    item.juros = pdf.juros;
                    item.multa = pdf.multa;
                }
            });

            parcelasData.forEach(function (item) {
                if (item.juros == null) item.juros = 0;
                if (item.multa == null) item.multa = 0;
            });

            renderTabela(parcelasData);
            form.reset();
        });
}

function normalizarValor(valor) {
    if (valor === null || valor === undefined) return 0;
    if (typeof valor === "number") return valor;

    const texto = valor.toString().replace("R$", "").trim();

    if (texto.includes(",")) {
        return parseFloat(texto.replace(/\./g, "").replace(",", "."));
    }

    return parseFloat(texto);
}

function formatarDataBR(data) {
    if (!data) return "";

    if (typeof data === "string" && data.includes("/")) {
        return data;
    }

    if (typeof data === "string" && data.includes("-")) {
        const dataLimpa = data.split("T")[0];
        const [ano, mes, dia] = dataLimpa.split("-");
        return `${dia}/${mes}/${ano}`;
    }

    const d = new Date(data);
    const dia = String(d.getUTCDate()).padStart(2, "0");
    const mes = String(d.getUTCMonth() + 1).padStart(2, "0");
    const ano = d.getUTCFullYear();

    return `${dia}/${mes}/${ano}`;
}

function exportarExcel() {
    const dadosParaExportar = parcelasData
        .filter(function (item) {
            return item.STATUS !== "PAGA";
        })
        .map(function (item) {
            return {
                ...item,
                cod_banco: configBanco.cod_banco,
                cod_carteira: configBanco.cod_carteira,
                cod_cedente: configBanco.cod_cedente,
                agencia: configBanco.agencia,
                conta_corrente: configBanco.conta_corrente,
            };
        });

    fetch(configBoleto.exportarUrl, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": configBoleto.csrfToken,
        },
        body: JSON.stringify(dadosParaExportar),
    })
        .then(function (resposta) {
            if (!resposta.ok) throw new Error("Erro ao exportar.");
            return resposta.blob();
        })
        .then(function (blob) {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");

            a.href = url;
            a.download = "boletos.xlsx";
            a.click();
            window.URL.revokeObjectURL(url);
        })
        .catch(function (erro) {
            console.error("Erro:", erro);
        });
}

function alterarBancoArquivo() {
    const banco = document.getElementById("bancoArquivo").value;
    const input = document.getElementById("arquivoBoleto");
    const label = document.getElementById("labelArquivoBoleto");

    input.value = "";

    if (banco === "sicredi") {
        input.accept = ".xlsx,.xls";
        label.innerText = "Arquivo Excel Sicredi";
    } else if (banco === "sicoob") {
        input.accept = ".pdf";
        label.innerText = "Arquivo PDF Sicoob";
    } else {
        input.accept = "";
        label.innerText = "Arquivo";
    }
}
