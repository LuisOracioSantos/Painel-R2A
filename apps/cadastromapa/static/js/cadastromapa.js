(function () {
    const LIMITE_LEILAO = 39;
    const PADRAO_LOTE_OBSERVACAO = /Lote(?:\(s\))?:\s*\d+/i;
    const camposCadastro = [
        "leilao",
        "datacontrato",
        "produto",
        "vendedor",
        "comprador",
        "cpfcnpj",
        "endereco",
        "numero",
        "bairro",
        "cep",
        "cidade",
        "uf",
        "complemento",
        "observacao",
    ];

    const estado = {
        paginas: [],
        paginaAtual: 0,
        selecoes: {},
    };

    document.addEventListener("DOMContentLoaded", iniciarCadastroMapa);

    function iniciarCadastroMapa() {
        const formPDF = document.getElementById("formPDF");

        if (!formPDF) {
            return;
        }

        formPDF.addEventListener("submit", enviarPDF);
        adicionarEvento("[data-acao='pagina-anterior']", "click", paginaAnterior);
        adicionarEvento("[data-acao='proxima-pagina']", "click", proximaPagina);
        adicionarEvento("[data-acao='exportar-excel']", "click", exportarExcel);
        adicionarEvento("#checkTodos", "change", alternarTodasParcelas);
        configurarValidacoes();
    }

    function adicionarEvento(seletor, evento, manipulador) {
        const elemento = document.querySelector(seletor);

        if (elemento) {
            elemento.addEventListener(evento, manipulador);
        }
    }

    function configurarValidacoes() {
        document.querySelectorAll(".cadastro-mapa-formulario input").forEach(function (campo) {
            campo.addEventListener("input", function () {
                salvarCamposPagina();
                replicarLeilao(campo);
                validarCampo(campo);
            });

            campo.addEventListener("change", function () {
                salvarCamposPagina();
                replicarLeilao(campo);
            });
        });
    }

    async function enviarPDF(evento) {
        evento.preventDefault();

        const inputPDF = document.getElementById("pdfFile");

        if (!inputPDF || !inputPDF.files.length) {
            marcarCampoInvalido(inputPDF, true);
            mostrarAlerta("Selecione um PDF antes de importar.");
            return;
        }

        marcarCampoInvalido(inputPDF, false);

        try {
            const dadosFormulario = new FormData(evento.currentTarget);
            const resposta = await fetch(window.CADASTRO_MAPA_CONFIG.importarUrl, {
                method: "POST",
                headers: {
                    "X-CSRF-Token": window.CADASTRO_MAPA_CONFIG.csrfToken,
                },
                body: dadosFormulario,
            });

            if (!resposta.ok) {
                mostrarAlerta(await lerMensagemErro(resposta));
                return;
            }

            const dados = await resposta.json();
            estado.paginas = Array.isArray(dados.paginas) ? dados.paginas : [];
            estado.paginaAtual = 0;
            estado.selecoes = criarSelecoesIniciais(estado.paginas);
            carregarPagina(0);
        } catch (erro) {
            console.error("Erro ao importar PDF:", erro);
            mostrarAlerta("Nao foi possivel importar o PDF.");
        }
    }

    function criarSelecoesIniciais(paginas) {
        return paginas.reduce(function (selecoes, pagina, indicePagina) {
            selecoes[indicePagina] = (pagina.parcelas || []).map(function (_, indiceParcela) {
                return indiceParcela;
            });
            return selecoes;
        }, {});
    }

    function carregarPagina(indice) {
        const pagina = estado.paginas[indice];

        estado.paginaAtual = indice;

        if (!pagina) {
            definirTextoPagina("Nenhum PDF carregado");
            renderizarParcelas([]);
            return;
        }

        preencherCampos(pagina);
        renderizarParcelas(pagina.parcelas || []);
        definirTextoPagina(`Pagina ${indice + 1} de ${estado.paginas.length}`);
        atualizarCheckTodos();
        validarFormularioCadastro();
    }

    function preencherCampos(pagina) {
        camposCadastro.forEach(function (campo) {
            definirValor(campo, pagina[campo] || "");
        });

        preencherLista("telefone", pagina.telefones || [], 3);
        preencherLista("email", pagina.emails || [], 3);
    }

    function definirValor(nomeCampo, valor) {
        const campo = document.querySelector(`[name='${nomeCampo}']`);

        if (campo) {
            campo.value = valor;
        }
    }

    function preencherLista(prefixo, valores, total) {
        for (let indice = 1; indice <= total; indice += 1) {
            definirValor(`${prefixo}${indice}`, valores[indice - 1] || "");
        }
    }

    function renderizarParcelas(parcelas) {
        const tbodyParcelas = document.getElementById("tbodyParcelas");

        if (!tbodyParcelas) {
            return;
        }

        tbodyParcelas.innerHTML = "";

        parcelas.forEach(function (parcela, indice) {
            const linha = document.createElement("tr");
            const colunaSelecao = document.createElement("td");
            const checkbox = document.createElement("input");

            checkbox.type = "checkbox";
            checkbox.className = "checkParcela";
            checkbox.dataset.index = String(indice);
            checkbox.checked = parcelaEstaSelecionada(indice);
            checkbox.addEventListener("change", atualizarSelecaoParcela);

            colunaSelecao.className = "text-center";
            colunaSelecao.appendChild(checkbox);

            linha.appendChild(colunaSelecao);
            linha.appendChild(criarCelula(parcela.parcela || ""));
            linha.appendChild(criarCelula(parcela.vencimento || ""));
            linha.appendChild(criarCelula(formatarValor(parcela.valor)));
            tbodyParcelas.appendChild(linha);
        });
    }

    function criarCelula(valor) {
        const celula = document.createElement("td");
        celula.textContent = valor;
        return celula;
    }

    function parcelaEstaSelecionada(indice) {
        const selecionadas = estado.selecoes[estado.paginaAtual] || [];
        return selecionadas.includes(indice);
    }

    function atualizarSelecaoParcela(evento) {
        const indice = Number(evento.currentTarget.dataset.index);

        if (!estado.selecoes[estado.paginaAtual]) {
            estado.selecoes[estado.paginaAtual] = [];
        }

        if (evento.currentTarget.checked) {
            adicionarParcelaSelecionada(indice);
        } else {
            estado.selecoes[estado.paginaAtual] = estado.selecoes[estado.paginaAtual].filter(function (item) {
                return item !== indice;
            });
        }

        atualizarCheckTodos();
    }

    function adicionarParcelaSelecionada(indice) {
        const selecionadas = estado.selecoes[estado.paginaAtual];

        if (!selecionadas.includes(indice)) {
            selecionadas.push(indice);
        }
    }

    function alternarTodasParcelas(evento) {
        const checkboxes = document.querySelectorAll(".checkParcela");
        const selecionadas = [];

        checkboxes.forEach(function (checkbox) {
            const indice = Number(checkbox.dataset.index);

            checkbox.checked = evento.currentTarget.checked;

            if (evento.currentTarget.checked) {
                selecionadas.push(indice);
            }
        });

        estado.selecoes[estado.paginaAtual] = selecionadas;
        evento.currentTarget.indeterminate = false;
    }

    function atualizarCheckTodos() {
        const checkTodos = document.getElementById("checkTodos");
        const checkboxes = document.querySelectorAll(".checkParcela");

        if (!checkTodos) {
            return;
        }

        if (checkboxes.length === 0) {
            checkTodos.checked = false;
            checkTodos.indeterminate = false;
            return;
        }

        const total = checkboxes.length;
        const marcados = Array.from(checkboxes).filter(function (checkbox) {
            return checkbox.checked;
        }).length;

        checkTodos.checked = total === marcados;
        checkTodos.indeterminate = marcados > 0 && marcados < total;
    }

    function paginaAnterior() {
        if (estado.paginaAtual > 0) {
            salvarCamposPagina();
            carregarPagina(estado.paginaAtual - 1);
        }
    }

    function proximaPagina() {
        if (estado.paginaAtual < estado.paginas.length - 1) {
            salvarCamposPagina();
            carregarPagina(estado.paginaAtual + 1);
        }
    }

    function salvarCamposPagina() {
        const pagina = estado.paginas[estado.paginaAtual];

        if (!pagina) {
            return;
        }

        camposCadastro.forEach(function (campo) {
            pagina[campo] = obterValor(campo);
        });

        pagina.telefones = [
            obterValor("telefone1"),
            obterValor("telefone2"),
            obterValor("telefone3"),
        ];

        pagina.emails = [
            obterValor("email1"),
            obterValor("email2"),
            obterValor("email3"),
        ];
    }

    function replicarLeilao(campo) {
        if (!campo || campo.id !== "leilao") {
            return;
        }

        const valor = campo.value.trim();

        estado.paginas.forEach(function (pagina) {
            pagina.leilao = valor;
        });
    }

    function obterValor(nomeCampo) {
        const campo = document.querySelector(`[name='${nomeCampo}']`);
        return campo ? campo.value.trim() : "";
    }

    async function exportarExcel() {
        salvarCamposPagina();

        if (!estado.paginas.length) {
            mostrarAlerta("Nenhum PDF foi carregado.");
            return;
        }

        if (!validarFormularioCadastro()) {
            mostrarAlerta("Corrija os campos destacados antes de exportar.");
            return;
        }

        const paginasFiltradas = estado.paginas.map(function (pagina, indicePagina) {
            const selecionadas = estado.selecoes[indicePagina] || [];
            const parcelas = selecionadas
                .map(function (indiceParcela) {
                    return (pagina.parcelas || [])[indiceParcela];
                })
                .filter(Boolean);

            return {
                ...pagina,
                parcelas,
            };
        }).filter(function (pagina) {
            return pagina.parcelas.length > 0;
        });

        if (!paginasFiltradas.length) {
            mostrarAlerta("Nenhuma parcela selecionada.");
            return;
        }

        try {
            const resposta = await fetch(window.CADASTRO_MAPA_CONFIG.exportarUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": window.CADASTRO_MAPA_CONFIG.csrfToken,
                },
                body: JSON.stringify({ paginas: paginasFiltradas }),
            });

            if (!resposta.ok) {
                mostrarAlerta(await lerMensagemErro(resposta), "erro");
                return;
            }

            const blob = await resposta.blob();
            baixarArquivo(obterNomeArquivoResposta(resposta, paginasFiltradas), blob);
        } catch (erro) {
            console.error("Erro ao exportar Excel:", erro);
            mostrarAlerta("Erro ao gerar Excel. Veja o console.", "erro");
        }
    }

    function obterNomeArquivoResposta(resposta, paginas) {
        const contentDisposition = resposta.headers.get("Content-Disposition") || "";
        const nomeHeader = contentDisposition.match(/filename\*?=(?:UTF-8'')?["']?([^;"']+)/i);

        if (nomeHeader) {
            return decodeURIComponent(nomeHeader[1].replace(/"/g, ""));
        }

        return `${normalizarNomeArquivo((paginas[0] && paginas[0].leilao) || "cadastro-mapa")}.xlsx`;
    }

    function normalizarNomeArquivo(nome) {
        return String(nome || "cadastro-mapa")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/[<>:"/\\|?*\x00-\x1f]/g, " ")
            .replace(/\s+/g, " ")
            .trim()
            .replace(/[. ]+$/g, "") || "cadastro-mapa";
    }

    function baixarArquivo(nomeArquivo, blob) {
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");

        link.href = url;
        link.download = nomeArquivo;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    }

    function validarFormularioCadastro() {
        const camposValidos = validarCamposObrigatorios();
        const leilaoValido = validarLeilao();
        const observacaoValida = validarObservacao();

        return camposValidos && leilaoValido && observacaoValida;
    }

    function validarCampo(campo) {
        if (campo.id === "leilao") {
            validarLeilao();
            return;
        }

        if (campo.id === "observacao") {
            validarObservacao();
            return;
        }

        if (campo.hasAttribute("required")) {
            validarCampoObrigatorio(campo);
        }
    }

    function validarCamposObrigatorios() {
        let formularioValido = true;

        document.querySelectorAll(".cadastro-mapa-formulario [required]").forEach(function (campo) {
            if (!validarCampoObrigatorio(campo)) {
                formularioValido = false;
            }
        });

        return formularioValido;
    }

    function validarCampoObrigatorio(campo) {
        const estaInvalido = campo.value.trim() === "";
        marcarCampoInvalido(campo, estaInvalido);
        return !estaInvalido;
    }

    function validarLeilao() {
        const campo = document.getElementById("leilao");
        const mensagem = document.getElementById("msgLeilao");

        if (!campo) {
            return true;
        }

        const estaVazio = campo.hasAttribute("required") && campo.value.trim() === "";
        const ultrapassouLimite = campo.value.length > LIMITE_LEILAO;

        marcarCampoInvalido(campo, estaVazio || ultrapassouLimite);
        alternarMensagem(mensagem, !ultrapassouLimite);
        return !estaVazio && !ultrapassouLimite;
    }

    function validarObservacao() {
        const campo = document.getElementById("observacao");
        const mensagem = document.getElementById("msgObservacao");

        if (!campo) {
            return true;
        }

        const possuiLote = PADRAO_LOTE_OBSERVACAO.test(campo.value.trim());

        marcarCampoInvalido(campo, !possuiLote);
        alternarMensagem(mensagem, possuiLote);
        return possuiLote;
    }

    function marcarCampoInvalido(campo, invalido) {
        if (campo) {
            campo.classList.toggle("is-invalid", invalido);
        }
    }

    function alternarMensagem(mensagem, ocultar) {
        if (mensagem) {
            mensagem.classList.toggle("oculto", ocultar);
        }
    }

    async function lerMensagemErro(resposta) {
        const tipoConteudo = resposta.headers.get("Content-Type") || "";

        if (tipoConteudo.includes("application/json")) {
            const dados = await resposta.json();
            return dados.erro || "Nao foi possivel concluir a operacao.";
        }

        return (await resposta.text()) || "Nao foi possivel concluir a operacao.";
    }

    function definirTextoPagina(texto) {
        const paginaAtual = document.getElementById("paginaAtual");

        if (paginaAtual) {
            paginaAtual.textContent = texto;
        }
    }

    function formatarValor(valor) {
        return Number(valor || 0).toLocaleString("pt-BR", {
            style: "currency",
            currency: "BRL",
        });
    }

    function mostrarAlerta(mensagem, tipo = "aviso") {
        const alerta = obterAlerta();

        alerta.className = `alerta-cadastromapa alerta-cadastromapa-${tipo}`;
        alerta.textContent = mensagem;
        alerta.classList.remove("oculto");

        window.clearTimeout(alerta.dataset.timer);
        alerta.dataset.timer = window.setTimeout(function () {
            alerta.classList.add("oculto");
        }, 3500);
    }

    function obterAlerta() {
        let alerta = document.getElementById("alertaCadastromapa");

        if (!alerta) {
            alerta = document.createElement("div");
            alerta.id = "alertaCadastromapa";
            alerta.className = "alerta-cadastromapa oculto";
            alerta.setAttribute("role", "alert");
            document.body.appendChild(alerta);
        }

        return alerta;
    }
})();
