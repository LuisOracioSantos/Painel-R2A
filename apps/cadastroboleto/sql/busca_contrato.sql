DECLARE @cpf VARCHAR(20) = :cnpj;
DECLARE @today DATE = CAST(GETDATE() AS DATE);

;WITH pago_cte AS (
    SELECT par.par_id,
           par.par_valor,
           par.par_vencimento,
           par.neg_id,
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
    p.pes_cpfcnpj AS [CPF/CNPJ],
    p.pes_nome AS [CLIENTE],
    cre_pes.pes_nome AS [CREDOR],
    c.con_inclusao AS [INCLUSAO],
    c.con_numero AS [CONTRATO],
    UPPER(e.est_nome) AS [ESTAGIO],
    pr.pro_nome AS [PRODUTO],
    c.con_data AS [DATA],
    c.con_expiracao AS [EXPIRACAO],
    (SELECT MIN(pc.par_vencimento)
     FROM pago_cte pc
     JOIN tb_negociacao n ON n.neg_id = pc.neg_id
     WHERE n.con_id = c.con_id AND pc.pago_bruto < pc.par_valor)
     AS [MENOR_VCTO]

FROM tb_pessoa p
JOIN tb_contrato c ON c.cli_id = p.pes_id
JOIN tb_credor cr ON cr.cre_id = c.cre_id
JOIN tb_pessoa cre_pes ON cre_pes.pes_id = cr.cre_id
LEFT JOIN tb_estagio e ON e.est_id = c.est_id
LEFT JOIN tb_produto pr ON pr.pro_id = c.pro_id

WHERE p.pes_cpfcnpj = @cpf
ORDER BY c.con_inclusao;