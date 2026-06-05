select   tp.pes_cpfcnpj as cnpj, tp.pes_nome as nome  from tb_pessoa tp
inner join  tb_cliente tcli on  tcli.cli_id = tp.pes_id
order by tp.pes_nome