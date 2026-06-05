DECLARE @cpf VARCHAR(20) = :cnpj;

;WITH pago_cte AS (
    SELECT par.par_id,
        CAST(COALESCE(
            (SELECT SUM(pp.pgo_valor) FROM tb_pagamento_parcela pp WHERE pp.par_id = par.par_id),
            (SELECT SUM(ap.acp_total)  FROM tb_acordo_parcela ap
               JOIN tb_pagamento pg ON pg.aco_id = ap.aco_id
              WHERE ap.par_id = par.par_id),
            (SELECT pg.pgo_valor FROM tb_pagamento pg WHERE pg.pgo_id = par.fin_id),
            0
        ) AS DECIMAL(18,2)) AS pago_bruto
    FROM tb_parcela par
)

SELECT
    p.pes_cpfcnpj AS [CPFCNPJ],
    p.pes_nome AS [CLIENTE],
    c.con_numero AS [CONTRATO],
    par.par_numero AS [NUMERO],
    par.par_vencimento AS [VENCIMENTO],
    par.par_valor AS [VALOR],
    CASE WHEN pc.pago_bruto >= par.par_valor THEN 'PAGA' ELSE '' END AS [STATUS]

FROM tb_pessoa p
JOIN tb_contrato c ON c.cli_id = p.pes_id
JOIN tb_negociacao n ON n.con_id = c.con_id
JOIN tb_parcela par ON par.neg_id = n.neg_id
JOIN pago_cte pc ON pc.par_id = par.par_id

WHERE p.pes_cpfcnpj = @cpf
ORDER BY c.con_numero, TRY_CAST(par.par_numero AS INT);